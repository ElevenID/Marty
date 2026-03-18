"""
Compliance Profile Service

Application service for ComplianceProfile CRUD.
System profiles (is_system=True) are read-only via the API.
"""

from __future__ import annotations

import logging
from typing import Any

from digital_identity.domain.entities import ComplianceProfile
from digital_identity.domain.value_objects import CredentialFormat

logger = logging.getLogger(__name__)


class ComplianceProfileService:
    """Service for Compliance Profile management."""

    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(
        self,
        name: str,
        compliance_code: str,
        credential_format: str = "SD_JWT_VC",
        organization_id: str | None = None,
        description: str | None = None,
        issuance_protocol: str | None = None,
        trust_profile_constraints: dict[str, Any] | None = None,
        discoverable: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> ComplianceProfile:
        """Create a custom (non-system) Compliance Profile."""
        existing = await self._repository.get_by_code(compliance_code)
        if existing:
            raise ValueError(f"Compliance profile with code '{compliance_code}' already exists")

        profile = ComplianceProfile(
            name=name,
            compliance_code=compliance_code,
            credential_format=CredentialFormat(credential_format),
            organization_id=organization_id,
            description=description,
            issuance_protocol=issuance_protocol,
            trust_profile_constraints=trust_profile_constraints or {},
            is_system=False,
            discoverable=discoverable,
            metadata=metadata or {},
        )
        saved = await self._repository.save(profile)
        logger.info(f"Created Compliance Profile: {saved.id} ({saved.compliance_code})")
        return saved

    async def get(self, profile_id: str) -> ComplianceProfile | None:
        """Get a Compliance Profile by ID."""
        return await self._repository.get(profile_id)

    async def get_by_code(self, compliance_code: str) -> ComplianceProfile | None:
        """Get a Compliance Profile by its compliance_code."""
        return await self._repository.get_by_code(compliance_code)

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        organization_id: str | None = None,
        is_system: bool | None = None,
        discoverable_only: bool = False,
    ) -> list[ComplianceProfile]:
        """List Compliance Profiles with optional filters."""
        return await self._repository.list(
            skip=skip,
            limit=limit,
            organization_id=organization_id,
            is_system=is_system,
            discoverable_only=discoverable_only,
        )

    async def update(
        self,
        profile_id: str,
        **updates: Any,
    ) -> ComplianceProfile | None:
        """Update a custom Compliance Profile (system profiles are immutable)."""
        profile = await self._repository.get(profile_id)
        if not profile:
            return None
        if profile.is_system:
            raise ValueError("System compliance profiles cannot be modified via the API")

        for key, value in updates.items():
            if value is None:
                continue
            if key == "credential_format":
                setattr(profile, key, CredentialFormat(value))
            elif key == "is_system":
                continue  # never allow escalation to system
            elif hasattr(profile, key):
                setattr(profile, key, value)

        profile.touch()
        saved = await self._repository.save(profile)
        logger.info(f"Updated Compliance Profile: {profile_id}")
        return saved

    async def delete(self, profile_id: str) -> bool:
        """Delete a custom Compliance Profile (system profiles cannot be deleted)."""
        profile = await self._repository.get(profile_id)
        if not profile:
            return False
        if profile.is_system:
            raise ValueError("System compliance profiles cannot be deleted")
        result = await self._repository.delete(profile_id)
        logger.info(f"Deleted Compliance Profile: {profile_id}")
        return result
