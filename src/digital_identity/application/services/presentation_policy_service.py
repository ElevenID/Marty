"""
Presentation Policy Service

Application service for Presentation Policy management.
Implements the PresentationPolicyServicePort interface.
"""

from __future__ import annotations

import logging
from typing import Any

from digital_identity.domain.entities import PresentationPolicy
from digital_identity.domain.events import (
    PresentationPolicyCreatedEvent,
    PresentationPolicyUpdatedEvent,
    PresentationPolicyDeletedEvent,
)
from digital_identity.domain.value_objects import (
    HolderBindingMethod,
    RequiredClaim,
    FreshnessRequirements,
)
from digital_identity.application.ports.outbound import (
    PresentationPolicyRepositoryPort,
    EventPublisherPort,
)

logger = logging.getLogger(__name__)


class PresentationPolicyService:
    """
    Service for Presentation Policy management.
    
    Orchestrates domain operations for Presentation Policies including
    CRUD and required claims management.
    """
    
    def __init__(
        self,
        repository: PresentationPolicyRepositoryPort,
        event_publisher: EventPublisherPort | None = None,
    ):
        self._repository = repository
        self._event_publisher = event_publisher
    
    async def create(
        self,
        name: str,
        purpose: str,
        description: str | None = None,
        required_claims: list[dict[str, Any]] | None = None,
        accepted_credential_types: list[str] | None = None,
        holder_binding: str | dict[str, Any] = "NONCE",
        trust_profile_id: str | None = None,
        freshness_requirements: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> PresentationPolicy:
        """Create a new Presentation Policy."""
        # Check for duplicate name
        existing = await self._repository.get_by_name(name)
        if existing:
            raise ValueError(f"Presentation Policy with name '{name}' already exists")
        
        # Parse required claims
        claims = []
        if required_claims:
            for claim_data in required_claims:
                claims.append(RequiredClaim(**claim_data))
        
        # Resolve holder_binding (accept dict from schema or string)
        if isinstance(holder_binding, dict):
            binding_methods = holder_binding.get("binding_methods", [])
            hb_value = binding_methods[0] if binding_methods else "NONE"
            if not holder_binding.get("required", False):
                hb_value = "NONE"
        else:
            hb_value = holder_binding
        
        # Create entity
        policy = PresentationPolicy(
            name=name,
            purpose=purpose,
            description=description,
            required_claims=claims,
            accepted_credential_types=accepted_credential_types or [],
            holder_binding=HolderBindingMethod(hb_value),
            trust_profile_id=trust_profile_id,
            **kwargs,
        )
        
        # Apply freshness requirements if provided
        if freshness_requirements:
            policy.freshness_requirements = FreshnessRequirements(**freshness_requirements)
        
        # Save
        saved = await self._repository.save(policy)
        
        # Publish event
        if self._event_publisher:
            await self._event_publisher.publish(
                PresentationPolicyCreatedEvent(
                    policy_id=saved.id,
                    name=saved.name,
                    purpose=saved.purpose,
                )
            )
        
        logger.info(f"Created Presentation Policy: {saved.id} ({saved.name})")
        return saved
    
    async def get(self, policy_id: str) -> PresentationPolicy | None:
        """Get a Presentation Policy by ID."""
        return await self._repository.get(policy_id)
    
    async def get_by_name(self, name: str) -> PresentationPolicy | None:
        """Get a Presentation Policy by name."""
        return await self._repository.get_by_name(name)
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        trust_profile_id: str | None = None,
    ) -> list[PresentationPolicy]:
        """List Presentation Policies with optional filters."""
        return await self._repository.list(
            skip=skip,
            limit=limit,
            trust_profile_id=trust_profile_id,
        )
    
    async def update(
        self,
        policy_id: str,
        **updates: Any,
    ) -> PresentationPolicy | None:
        """Update a Presentation Policy."""
        policy = await self._repository.get(policy_id)
        if not policy:
            return None
        
        # Track changes for event
        changes = {}
        
        # Apply updates
        for key, value in updates.items():
            if hasattr(policy, key):
                old_value = getattr(policy, key)
                if old_value != value:
                    setattr(policy, key, value)
                    changes[key] = {"old": str(old_value), "new": str(value)}
        
        if changes:
            policy.touch()
            saved = await self._repository.save(policy)
            
            # Publish event
            if self._event_publisher:
                await self._event_publisher.publish(
                    PresentationPolicyUpdatedEvent(
                        policy_id=saved.id,
                        changes=changes,
                    )
                )
            
            logger.info(f"Updated Presentation Policy: {saved.id}")
            return saved
        
        return policy
    
    async def delete(self, policy_id: str) -> bool:
        """Delete a Presentation Policy."""
        if not await self._repository.exists(policy_id):
            return False
        
        result = await self._repository.delete(policy_id)
        
        if result and self._event_publisher:
            await self._event_publisher.publish(
                PresentationPolicyDeletedEvent(policy_id=policy_id)
            )
        
        logger.info(f"Deleted Presentation Policy: {policy_id}")
        return result
    
    async def add_required_claim(
        self,
        policy_id: str,
        claim_name: str,
        credential_type: str,
        accept_predicate: bool = True,
        required_value: Any = None,
    ) -> PresentationPolicy | None:
        """Add a required claim to a policy."""
        policy = await self._repository.get(policy_id)
        if not policy:
            return None
        
        policy.add_required_claim(
            claim_name=claim_name,
            credential_type=credential_type,
            accept_predicate=accept_predicate,
            required_value=required_value,
        )
        saved = await self._repository.save(policy)
        
        logger.info(f"Added required claim '{claim_name}' to policy {policy_id}")
        return saved
