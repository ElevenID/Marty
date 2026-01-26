"""
Issuer Registry Service

Manages issuer lifecycle, trust relationships, and cascade revocation operations.
Implements circuit breaker protection and rollback support for high-impact revocations.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from digital_identity.domain.entities import (
    IssuerEntity,
    TrustProfileIssuer,
    CascadeRevocationOperation,
)
from digital_identity.domain.events import (
    IssuerRegisteredEvent,
    IssuerRevokedEvent,
    IssuerSuspendedEvent,
    TrustLevelUpdatedEvent,
    CascadeOperationCreatedEvent,
)

logger = logging.getLogger(__name__)


class IssuerRegistryService:
    """
    Service for managing the issuer registry.
    
    Handles:
    - Issuer registration and lifecycle
    - Trust profile to issuer relationships
    - Cascade revocation with circuit breaker
    - Rollback support for revocation operations
    """
    
    def __init__(
        self,
        issuer_repository: Any,  # IssuerRepositoryPort
        trust_profile_issuer_repository: Any,  # TrustProfileIssuerRepositoryPort
        cascade_operation_repository: Any,  # CascadeOperationRepositoryPort
        credential_repository: Any,  # IssuedCredentialRepositoryPort
        event_publisher: Any,  # EventPublisherPort
    ):
        """
        Initialize issuer registry service.
        
        Args:
            issuer_repository: Repository for issuer entities
            trust_profile_issuer_repository: Repository for trust profile relationships
            cascade_operation_repository: Repository for cascade operations
            credential_repository: Repository for issued credentials
            event_publisher: Event publisher for domain events
        """
        self.issuer_repo = issuer_repository
        self.tp_issuer_repo = trust_profile_issuer_repository
        self.cascade_repo = cascade_operation_repository
        self.credential_repo = credential_repository
        self.event_publisher = event_publisher
    
    async def register_issuer(
        self,
        issuer_id: str,
        display_name: str,
        issuer_type: str = "ORGANIZATION",
        organization_id: str | None = None,
        trust_anchor_id: str | None = None,
        is_system_issuer: bool = False,
        **kwargs: Any,
    ) -> IssuerEntity:
        """
        Register a new issuer.
        
        Args:
            issuer_id: Unique issuer identifier (DID, domain, etc.)
            display_name: Human-readable name
            issuer_type: Type of issuer (ORGANIZATION, GOVERNMENT, DEVICE)
            organization_id: Organization ID (NULL for global issuers)
            trust_anchor_id: Optional link to trust anchor
            is_system_issuer: Whether this is a system issuer (auto-visible)
            **kwargs: Additional issuer attributes
            
        Returns:
            Created issuer entity
        """
        # Create issuer entity
        issuer = IssuerEntity(
            id=str(uuid4()),
            organization_id=organization_id,
            issuer_id=issuer_id,
            issuer_type=issuer_type,
            display_name=display_name,
            is_system_issuer=is_system_issuer,
            trust_anchor_id=trust_anchor_id,
            **kwargs,
        )
        
        # Persist
        await self.issuer_repo.save(issuer)
        
        # Publish event
        event = IssuerRegisteredEvent(
            issuer_id=issuer.id,
            issuer_identifier=issuer.issuer_id,
            organization_id=organization_id,
            is_system_issuer=is_system_issuer,
        )
        await self.event_publisher.publish(event)
        
        logger.info(f"Registered issuer: {issuer.issuer_id} ({issuer.id})")
        return issuer
    
    async def link_to_trust_anchor(
        self,
        issuer_id: str,
        trust_anchor_id: str,
    ) -> IssuerEntity:
        """
        Link an issuer to a trust anchor.
        
        Args:
            issuer_id: Issuer entity ID
            trust_anchor_id: Trust anchor identifier
            
        Returns:
            Updated issuer entity
        """
        issuer = await self.issuer_repo.get(issuer_id)
        if not issuer:
            raise ValueError(f"Issuer not found: {issuer_id}")
        
        issuer.trust_anchor_id = trust_anchor_id
        issuer.touch()
        
        await self.issuer_repo.save(issuer)
        logger.info(f"Linked issuer {issuer_id} to trust anchor {trust_anchor_id}")
        return issuer
    
    async def add_issuer_to_trust_profile(
        self,
        trust_profile_id: str,
        issuer_id: str,
        trust_level: int = 100,
        cascade_policy: str = "MANUAL",
        relationship_status: str = "TRUSTED",
    ) -> TrustProfileIssuer:
        """
        Add an issuer to a trust profile with trust scoring.
        
        Args:
            trust_profile_id: Trust profile ID
            issuer_id: Issuer entity ID
            trust_level: Trust score 0-100
            cascade_policy: Cascade revocation policy (AUTO_CASCADE, MANUAL, NOTIFY_ONLY)
            relationship_status: Relationship status (TRUSTED, DENIED, UNDER_REVIEW)
            
        Returns:
            Created relationship entity
        """
        # Validate trust level
        if not 0 <= trust_level <= 100:
            raise ValueError("Trust level must be between 0 and 100")
        
        # Create relationship
        relationship = TrustProfileIssuer(
            id=str(uuid4()),
            trust_profile_id=trust_profile_id,
            issuer_id=issuer_id,
            trust_level=trust_level,
            cascade_revocation_policy=cascade_policy,
            relationship_status=relationship_status,
        )
        
        await self.tp_issuer_repo.save(relationship)
        logger.info(f"Added issuer {issuer_id} to trust profile {trust_profile_id}")
        return relationship
    
    async def update_trust_level(
        self,
        trust_profile_id: str,
        issuer_id: str,
        new_level: int,
        reason: str | None = None,
    ) -> TrustProfileIssuer:
        """
        Update trust level for an issuer in a trust profile.
        
        Args:
            trust_profile_id: Trust profile ID
            issuer_id: Issuer entity ID
            new_level: New trust level (0-100)
            reason: Optional reason for change
            
        Returns:
            Updated relationship
        """
        relationship = await self.tp_issuer_repo.get_by_profile_and_issuer(
            trust_profile_id, issuer_id
        )
        if not relationship:
            raise ValueError(f"Relationship not found: {trust_profile_id}:{issuer_id}")
        
        old_level = relationship.trust_level
        relationship.update_trust_level(new_level, reason)
        
        await self.tp_issuer_repo.save(relationship)
        
        # Publish event
        event = TrustLevelUpdatedEvent(
            trust_profile_id=trust_profile_id,
            issuer_id=issuer_id,
            old_level=old_level,
            new_level=new_level,
            reason=reason,
        )
        await self.event_publisher.publish(event)
        
        logger.info(f"Updated trust level for {issuer_id} in {trust_profile_id}: {old_level} → {new_level}")
        return relationship
    
    async def get_issuers_by_anchor(self, trust_anchor_id: str) -> list[IssuerEntity]:
        """
        Get all issuers linked to a trust anchor.
        
        Useful for cascade revocation from anchor to issuers.
        
        Args:
            trust_anchor_id: Trust anchor identifier
            
        Returns:
            List of issuer entities
        """
        return await self.issuer_repo.find_by_trust_anchor(trust_anchor_id)
    
    async def revoke_issuer(
        self,
        issuer_id: str,
        reason: str,
        revoked_by: str,
        cascade_policy: str | None = None,
        max_cascade_depth: int = 3,
        circuit_breaker_threshold: int = 1000,
    ) -> CascadeRevocationOperation:
        """
        Revoke an issuer and create cascade operation for dependent credentials.
        
        Args:
            issuer_id: Issuer entity ID
            reason: Revocation reason
            revoked_by: Who initiated revocation
            cascade_policy: Override policy (or use relationship policies)
            max_cascade_depth: Maximum cascade depth
            circuit_breaker_threshold: Max credentials before requiring confirmation
            
        Returns:
            Cascade operation entity
        """
        # Get issuer
        issuer = await self.issuer_repo.get(issuer_id)
        if not issuer:
            raise ValueError(f"Issuer not found: {issuer_id}")
        
        # Revoke issuer
        issuer.revoke(reason, revoked_by)
        await self.issuer_repo.save(issuer)
        
        # Publish event
        event = IssuerRevokedEvent(
            issuer_id=issuer.id,
            issuer_identifier=issuer.issuer_id,
            reason=reason,
            revoked_by=revoked_by,
        )
        await self.event_publisher.publish(event)
        
        # Find affected credentials
        affected_credentials = await self.credential_repo.find_by_issuer(issuer.issuer_id)
        credential_count = len(affected_credentials)
        
        # Create cascade operation
        operation = CascadeRevocationOperation(
            id=str(uuid4()),
            operation_type="ISSUER_REVOCATION",
            trigger_entity_type="ISSUER",
            trigger_entity_id=issuer_id,
            status="PENDING_CONFIRMATION" if credential_count > circuit_breaker_threshold else "IN_PROGRESS",
            affected_credential_count=credential_count,
            affected_credential_ids=[c.id for c in affected_credentials],
            requires_confirmation=credential_count > circuit_breaker_threshold,
            max_cascade_depth=max_cascade_depth,
            circuit_breaker_threshold=circuit_breaker_threshold,
            circuit_breaker_triggered=credential_count > circuit_breaker_threshold,
            rollback_snapshot={
                "issuer_status": "ACTIVE",
                "revoked_at": None,
                "affected_credentials": [
                    {"id": c.id, "status": c.status, "revoked_at": None}
                    for c in affected_credentials
                ],
            },
            metadata={"cascade_policy": cascade_policy, "reason": reason},
        )
        
        await self.cascade_repo.save(operation)
        
        # Publish cascade event
        cascade_event = CascadeOperationCreatedEvent(
            operation_id=operation.id,
            trigger_entity_id=issuer_id,
            affected_count=credential_count,
            requires_confirmation=operation.requires_confirmation,
        )
        await self.event_publisher.publish(cascade_event)
        
        logger.warning(
            f"Issuer {issuer.issuer_id} revoked. "
            f"Cascade operation {operation.id} created affecting {credential_count} credentials"
        )
        
        # Auto-execute if below threshold
        if not operation.requires_confirmation:
            await self._execute_cascade(operation, cascade_policy)
        
        return operation
    
    async def confirm_cascade(
        self,
        operation_id: str,
        confirmed_by: str,
    ) -> CascadeRevocationOperation:
        """
        Confirm and execute a high-impact cascade operation.
        
        Args:
            operation_id: Cascade operation ID
            confirmed_by: Who confirmed the operation
            
        Returns:
            Updated cascade operation
        """
        operation = await self.cascade_repo.get(operation_id)
        if not operation:
            raise ValueError(f"Cascade operation not found: {operation_id}")
        
        if not operation.is_pending_confirmation():
            raise ValueError(f"Operation {operation_id} is not pending confirmation")
        
        operation.confirm(confirmed_by)
        await self.cascade_repo.save(operation)
        
        # Execute cascade
        await self._execute_cascade(operation, operation.metadata.get("cascade_policy"))
        
        return operation
    
    async def rollback_cascade(
        self,
        operation_id: str,
        rolled_back_by: str,
    ) -> CascadeRevocationOperation:
        """
        Roll back a completed cascade operation.
        
        Args:
            operation_id: Cascade operation ID
            rolled_back_by: Who initiated rollback
            
        Returns:
            Updated cascade operation
        """
        operation = await self.cascade_repo.get(operation_id)
        if not operation:
            raise ValueError(f"Cascade operation not found: {operation_id}")
        
        if not operation.can_be_rolled_back():
            raise ValueError(f"Operation {operation_id} cannot be rolled back")
        
        # Restore issuer
        issuer = await self.issuer_repo.get(operation.trigger_entity_id)
        if issuer:
            snapshot = operation.rollback_snapshot
            issuer.revoked_at = None
            issuer.revocation_reason = None
            issuer.revoked_by = None
            issuer.compliance_status = "COMPLIANT"
            await self.issuer_repo.save(issuer)
        
        # Restore credentials
        for cred_data in operation.rollback_snapshot.get("affected_credentials", []):
            credential = await self.credential_repo.get(cred_data["id"])
            if credential:
                credential.status = cred_data["status"]
                credential.revoked_at = cred_data["revoked_at"]
                credential.revocation_reason = None
                await self.credential_repo.save(credential)
        
        # Update operation
        operation.rollback(rolled_back_by)
        await self.cascade_repo.save(operation)
        
        logger.info(f"Rolled back cascade operation {operation_id}")
        return operation
    
    async def _execute_cascade(
        self,
        operation: CascadeRevocationOperation,
        cascade_policy: str | None,
    ) -> None:
        """
        Execute the cascade revocation of credentials.
        
        Args:
            operation: Cascade operation entity
            cascade_policy: Cascade policy override
        """
        try:
            # Get relationships to determine cascade behavior
            relationships = await self.tp_issuer_repo.find_by_issuer(operation.trigger_entity_id)
            
            # Determine effective cascade policy
            effective_policy = cascade_policy
            if not effective_policy and relationships:
                # Use first relationship's policy (in real impl, would need more sophisticated logic)
                effective_policy = relationships[0].cascade_revocation_policy
            
            if effective_policy == "AUTO_CASCADE":
                # Revoke all affected credentials
                for cred_id in operation.affected_credential_ids:
                    credential = await self.credential_repo.get(cred_id)
                    if credential and not credential.revoked_at:
                        credential.revoked_at = datetime.now(timezone.utc)
                        credential.revocation_reason = f"Issuer revoked: {operation.metadata.get('reason')}"
                        credential.revoked_by = "SYSTEM_CASCADE"
                        await self.credential_repo.save(credential)
                
                logger.info(f"Auto-cascaded revocation to {len(operation.affected_credential_ids)} credentials")
            
            elif effective_policy == "MANUAL":
                # Mark credentials for review but don't auto-revoke
                for cred_id in operation.affected_credential_ids:
                    credential = await self.credential_repo.get(cred_id)
                    if credential:
                        credential.metadata["pending_review"] = True
                        credential.metadata["review_reason"] = f"Issuer revoked: {operation.metadata.get('reason')}"
                        await self.credential_repo.save(credential)
                
                logger.info(f"Marked {len(operation.affected_credential_ids)} credentials for manual review")
            
            else:  # NOTIFY_ONLY
                # Just send notifications, don't modify credentials
                logger.info(f"Notification-only cascade for {len(operation.affected_credential_ids)} credentials")
            
            # Mark operation complete
            operation.complete()
            await self.cascade_repo.save(operation)
        
        except Exception as e:
            logger.error(f"Cascade execution failed: {e}", exc_info=True)
            operation.fail(str(e))
            await self.cascade_repo.save(operation)
            raise
