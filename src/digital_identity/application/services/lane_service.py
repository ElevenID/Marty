"""
Lane Service

Application service for Lane management within Deployment Profiles.
Implements Lane CRUD operations and device assignments.
"""

from __future__ import annotations

import logging
from typing import Any

from digital_identity.domain.entities import Lane, DeploymentProfile
from digital_identity.domain.events import (
    DeploymentProfileUpdatedEvent,
)
from digital_identity.application.ports.outbound import (
    DeploymentProfileRepositoryPort,
    EventPublisherPort,
)

logger = logging.getLogger(__name__)


class LaneService:
    """
    Service for Lane management.
    
    Orchestrates domain operations for Lanes including
    CRUD and device assignments.
    """
    
    def __init__(
        self,
        deployment_profile_repository: DeploymentProfileRepositoryPort,
        event_publisher: EventPublisherPort | None = None,
    ):
        self._profile_repository = deployment_profile_repository
        self._event_publisher = event_publisher
    
    async def create(
        self,
        deployment_profile_id: str,
        name: str,
        default_policy_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Lane:
        """Create a new Lane under a Deployment Profile."""
        # Get parent profile
        profile = await self._profile_repository.get(deployment_profile_id)
        if not profile:
            raise ValueError(f"Deployment Profile '{deployment_profile_id}' not found")
        
        # Create lane
        lane = Lane(
            name=name,
            deployment_profile_id=deployment_profile_id,
            default_policy_id=default_policy_id,
            metadata=metadata or {},
        )
        
        # Add to profile
        profile.lanes.append(lane)
        profile.touch()
        
        # Save
        await self._profile_repository.save(profile)
        
        # Publish event
        if self._event_publisher:
            await self._event_publisher.publish(
                DeploymentProfileUpdatedEvent(
                    profile_id=profile.id,
                    name=profile.name,
                )
            )
        
        logger.info(f"Created Lane: {lane.id} ({lane.name}) in profile {deployment_profile_id}")
        return lane
    
    async def get(self, deployment_profile_id: str, lane_id: str) -> Lane | None:
        """Get a Lane by ID within a Deployment Profile."""
        profile = await self._profile_repository.get(deployment_profile_id)
        if not profile:
            return None
        
        for lane in profile.lanes:
            if lane.id == lane_id:
                return lane
        return None
    
    async def list(self, deployment_profile_id: str) -> list[Lane]:
        """List all Lanes in a Deployment Profile."""
        profile = await self._profile_repository.get(deployment_profile_id)
        if not profile:
            return []
        return profile.lanes
    
    async def update(
        self,
        deployment_profile_id: str,
        lane_id: str,
        name: str | None = None,
        default_policy_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Lane | None:
        """Update a Lane."""
        profile = await self._profile_repository.get(deployment_profile_id)
        if not profile:
            return None
        
        # Find lane
        lane = None
        for l in profile.lanes:
            if l.id == lane_id:
                lane = l
                break
        
        if not lane:
            return None
        
        # Update fields
        if name is not None:
            lane.name = name
        if default_policy_id is not None:
            lane.default_policy_id = default_policy_id
        if metadata is not None:
            lane.metadata = metadata
        
        lane.touch()
        profile.touch()
        
        # Save
        await self._profile_repository.save(profile)
        
        # Publish event
        if self._event_publisher:
            await self._event_publisher.publish(
                DeploymentProfileUpdatedEvent(
                    profile_id=profile.id,
                    name=profile.name,
                )
            )
        
        logger.info(f"Updated Lane: {lane_id} in profile {deployment_profile_id}")
        return lane
    
    async def delete(
        self,
        deployment_profile_id: str,
        lane_id: str,
    ) -> bool:
        """Delete a Lane."""
        profile = await self._profile_repository.get(deployment_profile_id)
        if not profile:
            return False
        
        # Find and remove lane
        lane_found = False
        for i, lane in enumerate(profile.lanes):
            if lane.id == lane_id:
                profile.lanes.pop(i)
                lane_found = True
                break
        
        if not lane_found:
            return False
        
        profile.touch()
        
        # Save
        await self._profile_repository.save(profile)
        
        # Publish event
        if self._event_publisher:
            await self._event_publisher.publish(
                DeploymentProfileUpdatedEvent(
                    profile_id=profile.id,
                    name=profile.name,
                )
            )
        
        logger.info(f"Deleted Lane: {lane_id} from profile {deployment_profile_id}")
        return True
    
    async def assign_devices(
        self,
        deployment_profile_id: str,
        lane_id: str,
        device_ids: list[str],
    ) -> Lane | None:
        """Assign devices to a Lane."""
        profile = await self._profile_repository.get(deployment_profile_id)
        if not profile:
            return None
        
        # Find lane
        lane = None
        for l in profile.lanes:
            if l.id == lane_id:
                lane = l
                break
        
        if not lane:
            return None
        
        # Assign devices (replace existing assignments)
        lane.device_ids = device_ids
        lane.touch()
        profile.touch()
        
        # Save
        await self._profile_repository.save(profile)
        
        # Publish event
        if self._event_publisher:
            await self._event_publisher.publish(
                DeploymentProfileUpdatedEvent(
                    profile_id=profile.id,
                    name=profile.name,
                )
            )
        
        logger.info(f"Assigned {len(device_ids)} devices to Lane: {lane_id}")
        return lane
