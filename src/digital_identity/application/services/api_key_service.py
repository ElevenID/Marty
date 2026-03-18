"""
API Key Service

Application service for API Key CRUD.
"""

from __future__ import annotations

import logging

from digital_identity.domain.entities import ApiKey

logger = logging.getLogger(__name__)


class ApiKeyService:
    """Service for API Key management."""

    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(
        self,
        organization_id: str,
        name: str,
        key_prefix: str,
        scope_type: str,
        scopes: list[str],
        description: str | None = None,
        key_hash: str | None = None,
        deployment_profile_id: str | None = None,
        enabled: bool = True,
        expires_at=None,
    ) -> ApiKey:
        """Create a new API Key."""
        if scope_type == "DEPLOYMENT" and not deployment_profile_id:
            raise ValueError("deployment_profile_id is required when scope_type is DEPLOYMENT")
        if scope_type == "ORGANIZATION" and deployment_profile_id:
            raise ValueError("deployment_profile_id must be null when scope_type is ORGANIZATION")

        api_key = ApiKey(
            organization_id=organization_id,
            name=name,
            description=description,
            key_prefix=key_prefix,
            key_hash=key_hash,
            scope_type=scope_type,
            deployment_profile_id=deployment_profile_id,
            scopes=scopes,
            enabled=enabled,
            expires_at=expires_at,
        )
        saved = await self._repository.save(api_key)
        logger.info(f"Created ApiKey: {saved.id} (prefix={saved.key_prefix})")
        return saved

    async def get(self, key_id: str) -> ApiKey | None:
        return await self._repository.get(key_id)

    async def get_by_prefix(self, key_prefix: str) -> ApiKey | None:
        return await self._repository.get_by_prefix(key_prefix)

    async def list(
        self,
        organization_id: str,
        skip: int = 0,
        limit: int = 100,
        enabled: bool | None = None,
        scope_type: str | None = None,
    ) -> list[ApiKey]:
        return await self._repository.list(
            organization_id=organization_id,
            skip=skip,
            limit=limit,
            enabled=enabled,
            scope_type=scope_type,
        )

    async def update(self, key_id: str, **kwargs) -> ApiKey | None:
        api_key = await self._repository.get(key_id)
        if not api_key:
            return None

        for attr in (
            "name", "description", "scopes", "enabled",
            "scope_type", "deployment_profile_id",
        ):
            if attr in kwargs:
                setattr(api_key, attr, kwargs[attr])

        # Re-validate scope_type / deployment_profile_id after update
        if api_key.scope_type == "DEPLOYMENT" and not api_key.deployment_profile_id:
            raise ValueError("deployment_profile_id is required when scope_type is DEPLOYMENT")
        if api_key.scope_type == "ORGANIZATION" and api_key.deployment_profile_id:
            raise ValueError("deployment_profile_id must be null when scope_type is ORGANIZATION")

        api_key.touch()
        return await self._repository.save(api_key)

    async def delete(self, key_id: str) -> bool:
        return await self._repository.delete(key_id)
