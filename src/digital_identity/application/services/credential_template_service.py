"""
Credential Template Service

Application service for Credential Template management.
Implements the CredentialTemplateServicePort interface.
"""

from __future__ import annotations

import logging
from typing import Any

from digital_identity.domain.entities import CredentialTemplate
from digital_identity.domain.events import (
    CredentialTemplateCreatedEvent,
    CredentialTemplateUpdatedEvent,
    CredentialTemplateDeletedEvent,
)
from digital_identity.domain.value_objects import (
    CredentialFormat,
    ClaimDefinition,
    ValidityRules,
)
from digital_identity.application.ports.outbound import (
    CredentialTemplateRepositoryPort,
    EventPublisherPort,
)

logger = logging.getLogger(__name__)


class CredentialTemplateService:
    """
    Service for Credential Template management.
    
    Orchestrates domain operations for Credential Templates including
    CRUD and claim management.
    """
    
    def __init__(
        self,
        repository: CredentialTemplateRepositoryPort,
        event_publisher: EventPublisherPort | None = None,
    ):
        self._repository = repository
        self._event_publisher = event_publisher
    
    async def create(
        self,
        name: str,
        credential_type: str,
        description: str | None = None,
        claims: list[dict[str, Any]] | None = None,
        format: str = "sd_jwt_vc",
        namespace: str | None = None,
        validity_rules: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> CredentialTemplate:
        """Create a new Credential Template."""
        # Check for duplicate type
        existing = await self._repository.get_by_type(credential_type)
        if existing:
            raise ValueError(f"Credential Template for type '{credential_type}' already exists")
        
        # Parse claims
        claim_defs = []
        if claims:
            for claim_data in claims:
                claim_defs.append(ClaimDefinition(**claim_data))
        
        # Create entity
        template = CredentialTemplate(
            name=name,
            credential_type=credential_type,
            description=description,
            claims=claim_defs,
            format=CredentialFormat(format),
            namespace=namespace,
            **kwargs,
        )
        
        # Apply validity rules if provided
        if validity_rules:
            template.validity_rules = ValidityRules(**validity_rules)
        
        # Save
        saved = await self._repository.save(template)
        
        # Publish event
        if self._event_publisher:
            await self._event_publisher.publish(
                CredentialTemplateCreatedEvent(
                    template_id=saved.id,
                    name=saved.name,
                    credential_type=saved.credential_type,
                )
            )
        
        logger.info(f"Created Credential Template: {saved.id} ({saved.name})")
        return saved
    
    async def get(self, template_id: str) -> CredentialTemplate | None:
        """Get a Credential Template by ID."""
        return await self._repository.get(template_id)
    
    async def get_by_type(self, credential_type: str) -> CredentialTemplate | None:
        """Get a Credential Template by credential type."""
        return await self._repository.get_by_type(credential_type)
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        format: str | None = None,
    ) -> list[CredentialTemplate]:
        """List Credential Templates with optional filters."""
        return await self._repository.list(
            skip=skip,
            limit=limit,
            format=format,
        )
    
    async def update(
        self,
        template_id: str,
        **updates: Any,
    ) -> CredentialTemplate | None:
        """Update a Credential Template."""
        template = await self._repository.get(template_id)
        if not template:
            return None
        
        # Track changes for event
        changes = {}
        
        # Apply updates
        for key, value in updates.items():
            if hasattr(template, key):
                old_value = getattr(template, key)
                if old_value != value:
                    setattr(template, key, value)
                    changes[key] = {"old": str(old_value), "new": str(value)}
        
        if changes:
            template.touch()
            saved = await self._repository.save(template)
            
            # Publish event
            if self._event_publisher:
                await self._event_publisher.publish(
                    CredentialTemplateUpdatedEvent(
                        template_id=saved.id,
                        changes=changes,
                    )
                )
            
            logger.info(f"Updated Credential Template: {saved.id}")
            return saved
        
        return template
    
    async def delete(self, template_id: str) -> bool:
        """Delete a Credential Template."""
        if not await self._repository.exists(template_id):
            return False
        
        result = await self._repository.delete(template_id)
        
        if result and self._event_publisher:
            await self._event_publisher.publish(
                CredentialTemplateDeletedEvent(template_id=template_id)
            )
        
        logger.info(f"Deleted Credential Template: {template_id}")
        return result
    
    async def add_claim(
        self,
        template_id: str,
        name: str,
        display_name: str,
        data_type: str,
        required: bool = True,
        selectively_disclosable: bool = True,
        **kwargs: Any,
    ) -> CredentialTemplate | None:
        """Add a claim to a template."""
        template = await self._repository.get(template_id)
        if not template:
            return None
        
        claim = ClaimDefinition(
            name=name,
            display_name=display_name,
            data_type=data_type,
            required=required,
            selectively_disclosable=selectively_disclosable,
            **kwargs,
        )
        template.add_claim(claim)
        saved = await self._repository.save(template)
        
        logger.info(f"Added claim '{name}' to template {template_id}")
        return saved
