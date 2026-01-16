"""
Deployment Profile Service

Application service for Deployment Profile management.
Implements the DeploymentProfileServicePort interface.
"""

from __future__ import annotations

import logging
from typing import Any

from digital_identity.domain.entities import DeploymentProfile
from digital_identity.domain.events import (
    DeploymentProfileCreatedEvent,
    DeploymentProfileUpdatedEvent,
    DeploymentProfileDeletedEvent,
)
from digital_identity.domain.value_objects import (
    NetworkMode,
    KeyAccessMode,
    UXConfig,
    UpdatePolicy,
)
from digital_identity.application.ports.outbound import (
    DeploymentProfileRepositoryPort,
    EventPublisherPort,
)

logger = logging.getLogger(__name__)


class DeploymentProfileService:
    """
    Service for Deployment Profile management.
    
    Orchestrates domain operations for Deployment Profiles including
    CRUD and flow enablement.
    """
    
    def __init__(
        self,
        repository: DeploymentProfileRepositoryPort,
        event_publisher: EventPublisherPort | None = None,
    ):
        self._repository = repository
        self._event_publisher = event_publisher
    
    async def create(
        self,
        name: str,
        site_id: str | None = None,
        description: str | None = None,
        network_mode: str = "online",
        key_access_mode: str = "key_vault",
        enabled_flow_ids: list[str] | None = None,
        default_presentation_policy_id: str | None = None,
        ux_config: dict[str, Any] | None = None,
        update_policy: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> DeploymentProfile:
        """Create a new Deployment Profile."""
        # Check for duplicate site_id
        if site_id:
            existing = await self._repository.get_by_site(site_id)
            if existing:
                raise ValueError(f"Deployment Profile for site '{site_id}' already exists")
        
        # Create entity
        profile = DeploymentProfile(
            name=name,
            site_id=site_id,
            description=description,
            network_mode=NetworkMode(network_mode),
            key_access_mode=KeyAccessMode(key_access_mode),
            enabled_flow_ids=enabled_flow_ids or [],
            default_presentation_policy_id=default_presentation_policy_id,
            **kwargs,
        )
        
        # Apply UX config if provided
        if ux_config:
            profile.ux_config = UXConfig(**ux_config)
        
        # Apply update policy if provided
        if update_policy:
            profile.update_policy = UpdatePolicy(**update_policy)
        
        # Save
        saved = await self._repository.save(profile)
        
        # Publish event
        if self._event_publisher:
            await self._event_publisher.publish(
                DeploymentProfileCreatedEvent(
                    profile_id=saved.id,
                    name=saved.name,
                    site_id=saved.site_id,
                )
            )
        
        logger.info(f"Created Deployment Profile: {saved.id} ({saved.name})")
        return saved
    
    async def get(self, profile_id: str) -> DeploymentProfile | None:
        """Get a Deployment Profile by ID."""
        return await self._repository.get(profile_id)
    
    async def get_by_site(self, site_id: str) -> DeploymentProfile | None:
        """Get a Deployment Profile by site ID."""
        return await self._repository.get_by_site(site_id)
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        network_mode: str | None = None,
    ) -> list[DeploymentProfile]:
        """List Deployment Profiles with optional filters."""
        return await self._repository.list(
            skip=skip,
            limit=limit,
            network_mode=network_mode,
        )
    
    async def update(
        self,
        profile_id: str,
        **updates: Any,
    ) -> DeploymentProfile | None:
        """Update a Deployment Profile."""
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
                    DeploymentProfileUpdatedEvent(
                        profile_id=saved.id,
                        changes=changes,
                    )
                )
            
            logger.info(f"Updated Deployment Profile: {saved.id}")
            return saved
        
        return profile
    
    async def delete(self, profile_id: str) -> bool:
        """Delete a Deployment Profile."""
        if not await self._repository.exists(profile_id):
            return False
        
        result = await self._repository.delete(profile_id)
        
        if result and self._event_publisher:
            await self._event_publisher.publish(
                DeploymentProfileDeletedEvent(profile_id=profile_id)
            )
        
        logger.info(f"Deleted Deployment Profile: {profile_id}")
        return result
    
    async def enable_flow(
        self,
        profile_id: str,
        flow_id: str,
    ) -> DeploymentProfile | None:
        """Enable a flow for a deployment."""
        profile = await self._repository.get(profile_id)
        if not profile:
            return None
        
        profile.enable_flow(flow_id)
        saved = await self._repository.save(profile)
        
        logger.info(f"Enabled flow {flow_id} for deployment {profile_id}")
        return saved
    
    async def disable_flow(
        self,
        profile_id: str,
        flow_id: str,
    ) -> DeploymentProfile | None:
        """Disable a flow for a deployment."""
        profile = await self._repository.get(profile_id)
        if not profile:
            return None
        
        profile.disable_flow(flow_id)
        saved = await self._repository.save(profile)
        
        logger.info(f"Disabled flow {flow_id} for deployment {profile_id}")
        return saved
