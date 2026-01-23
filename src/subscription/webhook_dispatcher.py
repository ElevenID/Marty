"""
Webhook Dispatcher Service

Handles dispatching events to registered webhook endpoints with:
- HMAC signature generation
- Retry logic with exponential backoff
- Circuit breaker pattern
- Delivery attempt logging
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

import httpx
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import WebhookDeliveryAttempt, WebhookEndpoint

logger = logging.getLogger(__name__)


class WebhookDispatcher:
    """Service for dispatching webhook events."""

    def __init__(
        self,
        db: AsyncSession,
        timeout: float = 10.0,
        max_retries: int = 3,
        circuit_breaker_threshold: int = 5,
    ):
        """
        Initialize webhook dispatcher.

        Args:
            db: Database session
            timeout: HTTP request timeout in seconds
            max_retries: Maximum number of retry attempts
            circuit_breaker_threshold: Number of consecutive failures before opening circuit
        """
        self.db = db
        self.timeout = timeout
        self.max_retries = max_retries
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.client = httpx.AsyncClient(timeout=timeout)

    async def dispatch_event(
        self,
        organization_id: UUID,
        event_type: str,
        event_data: dict[str, Any],
        event_id: Optional[str] = None,
    ) -> None:
        """
        Dispatch an event to all registered webhooks for an organization.

        Args:
            organization_id: Organization ID
            event_type: Type of event (e.g., 'credential.issued')
            event_data: Event payload data
            event_id: Optional event ID for idempotency
        """
        if event_id is None:
            event_id = str(uuid4())

        # Get all active webhooks for this organization that subscribe to this event
        result = await self.db.execute(
            select(WebhookEndpoint).where(
                and_(
                    WebhookEndpoint.organization_id == organization_id,
                    WebhookEndpoint.enabled == True,
                    WebhookEndpoint.circuit_breaker_open_until == None,
                )
            )
        )
        webhooks = result.scalars().all()

        # Filter webhooks that subscribe to this event type
        matching_webhooks = [
            webhook
            for webhook in webhooks
            if self._webhook_matches_event(webhook, event_type)
        ]

        if not matching_webhooks:
            logger.debug(
                f"No webhooks registered for event {event_type} in org {organization_id}"
            )
            return

        # Dispatch to all matching webhooks concurrently
        tasks = [
            self._dispatch_to_webhook(webhook, event_type, event_data, event_id)
            for webhook in matching_webhooks
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    def _webhook_matches_event(self, webhook: WebhookEndpoint, event_type: str) -> bool:
        """Check if webhook subscribes to this event type."""
        if not webhook.event_types:
            return False

        # Wildcard subscription
        if "*" in webhook.event_types:
            return True

        # Exact match
        if event_type in webhook.event_types:
            return True

        # Category match (e.g., 'credential.*' matches 'credential.issued')
        event_category = event_type.split(".")[0] if "." in event_type else event_type
        for subscribed_type in webhook.event_types:
            if subscribed_type.endswith(".*"):
                subscribed_category = subscribed_type[:-2]
                if event_category == subscribed_category:
                    return True

        return False

    async def _dispatch_to_webhook(
        self,
        webhook: WebhookEndpoint,
        event_type: str,
        event_data: dict[str, Any],
        event_id: str,
    ) -> None:
        """
        Dispatch event to a single webhook with retry logic.

        Args:
            webhook: Webhook endpoint
            event_type: Event type
            event_data: Event payload
            event_id: Event ID
        """
        payload = {
            "id": event_id,
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": event_data,
        }

        retry_count = 0
        success = False
        last_error = None
        response_status_code = None
        response_body = None
        start_time = datetime.now(timezone.utc)

        while retry_count <= self.max_retries and not success:
            try:
                # Generate HMAC signature
                signature = self._generate_signature(webhook.secret, payload)

                # Send request
                response = await self.client.post(
                    webhook.url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": signature,
                        "X-Webhook-Event": event_type,
                        "X-Webhook-ID": event_id,
                    },
                )

                response_status_code = response.status_code
                response_body = response.text[:1000]  # Truncate to 1000 chars

                # Consider 2xx status codes as success
                if 200 <= response.status_code < 300:
                    success = True
                    # Reset failure count on success
                    webhook.failure_count = 0
                    webhook.last_triggered_at = datetime.now(timezone.utc)
                else:
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Webhook delivery failed to {webhook.url}: {e}",
                    exc_info=True,
                )

            if not success and retry_count < self.max_retries:
                # Exponential backoff: 1s, 2s, 4s
                await asyncio.sleep(2**retry_count)
                retry_count += 1

        end_time = datetime.now(timezone.utc)
        response_time_ms = int((end_time - start_time).total_seconds() * 1000)

        # Update webhook failure tracking
        if not success:
            webhook.failure_count += 1
            if webhook.failure_count >= self.circuit_breaker_threshold:
                # Open circuit breaker for 1 hour
                webhook.circuit_breaker_open_until = datetime.now(
                    timezone.utc
                ).timestamp() + 3600
                logger.error(
                    f"Circuit breaker opened for webhook {webhook.id} after {webhook.failure_count} failures"
                )

        # Log delivery attempt
        attempt = WebhookDeliveryAttempt(
            id=uuid4(),
            webhook_id=webhook.id,
            event_id=event_id,
            event_type=event_type,
            success=success,
            response_status_code=response_status_code,
            response_body=response_body,
            error_message=last_error if not success else None,
            retry_count=retry_count,
            response_time_ms=response_time_ms,
            created_at=datetime.now(timezone.utc),
        )

        self.db.add(attempt)
        await self.db.commit()

        if success:
            logger.info(
                f"Webhook delivered successfully to {webhook.url} for event {event_type}"
            )
        else:
            logger.error(
                f"Webhook delivery failed to {webhook.url} for event {event_type} after {retry_count} retries: {last_error}"
            )

    def _generate_signature(self, secret: str, payload: dict[str, Any]) -> str:
        """
        Generate HMAC-SHA256 signature for webhook payload.

        Args:
            secret: Webhook secret
            payload: Event payload

        Returns:
            Hex-encoded HMAC signature
        """
        payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
        signature = hmac.new(
            secret.encode("utf-8"), payload_bytes, hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()


async def dispatch_webhook_event(
    db: AsyncSession,
    organization_id: UUID,
    event_type: str,
    event_data: dict[str, Any],
    event_id: Optional[str] = None,
) -> None:
    """
    Convenience function to dispatch a webhook event.

    Args:
        db: Database session
        organization_id: Organization ID
        event_type: Event type (e.g., 'credential.issued')
        event_data: Event payload
        event_id: Optional event ID
    """
    dispatcher = WebhookDispatcher(db)
    try:
        await dispatcher.dispatch_event(organization_id, event_type, event_data, event_id)
    finally:
        await dispatcher.close()
