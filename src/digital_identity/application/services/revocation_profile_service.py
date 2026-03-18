"""
Revocation Profile Service

Application service for RevocationProfile CRUD.
"""

from __future__ import annotations

import logging
from typing import Any

from digital_identity.domain.entities import RevocationProfile
from digital_identity.domain.value_objects import RevocationTimingMode

logger = logging.getLogger(__name__)


class RevocationProfileService:
    """Service for Revocation Profile management."""

    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(
        self,
        organization_id: str,
        name: str,
        revocation_mechanism: list[str],
        check_mode: str = "ALWAYS",
        mechanism_priority: list[str] | None = None,
        cache_ttl_seconds: int | None = None,
        offline_grace_seconds: int | None = None,
        issuer_config: dict[str, Any] | None = None,
        status_list_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RevocationProfile:
        """Create a new Revocation Profile."""
        profile = RevocationProfile(
            organization_id=organization_id,
            name=name,
            revocation_mechanism=revocation_mechanism,
            mechanism_priority=mechanism_priority or [],
            check_mode=RevocationTimingMode(check_mode),
            cache_ttl_seconds=cache_ttl_seconds,
            offline_grace_seconds=offline_grace_seconds,
            issuer_config=issuer_config or {},
            status_list_url=status_list_url,
            metadata=metadata or {},
        )

        saved = await self._repository.save(profile)
        logger.info(f"Created Revocation Profile: {saved.id} ({saved.name})")
        return saved

    async def get(self, profile_id: str) -> RevocationProfile | None:
        """Get a Revocation Profile by ID."""
        return await self._repository.get(profile_id)

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        organization_id: str | None = None,
    ) -> list[RevocationProfile]:
        """List Revocation Profiles with optional filters."""
        return await self._repository.list(
            skip=skip, limit=limit, organization_id=organization_id,
        )

    async def update(
        self,
        profile_id: str,
        **updates: Any,
    ) -> RevocationProfile | None:
        """Update a Revocation Profile."""
        profile = await self._repository.get(profile_id)
        if not profile:
            return None

        for key, value in updates.items():
            if value is None:
                continue
            if key == "check_mode":
                setattr(profile, key, RevocationTimingMode(value))
            elif hasattr(profile, key):
                setattr(profile, key, value)

        profile.touch()
        saved = await self._repository.save(profile)
        logger.info(f"Updated Revocation Profile: {profile_id}")
        return saved

    async def delete(self, profile_id: str) -> bool:
        """Delete a Revocation Profile."""
        if not await self._repository.exists(profile_id):
            return False
        result = await self._repository.delete(profile_id)
        logger.info(f"Deleted Revocation Profile: {profile_id}")
        return result
