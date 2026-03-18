"""
Webhook Service

Application service for Webhook CRUD.
"""

from __future__ import annotations

import logging

from digital_identity.domain.entities import Webhook

logger = logging.getLogger(__name__)


class WebhookService:
    """Service for Webhook management."""

    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(
        self,
        organization_id: str,
        name: str,
        endpoint_url: str,
        events: list[str],
        description: str | None = None,
        enabled: bool = True,
        api_version: str | None = None,
        filter: dict | None = None,
        delivery_config: dict | None = None,
        signing_secret_hash: str | None = None,
        signing_secret_masked: str | None = None,
    ) -> Webhook:
        """Create a new Webhook."""
        webhook = Webhook(
            organization_id=organization_id,
            name=name,
            description=description,
            endpoint_url=endpoint_url,
            events=events,
            signing_secret_hash=signing_secret_hash,
            signing_secret_masked=signing_secret_masked,
            enabled=enabled,
            api_version=api_version,
            filter=filter or {},
            delivery_config=delivery_config or {},
        )
        saved = await self._repository.save(webhook)
        logger.info(f"Created Webhook: {saved.id} ({saved.name})")
        return saved

    async def get(self, webhook_id: str) -> Webhook | None:
        return await self._repository.get(webhook_id)

    async def list(
        self,
        organization_id: str,
        skip: int = 0,
        limit: int = 100,
        enabled: bool | None = None,
    ) -> list[Webhook]:
        return await self._repository.list(
            organization_id=organization_id, skip=skip, limit=limit, enabled=enabled,
        )

    async def update(self, webhook_id: str, **kwargs) -> Webhook | None:
        webhook = await self._repository.get(webhook_id)
        if not webhook:
            return None

        for attr in (
            "name", "description", "endpoint_url", "events", "enabled",
            "api_version", "filter", "delivery_config", "status",
            "signing_secret_hash", "signing_secret_masked",
        ):
            if attr in kwargs:
                setattr(webhook, attr, kwargs[attr])

        webhook.touch()
        return await self._repository.save(webhook)

    async def delete(self, webhook_id: str) -> bool:
        return await self._repository.delete(webhook_id)
