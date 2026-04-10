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
    
    Accepts a dict of trust adapters keyed by profile_type string
    (e.g. ``{"ICAO": IcaoTrustProfile(...), "AAMVA": AamvaTrustProfile(...)}``).
    The correct adapter is resolved per-profile via ``_adapter_for()``.
    """
    
    def __init__(
        self,
        repository: TrustProfileRepositoryPort,
        trust_validation: TrustValidationPort | None = None,
        event_publisher: EventPublisherPort | None = None,
        trust_adapters: dict[str, Any] | None = None,
    ):
        self._repository = repository
        self._trust_validation = trust_validation
        self._event_publisher = event_publisher
        self._trust_adapters: dict[str, Any] = trust_adapters or {}

    def _adapter_for(self, profile: TrustProfile) -> Any | None:
        """Resolve the trust adapter for a given profile's type.
        
        Falls back to CUSTOM adapter if the profile_type-specific
        adapter is not registered.
        """
        key = profile.profile_type.value if isinstance(profile.profile_type, TrustProfileType) else str(profile.profile_type)
        return self._trust_adapters.get(key) or self._trust_adapters.get("CUSTOM")
    
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
        # Remove keys we handle explicitly so they don't collide with kwargs
        kwargs.pop("supported_formats", None)
        kwargs.pop("allowed_algorithms", None)
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
            
            profile.revocation_policy = RevocationPolicy(
                check_mode=RevocationCheckMode(revocation_policy.get("check_mode") or revocation_policy.get("mode", "HARD_FAIL")),
                cache_ttl_seconds=int(revocation_policy.get("cache_ttl_seconds", 300)),
            )
        
        # Apply time policy if provided
        if time_policy:
            profile.time_policy = TimePolicy(
                clock_skew_seconds=int(time_policy.get("clock_skew_seconds", 300)),
                max_credential_age_seconds=time_policy.get("max_credential_age_seconds"),
                require_freshness=time_policy.get("require_freshness", False),
                freshness_window_seconds=time_policy.get("freshness_window_seconds"),
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

    async def update_revocation_services(
        self,
        profile_id: str,
        config: dict[str, Any],
    ) -> TrustProfile | None:
        """Update revocation services configuration for a trust profile."""
        profile = await self._repository.get(profile_id)
        if not profile:
            return None

        profile.revocation_services = config
        profile.touch()
        saved = await self._repository.save(profile)
        logger.info(f"Updated revocation services for profile {profile_id}")
        return saved

    async def update_system_issuer_overrides(
        self,
        profile_id: str,
        overrides: dict[str, Any],
    ) -> TrustProfile | None:
        """Bulk update system issuer overrides for a trust profile."""
        profile = await self._repository.get(profile_id)
        if not profile:
            return None

        profile.system_issuer_overrides = overrides
        profile.touch()
        saved = await self._repository.save(profile)
        logger.info(f"Updated system issuer overrides for profile {profile_id}")
        return saved

    # ------------------------------------------------------------------
    # Trust adapter delegation
    # ------------------------------------------------------------------

    async def validate_chain(
        self,
        profile_id: str,
        certificate_pem: str | None = None,
        certificate_der: bytes | None = None,
    ) -> dict[str, Any]:
        """Validate a certificate chain using the adapter matching the profile's type."""
        profile = await self._repository.get(profile_id)
        if not profile:
            return {"error": f"Trust Profile {profile_id} not found"}

        adapter = self._adapter_for(profile)
        if adapter is None:
            return {"error": f"No trust adapter registered for profile_type={profile.profile_type}"}

        result = await adapter.validate_chain(
            certificate_pem=certificate_pem,
            certificate_der=certificate_der,
        )
        return {
            "status": result.status.value if hasattr(result.status, "value") else str(result.status),
            "trust_anchor_id": result.trust_anchor_id,
            "chain_length": result.chain_length,
            "errors": result.errors,
        }

    async def get_trust_anchors(
        self,
        profile_id: str,
        jurisdiction: str | None = None,
        country_code: str | None = None,
    ) -> list[Any]:
        """Get trust anchors from the adapter matching the profile's type."""
        profile = await self._repository.get(profile_id)
        if not profile:
            return []

        adapter = self._adapter_for(profile)
        if adapter is None:
            return []

        return await adapter.get_trust_anchors(
            jurisdiction=jurisdiction,
            country_code=country_code,
        )

    async def check_revocation(
        self,
        profile_id: str,
        certificate_pem: str | None = None,
        certificate_der: bytes | None = None,
    ) -> dict[str, Any]:
        """Check certificate revocation using the adapter matching the profile's type."""
        profile = await self._repository.get(profile_id)
        if not profile:
            return {"error": f"Trust Profile {profile_id} not found"}

        adapter = self._adapter_for(profile)
        if adapter is None:
            return {"error": f"No trust adapter registered for profile_type={profile.profile_type}"}

        result = await adapter.check_revocation(
            certificate_pem=certificate_pem,
            certificate_der=certificate_der,
        )
        return {
            "status": result.status.value if hasattr(result.status, "value") else str(result.status),
            "checked_via": result.checked_via,
            "errors": result.errors,
        }
