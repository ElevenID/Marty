"""Device Registration Service — device record management."""
from __future__ import annotations
import logging
from digital_identity.domain.entities import DeviceRegistration

logger = logging.getLogger(__name__)

class DeviceRegistrationService:
    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(self, user_id: str, device_id: str, platform: str,
                     fcm_token: str, **kwargs) -> DeviceRegistration:
        existing = await self._repository.get_by_device_id(user_id, device_id)
        if existing:
            raise ValueError(f"Device '{device_id}' already registered for user '{user_id}'")
        dr = DeviceRegistration(user_id=user_id, device_id=device_id,
                                platform=platform, fcm_token=fcm_token, **kwargs)
        saved = await self._repository.save(dr)
        logger.info(f"Created DeviceRegistration: {saved.id}")
        return saved

    async def get(self, reg_id: str) -> DeviceRegistration | None:
        return await self._repository.get(reg_id)

    async def list(self, user_id: str | None = None, is_active: bool | None = None,
                   skip: int = 0, limit: int = 100) -> list[DeviceRegistration]:
        return await self._repository.list(user_id=user_id, is_active=is_active, skip=skip, limit=limit)

    async def update(self, reg_id: str, **kwargs) -> DeviceRegistration | None:
        dr = await self._repository.get(reg_id)
        if not dr:
            return None
        for attr in ("fcm_token", "app_version", "os_version", "device_model",
                     "preferences", "public_key_der", "public_key_kid",
                     "key_valid_from", "key_valid_until", "is_active"):
            if attr in kwargs:
                setattr(dr, attr, kwargs[attr])
        dr.touch()
        return await self._repository.save(dr)

    async def delete(self, reg_id: str) -> bool:
        return await self._repository.delete(reg_id)
