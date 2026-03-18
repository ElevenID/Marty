"""
Subscription Service

Application service for Subscription CRUD.
"""

from __future__ import annotations

import logging

from digital_identity.domain.entities import Subscription

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Service for Subscription management."""

    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(
        self,
        organization_id: str,
        name: str,
        event_types: list[str],
        delivery: dict,
        description: str | None = None,
        filter: dict | None = None,
        enabled: bool = True,
        retry_policy: dict | None = None,
    ) -> Subscription:
        """Create a new Subscription."""
        sub = Subscription(
            organization_id=organization_id,
            name=name,
            description=description,
            event_types=event_types,
            delivery=delivery,
            filter=filter or {},
            enabled=enabled,
            retry_policy=retry_policy or {},
        )
        saved = await self._repository.save(sub)
        logger.info(f"Created Subscription: {saved.id} ({saved.name})")
        return saved

    async def get(self, sub_id: str) -> Subscription | None:
        return await self._repository.get(sub_id)

    async def list(
        self,
        organization_id: str,
        skip: int = 0,
        limit: int = 100,
        enabled: bool | None = None,
    ) -> list[Subscription]:
        return await self._repository.list(
            organization_id=organization_id, skip=skip, limit=limit, enabled=enabled,
        )

    async def update(self, sub_id: str, **kwargs) -> Subscription | None:
        sub = await self._repository.get(sub_id)
        if not sub:
            return None

        for attr in (
            "name", "description", "event_types", "delivery",
            "filter", "enabled", "retry_policy",
        ):
            if attr in kwargs:
                setattr(sub, attr, kwargs[attr])

        sub.touch()
        return await self._repository.save(sub)

    async def delete(self, sub_id: str) -> bool:
        return await self._repository.delete(sub_id)
