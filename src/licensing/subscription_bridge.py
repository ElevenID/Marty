"""
Subscription ↔ License Bridge

Connects subscription lifecycle events to license issuance/revocation
and registry credential management.
Called by SquareService at key lifecycle points.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .keys import LicenseKeyManager
from .service import (
    DEFAULT_ENTITLEMENTS,
    SQUARE_PLAN_TO_TIER,
    IssuedLicense,
    LicenseIssuerService,
    LicenseRequest,
)

if TYPE_CHECKING:
    from .registry import RegistryGatingService

logger = logging.getLogger(__name__)


class SubscriptionLicenseBridge:
    """
    Bridges subscription events to license lifecycle.

    Usage:
        bridge = SubscriptionLicenseBridge(db, key_manager)
        license = await bridge.on_subscription_created(org_id, org_name, "starter")
        await bridge.on_subscription_canceled(org_id)
    """

    def __init__(
        self,
        db: AsyncSession,
        key_manager: LicenseKeyManager,
        registry_service: Optional["RegistryGatingService"] = None,
        registry_prefix: str = "",
    ):
        self._issuer = LicenseIssuerService(db, key_manager)
        self._registry = registry_service
        self._registry_prefix = registry_prefix

    async def on_subscription_created(
        self,
        org_id: UUID,
        org_name: str,
        square_plan: str,
        *,
        entitled_products: list[str] | None = None,
        features: list[str] | None = None,
        duration_days: int = 365,
    ) -> IssuedLicense:
        """
        Issue a license when a new subscription is created.

        Maps the Square plan name to a canonical tier and mints a JWT
        with the appropriate entitlements.
        """
        tier = SQUARE_PLAN_TO_TIER.get(square_plan, square_plan)
        defaults = DEFAULT_ENTITLEMENTS.get(tier, {})

        request = LicenseRequest(
            org_id=org_id,
            org_name=org_name,
            plan_tier=tier,
            entitled_products=entitled_products or defaults.get("entitled_products"),
            features=features or defaults.get("features"),
            max_instances=defaults.get("max_instances"),
            registry_access=defaults.get("registry_access"),
            api_calls_limit=defaults.get("api_calls_limit"),
            grace_period_days=defaults.get("grace_period_days"),
            duration_days=duration_days,
        )

        issued = await self._issuer.issue_license(request)
        logger.info(
            "Issued license %s for org %s (plan=%s, tier=%s)",
            issued.license_jti,
            org_id,
            square_plan,
            tier,
        )

        # Issue registry credentials if entitled
        if self._registry and defaults.get("registry_access"):
            try:
                await self._registry.issue_credentials(
                    org_id=org_id,
                    license_jti=issued.license_jti,
                    entitled_products=issued.entitled_products,
                    registry_prefix=self._registry_prefix,
                )
            except Exception:
                logger.exception(
                    "Failed to issue registry credentials for org %s", org_id,
                )

        return issued

    async def on_subscription_upgraded(
        self,
        org_id: UUID,
        org_name: str,
        new_square_plan: str,
    ) -> IssuedLicense:
        """
        Reissue license when a subscription plan changes.

        The old license is automatically superseded by LicenseIssuerService.
        """
        tier = SQUARE_PLAN_TO_TIER.get(new_square_plan, new_square_plan)
        defaults = DEFAULT_ENTITLEMENTS.get(tier, {})

        request = LicenseRequest(
            org_id=org_id,
            org_name=org_name,
            plan_tier=tier,
            entitled_products=defaults.get("entitled_products"),
            features=defaults.get("features"),
            max_instances=defaults.get("max_instances"),
            registry_access=defaults.get("registry_access"),
            api_calls_limit=defaults.get("api_calls_limit"),
            grace_period_days=defaults.get("grace_period_days"),
        )

        issued = await self._issuer.issue_license(request)
        logger.info(
            "Reissued license %s for org %s (new tier=%s)",
            issued.license_jti,
            org_id,
            tier,
        )

        # Reissue registry credentials with new image scope
        if self._registry and defaults.get("registry_access"):
            try:
                await self._registry.issue_credentials(
                    org_id=org_id,
                    license_jti=issued.license_jti,
                    entitled_products=issued.entitled_products,
                    registry_prefix=self._registry_prefix,
                )
            except Exception:
                logger.exception(
                    "Failed to reissue registry credentials for org %s", org_id,
                )

        return issued

    async def on_subscription_canceled(
        self,
        org_id: UUID,
        reason: str = "Subscription canceled",
    ) -> int:
        """
        Revoke all licenses when a subscription is canceled.

        Returns the number of licenses revoked.
        """
        count = await self._issuer.revoke_org_licenses(org_id, reason)
        logger.info("Revoked %d license(s) for org %s: %s", count, org_id, reason)

        # Revoke registry credentials
        if self._registry:
            try:
                await self._registry.revoke_org_credentials(org_id, reason)
            except Exception:
                logger.exception(
                    "Failed to revoke registry credentials for org %s", org_id,
                )

        return count

    async def on_payment_success(
        self,
        org_id: UUID,
        org_name: str,
        square_plan: str,
    ) -> Optional[IssuedLicense]:
        """
        Refresh license on successful payment (new billing cycle).

        Only reissues if the org currently has an active license.
        """
        existing = await self._issuer.get_org_license(org_id)
        if existing is None:
            logger.debug("No active license for org %s, skipping refresh", org_id)
            return None

        return await self.on_subscription_created(org_id, org_name, square_plan)

    async def on_payment_failed(
        self,
        org_id: UUID,
    ) -> None:
        """
        Handle payment failure.

        We don't revoke immediately — the license's built-in grace period
        handles the gap. Log for monitoring.
        """
        logger.warning(
            "Payment failed for org %s. License grace period applies.",
            org_id,
        )
