"""Notification Payload Service — manage notification events."""
from __future__ import annotations
import logging
from digital_identity.domain.entities import NotificationPayload

logger = logging.getLogger(__name__)

class NotificationPayloadService:
    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(self, event_type: str, subscription_id: str,
                     payload: dict | None = None, **kwargs) -> NotificationPayload:
        notification = NotificationPayload(event_type=event_type,
                                           correlation_id=subscription_id,
                                           data=payload or {}, **kwargs)
        saved = await self._repository.save(notification)
        logger.info(f"Created NotificationPayload: {saved.id} ({saved.event_type})")
        return saved

    async def get(self, notification_id: str) -> NotificationPayload | None:
        return await self._repository.get(notification_id)

    async def list(self, event_type: str | None = None,
                   skip: int = 0, limit: int = 100) -> list[NotificationPayload]:
        return await self._repository.list(event_type=event_type, skip=skip, limit=limit)

    async def update(self, notification_id: str, **kwargs) -> NotificationPayload | None:
        notification = await self._repository.get(notification_id)
        if not notification:
            return None
        for attr in ("status", "delivery_attempts", "last_attempt_at",
                     "delivered_at", "error_message"):
            if attr in kwargs:
                setattr(notification, attr, kwargs[attr])
        notification.touch()
        return await self._repository.save(notification)

    async def delete(self, notification_id: str) -> bool:
        return await self._repository.delete(notification_id)
