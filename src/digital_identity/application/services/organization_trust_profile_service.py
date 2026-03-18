"""
Organization Trust Profile Service

Application service for OrganizationTrustProfile CRUD.
Links organizations to trust frameworks with policy overrides.
"""

from __future__ import annotations

import logging
from typing import Any

from digital_identity.domain.entities import OrganizationTrustProfile
from digital_identity.domain.value_objects import (
    CryptoAlgorithm,
    CredentialFormat,
    RevocationPolicy,
    TimePolicy,
)

logger = logging.getLogger(__name__)


class OrganizationTrustProfileService:
    """Service for Organization Trust Profile management."""

    def __init__(self, repository, framework_repository=None, event_publisher=None):
        self._repository = repository
        self._framework_repository = framework_repository
        self._event_publisher = event_publisher

    async def create(
        self,
        organization_id: str,
        framework_id: str,
        name: str,
        display_name: str | None = None,
        description: str | None = None,
        enabled: bool = True,
        use_case_tags: list[str] | None = None,
        compliance_status: str = "SETUP_REQUIRED",
        auto_generated: bool = False,
        revocation_policy: dict[str, Any] | None = None,
        time_policy: dict[str, Any] | None = None,
        allowed_algorithms: list[str] | None = None,
        allowed_formats: list[str] | None = None,
        allowed_issuers: list[str] | None = None,
        denied_issuers: list[str] | None = None,
        jurisdiction_filter: list[str] | None = None,
    ) -> OrganizationTrustProfile:
        """Create a new Organization Trust Profile."""
        profile = OrganizationTrustProfile(
            organization_id=organization_id,
            framework_id=framework_id,
            name=name,
            display_name=display_name or name,
            description=description,
            enabled=enabled,
            use_case_tags=use_case_tags or [],
            compliance_status=compliance_status,
            auto_generated=auto_generated,
            revocation_policy=RevocationPolicy(**revocation_policy) if revocation_policy else None,
            time_policy=TimePolicy(**time_policy) if time_policy else None,
            allowed_algorithms=[CryptoAlgorithm(a) for a in allowed_algorithms] if allowed_algorithms else None,
            allowed_formats=[CredentialFormat(f) for f in allowed_formats] if allowed_formats else None,
            allowed_issuers=allowed_issuers,
            denied_issuers=denied_issuers,
            jurisdiction_filter=jurisdiction_filter,
        )

        saved = await self._repository.save(profile)
        logger.info(f"Created Organization Trust Profile: {saved.id} ({saved.name})")
        return saved

    async def get(self, profile_id: str) -> OrganizationTrustProfile | None:
        """Get an Organization Trust Profile by ID."""
        return await self._repository.get(profile_id)

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        organization_id: str | None = None,
        framework_id: str | None = None,
    ) -> list[OrganizationTrustProfile]:
        """List Organization Trust Profiles with optional filters."""
        return await self._repository.list(
            skip=skip,
            limit=limit,
            organization_id=organization_id,
            framework_id=framework_id,
        )

    async def update(
        self,
        profile_id: str,
        **kwargs,
    ) -> OrganizationTrustProfile | None:
        """Update an Organization Trust Profile."""
        profile = await self._repository.get(profile_id)
        if not profile:
            return None

        if "display_name" in kwargs:
            profile.display_name = kwargs["display_name"]
        if "description" in kwargs:
            profile.description = kwargs["description"]
        if "enabled" in kwargs:
            profile.enabled = kwargs["enabled"]
        if "use_case_tags" in kwargs:
            profile.use_case_tags = kwargs["use_case_tags"]
        if "compliance_status" in kwargs:
            profile.compliance_status = kwargs["compliance_status"]
        if "revocation_policy" in kwargs:
            rp = kwargs["revocation_policy"]
            profile.revocation_policy = RevocationPolicy(**rp) if rp else None
        if "time_policy" in kwargs:
            tp = kwargs["time_policy"]
            profile.time_policy = TimePolicy(**tp) if tp else None
        if "allowed_algorithms" in kwargs:
            aa = kwargs["allowed_algorithms"]
            profile.allowed_algorithms = [CryptoAlgorithm(a) for a in aa] if aa is not None else None
        if "allowed_formats" in kwargs:
            af = kwargs["allowed_formats"]
            profile.allowed_formats = [CredentialFormat(f) for f in af] if af is not None else None
        if "allowed_issuers" in kwargs:
            profile.allowed_issuers = kwargs["allowed_issuers"]
        if "denied_issuers" in kwargs:
            profile.denied_issuers = kwargs["denied_issuers"]
        if "jurisdiction_filter" in kwargs:
            profile.jurisdiction_filter = kwargs["jurisdiction_filter"]

        profile.touch()
        saved = await self._repository.save(profile)
        logger.info(f"Updated Organization Trust Profile: {saved.id}")
        return saved

    async def delete(self, profile_id: str) -> bool:
        """Delete an Organization Trust Profile."""
        result = await self._repository.delete(profile_id)
        if result:
            logger.info(f"Deleted Organization Trust Profile: {profile_id}")
        return result
