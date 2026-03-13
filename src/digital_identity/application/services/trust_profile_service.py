"""
Trust Profile Service

Application service for Trust Profile management.
Implements the TrustProfileServicePort interface.
"""

from __future__ import annotations

import logging
from typing import Any

from digital_identity.domain.entities import TrustProfile
from digital_identity.domain.events import (
    TrustProfileCreatedEvent,
    TrustProfileUpdatedEvent,
    TrustProfileDeletedEvent,
)
from digital_identity.domain.value_objects import (
    TrustProfileType,
    RevocationPolicy,
    TimePolicy,
    CryptoAlgorithm,
    CredentialFormat,
)
from digital_identity.application.ports.outbound import (
    TrustProfileRepositoryPort,
    TrustValidationPort,
    EventPublisherPort,
)

logger = logging.getLogger(__name__)


class TrustProfileService:
    """
    Service for Trust Profile management.
    
    Orchestrates domain operations for Trust Profiles including
    CRUD, trust source management, and trust data refresh.
    """
    
    def __init__(
        self,
        repository: TrustProfileRepositoryPort,
        trust_validation: TrustValidationPort | None = None,
        event_publisher: EventPublisherPort | None = None,
    ):
        self._repository = repository
        self._trust_validation = trust_validation
        self._event_publisher = event_publisher
    
    async def create(
        self,
        name: str,
        profile_type: str | TrustProfileType,  # Accept both string and enum
        description: str | None = None,
        trust_sources: list[dict[str, Any]] | None = None,
        allowed_algorithms: list[str] | None = None,
        allowed_formats: list[str] | None = None,
        revocation_policy: dict[str, Any] | None = None,
        time_policy: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> TrustProfile:
        """Create a new Trust Profile."""
        # Check for duplicate name
        existing = await self._repository.get_by_name(name)
        if existing:
            raise ValueError(f"Trust Profile with name '{name}' already exists")
        
        # Convert profile_type to enum if it's a string
        if isinstance(profile_type, str):
            profile_type = TrustProfileType(profile_type)
        
        # Parse algorithms
        algorithms = [
            CryptoAlgorithm(a) for a in (allowed_algorithms or ["ES256", "ES384", "ES512"])
        ]
        
        # Parse formats
        formats = [
            CredentialFormat(f) for f in (allowed_formats or ["MDOC", "SD_JWT_VC"])
        ]
        
        # Create entity
        profile = TrustProfile(
            name=name,
            profile_type=profile_type,
            description=description,
            trust_sources=trust_sources or [],
            allowed_algorithms=algorithms,
            supported_formats=formats,
            **kwargs,
        )
        
        # Apply revocation policy if provided
        if revocation_policy:
            from digital_identity.domain.value_objects import RevocationCheckMode
            from datetime import timedelta
            
            # Convert schema format to value object format
            policy_data = {
                "mode": RevocationCheckMode(revocation_policy.get("check_mode") or revocation_policy.get("mode", "HARD_FAIL")),
                "check_ocsp": revocation_policy.get("check_ocsp", True),
                "check_crl": revocation_policy.get("check_crl", True),
                "check_status_list": revocation_policy.get("check_status_list", True),
                "offline_grace_period": timedelta(seconds=revocation_policy.get("offline_grace_period_seconds", 86400)),
                "cache_ttl": timedelta(seconds=revocation_policy.get("cache_ttl_seconds", 3600)),
            }
            profile.revocation_policy = RevocationPolicy(**policy_data)
        
        # Apply time policy if provided
        if time_policy:
            from datetime import timedelta
            
            # Convert schema format to value object format
            clock_skew = timedelta(seconds=time_policy.get("clock_skew_seconds", 300))
            max_age_secs = time_policy.get("max_credential_age_seconds")
            max_age = timedelta(seconds=max_age_secs) if max_age_secs else None
            
            profile.time_policy = TimePolicy(
                clock_skew_tolerance=clock_skew,
                max_credential_age=max_age,
                require_not_before=time_policy.get("require_not_before", True),
                require_not_after=time_policy.get("require_not_after", True),
            )
        
        # Save
        saved = await self._repository.save(profile)
        
        # Publish event
        if self._event_publisher:
            await self._event_publisher.publish(
                TrustProfileCreatedEvent(
                    trust_profile_id=saved.id,
                    name=saved.name,
                    profile_type=saved.profile_type.value,
                )
            )
        
        logger.info(f"Created Trust Profile: {saved.id} ({saved.name})")
        return saved
    
    async def get(self, profile_id: str) -> TrustProfile | None:
        """Get a Trust Profile by ID."""
        return await self._repository.get(profile_id)
    
    async def get_by_name(self, name: str) -> TrustProfile | None:
        """Get a Trust Profile by name."""
        return await self._repository.get_by_name(name)
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        profile_type: TrustProfileType | None = None,
        enabled: bool | None = None,
    ) -> list[TrustProfile]:
        """List Trust Profiles with optional filters."""
        return await self._repository.list(
            skip=skip,
            limit=limit,
            profile_type=profile_type,
            enabled=enabled,
        )
    
    async def update(
        self,
        profile_id: str,
        **updates: Any,
    ) -> TrustProfile | None:
        """Update a Trust Profile."""
        profile = await self._repository.get(profile_id)
        if not profile:
            return None
        
        # Track changes for event
        changes = {}
        
        # Apply updates
        for key, value in updates.items():
            if hasattr(profile, key):
                old_value = getattr(profile, key)
                if old_value != value:
                    setattr(profile, key, value)
                    changes[key] = {"old": str(old_value), "new": str(value)}
        
        if changes:
            profile.touch()
            saved = await self._repository.save(profile)
            
            # Publish event
            if self._event_publisher:
                await self._event_publisher.publish(
                    TrustProfileUpdatedEvent(
                        trust_profile_id=saved.id,
                        changes=changes,
                    )
                )
            
            logger.info(f"Updated Trust Profile: {saved.id}")
            return saved
        
        return profile
    
    async def delete(self, profile_id: str) -> bool:
        """Delete a Trust Profile."""
        if not await self._repository.exists(profile_id):
            return False
        
        result = await self._repository.delete(profile_id)
        
        if result and self._event_publisher:
            await self._event_publisher.publish(
                TrustProfileDeletedEvent(trust_profile_id=profile_id)
            )
        
        logger.info(f"Deleted Trust Profile: {profile_id}")
        return result
    
    async def add_trust_source(
        self,
        profile_id: str,
        source_type: str,
        source_uri: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> TrustProfile | None:
        """Add a trust source to a profile."""
        profile = await self._repository.get(profile_id)
        if not profile:
            return None
        
        profile.add_trust_source(source_type, source_uri, config)
        saved = await self._repository.save(profile)
        
        logger.info(f"Added trust source to profile {profile_id}: {source_type}")
        return saved
    
    async def refresh_trust_data(self, profile_id: str) -> dict[str, Any]:
        """Refresh trust data for a profile."""
        if not self._trust_validation:
            return {"error": "Trust validation service not configured"}
        
        profile = await self._repository.get(profile_id)
        if not profile:
            return {"error": f"Trust Profile {profile_id} not found"}
        
        result = await self._trust_validation.refresh_trust_data(profile_id)
        
        logger.info(f"Refreshed trust data for profile {profile_id}: {result}")
        return result
