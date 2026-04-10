"""
Square Billing Service

Integrates with Square Subscriptions API for recurring billing.
Handles plan management, subscription lifecycle, and payment webhooks.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Organization, Subscription, SubscriptionStatus, UsageRecord

TYPE_CHECKING = False
if TYPE_CHECKING:
    from src.licensing.subscription_bridge import SubscriptionLicenseBridge

logger = logging.getLogger(__name__)


class SquarePlan(str, Enum):
    """Available subscription plans (canonical tier names)."""
    SANDBOX = "sandbox"
    PROGRAM = "program"
    INSTITUTION = "institution"
    SYSTEM = "system"


@dataclass
class PlanLimits:
    """Rate limits and quotas per plan."""
    api_calls_per_month: int
    webhook_endpoints: int
    api_keys: int
    ip_allowlist_entries: int
    priority_support: bool
    custom_branding: bool
    can_use_service_key_vault: bool  # Can use service provider's key vault
    requires_remote_signing: bool  # Must use remote signing with own keys


PLAN_LIMITS: dict[SquarePlan, PlanLimits] = {
    SquarePlan.SANDBOX: PlanLimits(
        api_calls_per_month=1000,
        webhook_endpoints=1,
        api_keys=2,
        ip_allowlist_entries=5,
        priority_support=False,
        custom_branding=False,
        can_use_service_key_vault=True,
        requires_remote_signing=False,
    ),
    SquarePlan.PROGRAM: PlanLimits(
        api_calls_per_month=50000,
        webhook_endpoints=5,
        api_keys=10,
        ip_allowlist_entries=20,
        priority_support=False,
        custom_branding=False,
        can_use_service_key_vault=False,
        requires_remote_signing=True,
    ),
    SquarePlan.INSTITUTION: PlanLimits(
        api_calls_per_month=500000,
        webhook_endpoints=20,
        api_keys=50,
        ip_allowlist_entries=100,
        priority_support=True,
        custom_branding=True,
        can_use_service_key_vault=False,
        requires_remote_signing=True,
    ),
    SquarePlan.SYSTEM: PlanLimits(
        api_calls_per_month=-1,  # Unlimited
        webhook_endpoints=-1,
        api_keys=-1,
        ip_allowlist_entries=-1,
        priority_support=True,
        custom_branding=True,
        can_use_service_key_vault=False,
        requires_remote_signing=True,
    ),
}


@dataclass
class SquareConfig:
    """Square API configuration."""
    access_token: str
    environment: str = "sandbox"  # "sandbox" or "production"
    location_id: str = ""
    webhook_signature_key: str = ""
    
    @property
    def base_url(self) -> str:
        if self.environment == "production":
            return "https://connect.squareup.com/v2"
        return "https://connect.squareupsandbox.com/v2"


class SquareService:
    """
    Square Subscriptions API integration.
    
    Handles:
    - Creating subscription plans in Square
    - Managing customer subscriptions
    - Processing webhooks for payment events
    - Syncing subscription status with local database
    """
    
    def __init__(
        self,
        config: SquareConfig,
        db_session: AsyncSession,
        license_bridge: Optional["SubscriptionLicenseBridge"] = None,
    ):
        self.config = config
        self.db = db_session
        self._client: Optional[httpx.AsyncClient] = None
        self._license_bridge = license_bridge
        
        # Map Square plan IDs to our plans (configured externally)
        self._plan_catalog_ids: dict[SquarePlan, str] = {}
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                headers={
                    "Authorization": f"Bearer {self.config.access_token}",
                    "Content-Type": "application/json",
                    "Square-Version": "2024-01-18",
                },
                timeout=30.0,
            )
        return self._client
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
    
    def set_plan_catalog_id(self, plan: SquarePlan, catalog_id: str) -> None:
        """Map a Square catalog object ID to a plan."""
        self._plan_catalog_ids[plan] = catalog_id
    
    async def create_customer(
        self,
        organization: Organization,
        email: str,
        company_name: Optional[str] = None,
    ) -> str:
        """
        Create a Square customer for an organization.
        
        Returns the Square customer ID.
        """
        client = await self._get_client()
        
        response = await client.post(
            "/customers",
            json={
                "idempotency_key": str(uuid4()),
                "email_address": email,
                "company_name": company_name or organization.name,
                "reference_id": str(organization.id),
                "note": f"Marty organization: {organization.slug}",
            },
        )
        
        if response.status_code != 200:
            logger.error(f"Square create customer failed: {response.text}")
            raise SquareError(f"Failed to create customer: {response.text}")
        
        data = response.json()
        customer_id = data["customer"]["id"]
        
        # Store Square customer ID on organization
        organization.square_customer_id = customer_id
        await self.db.commit()
        
        logger.info(f"Created Square customer {customer_id} for org {organization.slug}")
        return customer_id
    
    async def create_subscription(
        self,
        organization: Organization,
        plan: SquarePlan,
        card_id: Optional[str] = None,
    ) -> Subscription:
        """
        Create a new subscription for an organization.
        
        Args:
            organization: The organization to subscribe
            plan: The subscription plan
            card_id: Square card ID for payment (optional for free plan)
            
        Returns:
            The created Subscription record
        """
        if plan != SquarePlan.SANDBOX and not card_id:
            raise SquareError("Payment method required for paid plans")
        
        client = await self._get_client()
        
        # Get or create Square customer
        if not organization.square_customer_id:
            raise SquareError("Organization must have a Square customer ID")
        
        catalog_id = self._plan_catalog_ids.get(plan)
        if not catalog_id and plan != SquarePlan.SANDBOX:
            raise SquareError(f"No catalog ID configured for plan: {plan}")
        
        square_subscription_id = None
        
        # Create subscription in Square (skip for sandbox plan)
        if plan != SquarePlan.SANDBOX and catalog_id:
            response = await client.post(
                "/subscriptions",
                json={
                    "idempotency_key": str(uuid4()),
                    "location_id": self.config.location_id,
                    "customer_id": organization.square_customer_id,
                    "plan_variation_id": catalog_id,
                    "card_id": card_id,
                    "start_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                },
            )
            
            if response.status_code != 200:
                logger.error(f"Square create subscription failed: {response.text}")
                raise SquareError(f"Failed to create subscription: {response.text}")
            
            data = response.json()
            square_subscription_id = data["subscription"]["id"]
        
        # Create local subscription record
        limits = PLAN_LIMITS[plan]
        subscription = Subscription(
            id=uuid4(),
            organization_id=organization.id,
            plan=plan.value,
            status=SubscriptionStatus.ACTIVE,
            square_subscription_id=square_subscription_id,
            api_calls_limit=limits.api_calls_per_month,
            api_calls_used=0,
            current_period_start=datetime.now(timezone.utc),
        )
        
        self.db.add(subscription)
        await self.db.commit()
        await self.db.refresh(subscription)
        
        # Issue license for the new subscription
        if self._license_bridge:
            try:
                await self._license_bridge.on_subscription_created(
                    org_id=organization.id,
                    org_name=organization.name,
                    square_plan=plan.value,
                )
            except Exception:
                logger.exception("Failed to issue license for org %s", organization.id)
        
        logger.info(f"Created subscription {subscription.id} for org {organization.slug}")
        return subscription
    
    async def cancel_subscription(
        self,
        subscription: Subscription,
        immediately: bool = False,
    ) -> None:
        """
        Cancel a subscription.
        
        Args:
            subscription: The subscription to cancel
            immediately: If True, cancel immediately; otherwise, cancel at period end
        """
        client = await self._get_client()
        
        if subscription.square_subscription_id:
            if immediately:
                # Cancel immediately
                response = await client.post(
                    f"/subscriptions/{subscription.square_subscription_id}/cancel",
                    json={"idempotency_key": str(uuid4())},
                )
            else:
                # Pause subscription (Square doesn't have cancel-at-period-end)
                response = await client.post(
                    f"/subscriptions/{subscription.square_subscription_id}/pause",
                    json={
                        "idempotency_key": str(uuid4()),
                        "pause_effective_date": subscription.current_period_end.strftime("%Y-%m-%d") if subscription.current_period_end else None,
                    },
                )
            
            if response.status_code not in (200, 404):
                logger.error(f"Square cancel subscription failed: {response.text}")
                raise SquareError(f"Failed to cancel subscription: {response.text}")
        
        subscription.status = SubscriptionStatus.CANCELED if immediately else SubscriptionStatus.PAST_DUE
        await self.db.commit()
        
        # Revoke licenses on immediate cancellation
        if immediately and self._license_bridge:
            try:
                await self._license_bridge.on_subscription_canceled(
                    org_id=subscription.organization_id,
                    reason="Subscription canceled",
                )
            except Exception:
                logger.exception("Failed to revoke licenses for subscription %s", subscription.id)
        
        logger.info(f"Canceled subscription {subscription.id}")
    
    async def upgrade_subscription(
        self,
        subscription: Subscription,
        new_plan: SquarePlan,
    ) -> Subscription:
        """
        Upgrade or downgrade a subscription to a new plan.
        
        Prorated billing is handled by Square.
        """
        client = await self._get_client()
        
        catalog_id = self._plan_catalog_ids.get(new_plan)
        if not catalog_id and new_plan != SquarePlan.SANDBOX:
            raise SquareError(f"No catalog ID configured for plan: {new_plan}")
        
        if subscription.square_subscription_id and catalog_id:
            # Swap subscription plan in Square
            response = await client.post(
                f"/subscriptions/{subscription.square_subscription_id}/swap-plan",
                json={
                    "new_plan_variation_id": catalog_id,
                },
            )
            
            if response.status_code != 200:
                logger.error(f"Square swap plan failed: {response.text}")
                raise SquareError(f"Failed to upgrade subscription: {response.text}")
        
        # Update local limits
        limits = PLAN_LIMITS[new_plan]
        subscription.plan = new_plan.value
        subscription.api_calls_limit = limits.api_calls_per_month
        await self.db.commit()
        
        # Reissue license with new tier entitlements
        if self._license_bridge:
            try:
                org = await self.db.get(Organization, subscription.organization_id)
                if org:
                    await self._license_bridge.on_subscription_upgraded(
                        org_id=org.id,
                        org_name=org.name,
                        new_square_plan=new_plan.value,
                    )
            except Exception:
                logger.exception("Failed to reissue license for subscription %s", subscription.id)
        
        logger.info(f"Upgraded subscription {subscription.id} to {new_plan.value}")
        return subscription
    
    async def record_api_usage(
        self,
        subscription: Subscription,
        endpoint: str,
        count: int = 1,
    ) -> bool:
        """
        Record API usage for a subscription.
        
        Returns True if within limits, False if limit exceeded.
        """
        # Check limits (-1 means unlimited)
        if subscription.api_calls_limit != -1:
            if subscription.api_calls_used + count > subscription.api_calls_limit:
                logger.warning(f"API limit exceeded for subscription {subscription.id}")
                return False
        
        # Update usage counter
        subscription.api_calls_used += count
        
        # Record detailed usage
        usage = UsageRecord(
            id=uuid4(),
            subscription_id=subscription.id,
            endpoint=endpoint,
            count=count,
            recorded_at=datetime.now(timezone.utc),
        )
        self.db.add(usage)
        await self.db.commit()
        
        return True
    
    async def get_usage_summary(
        self,
        subscription: Subscription,
    ) -> dict[str, Any]:
        """Get usage summary for a subscription."""
        limits = PLAN_LIMITS.get(SquarePlan(subscription.plan))
        
        return {
            "plan": subscription.plan,
            "api_calls": {
                "used": subscription.api_calls_used,
                "limit": subscription.api_calls_limit,
                "remaining": (
                    subscription.api_calls_limit - subscription.api_calls_used
                    if subscription.api_calls_limit != -1
                    else -1
                ),
            },
            "limits": {
                "webhook_endpoints": limits.webhook_endpoints if limits else -1,
                "api_keys": limits.api_keys if limits else -1,
                "ip_allowlist_entries": limits.ip_allowlist_entries if limits else -1,
            },
            "features": {
                "priority_support": limits.priority_support if limits else False,
                "custom_branding": limits.custom_branding if limits else False,
            },
            "period_start": subscription.current_period_start.isoformat() if subscription.current_period_start else None,
            "period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        }
    
    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        webhook_url: str,
    ) -> bool:
        """
        Verify Square webhook signature.
        
        Args:
            payload: Raw request body
            signature: X-Square-Hmacsha256-Signature header
            webhook_url: The notification URL configured in Square
            
        Returns:
            True if signature is valid
        """
        # Square signature = base64(hmac-sha256(webhook_url + body))
        message = webhook_url.encode() + payload
        expected = hmac.new(
            self.config.webhook_signature_key.encode(),
            message,
            hashlib.sha256,
        ).digest()
        
        import base64
        expected_b64 = base64.b64encode(expected).decode()
        
        return hmac.compare_digest(expected_b64, signature)
    
    async def handle_webhook(
        self,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """
        Handle Square webhook events.
        
        Supported events:
        - subscription.created
        - subscription.updated
        - subscription.canceled
        - invoice.payment_made
        - invoice.payment_failed
        """
        logger.info(f"Processing Square webhook: {event_type}")
        
        if event_type == "subscription.created":
            await self._handle_subscription_created(data)
        elif event_type == "subscription.updated":
            await self._handle_subscription_updated(data)
        elif event_type == "subscription.canceled":
            await self._handle_subscription_canceled(data)
        elif event_type == "invoice.payment_made":
            await self._handle_payment_success(data)
        elif event_type == "invoice.payment_failed":
            await self._handle_payment_failed(data)
        else:
            logger.debug(f"Ignoring webhook event: {event_type}")
    
    async def _handle_subscription_created(self, data: dict[str, Any]) -> None:
        """Handle subscription.created webhook."""
        # Usually already handled by create_subscription.
        # If the subscription was created externally (e.g. Square dashboard),
        # ensure a license exists.
        subscription_data = data.get("subscription", {})
        square_id = subscription_data.get("id")
        if not square_id or not self._license_bridge:
            return

        result = await self.db.execute(
            select(Subscription).where(Subscription.square_subscription_id == square_id)
        )
        subscription = result.scalar_one_or_none()
        if not subscription:
            return

        # Check if org already has a license
        existing = await self._license_bridge._issuer.get_org_license(
            subscription.organization_id
        )
        if existing:
            return  # Already issued

        org = await self.db.get(Organization, subscription.organization_id)
        if org:
            try:
                await self._license_bridge.on_subscription_created(
                    org_id=org.id,
                    org_name=org.name,
                    square_plan=subscription.plan,
                )
            except Exception:
                logger.exception(
                    "Failed to issue license from webhook for org %s", org.id
                )
    
    async def _handle_subscription_updated(self, data: dict[str, Any]) -> None:
        """Handle subscription.updated webhook."""
        subscription_data = data.get("subscription", {})
        square_id = subscription_data.get("id")
        
        if not square_id:
            return
        
        # Find local subscription
        result = await self.db.execute(
            select(Subscription).where(Subscription.square_subscription_id == square_id)
        )
        subscription = result.scalar_one_or_none()
        
        if subscription:
            # Update status based on Square status
            square_status = subscription_data.get("status", "").upper()
            if square_status == "ACTIVE":
                subscription.status = SubscriptionStatus.ACTIVE
            elif square_status == "PAUSED":
                subscription.status = SubscriptionStatus.PAST_DUE
            elif square_status == "CANCELED":
                subscription.status = SubscriptionStatus.CANCELED
            
            await self.db.commit()
    
    async def _handle_subscription_canceled(self, data: dict[str, Any]) -> None:
        """Handle subscription.canceled webhook."""
        subscription_data = data.get("subscription", {})
        square_id = subscription_data.get("id")
        
        if not square_id:
            return
        
        result = await self.db.execute(
            select(Subscription).where(Subscription.square_subscription_id == square_id)
        )
        subscription = result.scalar_one_or_none()
        
        if subscription:
            subscription.status = SubscriptionStatus.CANCELED
            await self.db.commit()

            if self._license_bridge:
                try:
                    await self._license_bridge.on_subscription_canceled(
                        org_id=subscription.organization_id,
                        reason="Subscription canceled via webhook",
                    )
                except Exception:
                    logger.exception(
                        "Failed to revoke licenses from webhook for org %s",
                        subscription.organization_id,
                    )
    
    async def _handle_payment_success(self, data: dict[str, Any]) -> None:
        """Handle invoice.payment_made webhook."""
        invoice = data.get("invoice", {})
        subscription_id = invoice.get("subscription_id")
        
        if not subscription_id:
            return
        
        result = await self.db.execute(
            select(Subscription).where(Subscription.square_subscription_id == subscription_id)
        )
        subscription = result.scalar_one_or_none()
        
        if subscription:
            # Reset usage counters for new billing period
            subscription.api_calls_used = 0
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.current_period_start = datetime.now(timezone.utc)
            await self.db.commit()

            # Refresh license for the new billing period
            if self._license_bridge:
                try:
                    org = await self.db.get(Organization, subscription.organization_id)
                    if org:
                        await self._license_bridge.on_payment_success(
                            org_id=org.id,
                            org_name=org.name,
                            square_plan=subscription.plan,
                        )
                except Exception:
                    logger.exception(
                        "Failed to refresh license from payment webhook for org %s",
                        subscription.organization_id,
                    )
            
            logger.info(f"Payment received for subscription {subscription.id}")
    
    async def _handle_payment_failed(self, data: dict[str, Any]) -> None:
        """Handle invoice.payment_failed webhook."""
        invoice = data.get("invoice", {})
        subscription_id = invoice.get("subscription_id")
        
        if not subscription_id:
            return
        
        result = await self.db.execute(
            select(Subscription).where(Subscription.square_subscription_id == subscription_id)
        )
        subscription = result.scalar_one_or_none()
        
        if subscription:
            subscription.status = SubscriptionStatus.PAST_DUE
            await self.db.commit()

            # Don't revoke — license grace period handles the gap
            if self._license_bridge:
                try:
                    await self._license_bridge.on_payment_failed(
                        org_id=subscription.organization_id,
                    )
                except Exception:
                    logger.exception(
                        "Failed to handle payment failure for org %s",
                        subscription.organization_id,
                    )
            
            logger.warning(f"Payment failed for subscription {subscription.id}")


class SquareError(Exception):
    """Square API error."""
    pass
