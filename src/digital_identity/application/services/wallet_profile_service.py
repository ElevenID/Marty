"""Wallet Profile Service — wallet compatibility records."""
from __future__ import annotations
import logging
from digital_identity.domain.entities import WalletProfile

logger = logging.getLogger(__name__)

class WalletProfileService:
    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(self, name: str, credential_format: str, issuance_protocol: str,
                     **kwargs) -> WalletProfile:
        wp = WalletProfile(name=name, credential_format=credential_format,
                           issuance_protocol=issuance_protocol, **kwargs)
        saved = await self._repository.save(wp)
        logger.info(f"Created WalletProfile: {saved.id} ({saved.name})")
        return saved

    async def get(self, wp_id: str) -> WalletProfile | None:
        return await self._repository.get(wp_id)

    async def list(self, organization_id: str | None = None, credential_format: str | None = None,
                   skip: int = 0, limit: int = 100) -> list[WalletProfile]:
        return await self._repository.list(organization_id=organization_id,
                                           credential_format=credential_format, skip=skip, limit=limit)

    async def update(self, wp_id: str, **kwargs) -> WalletProfile | None:
        wp = await self._repository.get(wp_id)
        if not wp:
            return None
        for attr in ("name", "description", "is_override", "override_precedence",
                     "credential_format", "issuance_protocol", "compliance_profile_code",
                     "wallet_apps", "merge_strategy", "specifications",
                     "supported_platforms", "deep_link_pattern"):
            if attr in kwargs:
                setattr(wp, attr, kwargs[attr])
        wp.touch()
        return await self._repository.save(wp)

    async def delete(self, wp_id: str) -> bool:
        return await self._repository.delete(wp_id)
