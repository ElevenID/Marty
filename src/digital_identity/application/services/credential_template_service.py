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
    CredentialTemplatePublishedEvent,
)
from digital_identity.domain.value_objects import (
    CredentialFormat,
    ClaimDefinition,
    ValidityRules,
    PrivacyPosture,
)
from digital_identity.application.ports.outbound import (
    CredentialTemplateRepositoryPort,
    EventPublisherPort,
    ComplianceProfileRepositoryPort,
)
from digital_identity.application.validation import (
    OBv3ValidationService,
    OBv3ValidationError,
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
        compliance_profile_repository: ComplianceProfileRepositoryPort | None = None,
        event_publisher: EventPublisherPort | None = None,
    ):
        self._repository = repository
        self._compliance_profile_repository = compliance_profile_repository
        self._event_publisher = event_publisher
        self._obv3_validator = OBv3ValidationService()
    
    async def create(
        self,
        name: str,
        credential_type: str,
        description: str | None = None,
        claims: list[dict[str, Any]] | None = None,
        format: str = "SD_JWT_VC",
        credential_payload_format: str | None = None,
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
                # Normalize: accept both "type"/"data_type" → claim_type
                normalized = dict(claim_data)
                if "data_type" in normalized and "claim_type" not in normalized:
                    normalized["claim_type"] = normalized.pop("data_type")
                elif "type" in normalized and "claim_type" not in normalized:
                    normalized["claim_type"] = normalized.pop("type")
                claim_defs.append(ClaimDefinition(**normalized))
        
        # Use credential_payload_format if provided, otherwise fall back to format
        effective_format = credential_payload_format or format
        
        # Normalize privacy_posture if passed as string
        if 'privacy_posture' in kwargs and isinstance(kwargs['privacy_posture'], str):
            kwargs['privacy_posture'] = PrivacyPosture.from_legacy(kwargs['privacy_posture'])
        elif 'privacy_posture' in kwargs and isinstance(kwargs['privacy_posture'], dict):
            kwargs['privacy_posture'] = PrivacyPosture.from_dict(kwargs['privacy_posture'])
        
        # Create entity
        template = CredentialTemplate(
            name=name,
            credential_type=credential_type,
            description=description,
            claims=claim_defs,
            format=CredentialFormat(effective_format),
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
        
        # Normalize privacy_posture if passed as string
        if 'privacy_posture' in updates and isinstance(updates['privacy_posture'], str):
            updates['privacy_posture'] = PrivacyPosture.from_legacy(updates['privacy_posture'])
        elif 'privacy_posture' in updates and isinstance(updates['privacy_posture'], dict):
            updates['privacy_posture'] = PrivacyPosture.from_dict(updates['privacy_posture'])

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
        claim_type: str,
        required: bool = True,
        selectively_disclosable: bool = False,
        **kwargs: Any,
    ) -> CredentialTemplate | None:
        """Add a claim to a template."""
        template = await self._repository.get(template_id)
        if not template:
            return None
        
        claim = ClaimDefinition(
            name=name,
            display_name=display_name,
            claim_type=claim_type,
            required=required,
            selectively_disclosable=selectively_disclosable,
            **kwargs,
        )
        template.add_claim(claim)
        saved = await self._repository.save(template)
        
        logger.info(f"Added claim '{name}' to template {template_id}")
        return saved
    
    async def publish(
        self,
        template_id: str,
        force: bool = False,
    ) -> CredentialTemplate:
        """
        Publish a credential template.
        
        Validates that the template meets all requirements before publishing:
        - Has compliance profile reference (recommended)
        - Has application template reference (required for application-based issuance)
        - Has trust profile reference (if required by compliance profile)
        - Meets OBv3 requirements (if using OBv3 compliance profile)
        - Has valid issuer artifacts
        
        Args:
            template_id: Template to publish
            force: Skip validation checks (use with caution)
        
        Returns:
            Published credential template
        
        Raises:
            ValueError: If template not found or validation fails
            OBv3ValidationError: If OBv3 validation fails
        """
        template = await self._repository.get(template_id)
        if not template:
            raise ValueError(f"Credential Template '{template_id}' not found")
        
        # Check if already published
        if template.status == "ACTIVE":
            logger.info(f"Template {template_id} is already published")
            return template
        
        if not force:
            # Run validation
            validation_errors = await self._validate_for_publish(template)
            if validation_errors:
                error_msg = "Cannot publish template - validation errors:\n" + "\n".join(
                    f"  - {err}" for err in validation_errors
                )
                raise ValueError(error_msg)
        
        # Update status
        template.status = "ACTIVE"
        template.touch()
        saved = await self._repository.save(template)
        
        # Publish event
        if self._event_publisher:
            await self._event_publisher.publish(
                CredentialTemplatePublishedEvent(
                    template_id=saved.id,
                    name=saved.name,
                )
            )
        
        logger.info(f"Published Credential Template: {template_id}")
        return saved
    
    async def unpublish(
        self,
        template_id: str,
        reason: str | None = None,
    ) -> CredentialTemplate:
        """
        Unpublish (archive) a credential template.
        
        Args:
            template_id: Template to unpublish
            reason: Optional reason for unpublishing
        
        Returns:
            Archived credential template
        
        Raises:
            ValueError: If template not found
        """
        template = await self._repository.get(template_id)
        if not template:
            raise ValueError(f"Credential Template '{template_id}' not found")
        
        template.status = "ARCHIVED"
        if reason and hasattr(template, "metadata"):
            template.metadata["archive_reason"] = reason
        
        template.touch()
        saved = await self._repository.save(template)
        
        logger.info(f"Archived Credential Template: {template_id}" + (f" - {reason}" if reason else ""))
        return saved
    
    async def _validate_for_publish(
        self,
        template: CredentialTemplate,
    ) -> list[str]:
        """
        Validate that a template meets all requirements for publishing.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        # Check for application template (recommended for application-based issuance)
        if not template.application_template_id:
            errors.append(
                "Application Template is required for MVP application-based issuance workflows. "
                "Set application_template_id or use direct issuance flows."
            )
        
        # Check for compliance profile and validate OBv3 if applicable
        if template.compliance_profile_id and self._compliance_profile_repository:
            compliance_profile = await self._compliance_profile_repository.get(
                template.compliance_profile_id
            )
            
            if compliance_profile:
                # Validate OBv3 requirements
                template_dict = {
                    "claims": [claim.to_dict() if hasattr(claim, "to_dict") else claim for claim in template.claims],
                    "format": template.format.value if hasattr(template.format, "value") else template.format,
                    "issuer_key_id": getattr(template, "issuer_key_ids", [None])[0] if getattr(template, "issuer_key_ids", None) else None,
                    "issuer_certificate_chain_pem": getattr(template, "issuer_certificate_chain_pem", None),
                    "issuer_did": getattr(template, "issuer_did", None),
                }
                
                compliance_dict = {
                    "code": getattr(compliance_profile, 'compliance_code', getattr(compliance_profile, 'code', None)),
                    "credential_format": compliance_profile.credential_format if hasattr(compliance_profile, "credential_format") else None,
                }
                
                is_valid, obv3_errors = self._obv3_validator.validate_full_template(
                    template_dict,
                    compliance_dict,
                )
                
                if not is_valid:
                    errors.extend(obv3_errors)
            else:
                errors.append(f"Compliance Profile '{template.compliance_profile_id}' not found")
        
        # Check for issuer artifacts
        has_issuer_artifact = any([
            getattr(template, "issuer_key_ids", None),
            getattr(template, "issuer_certificate_chain_pem", None),
            getattr(template, "issuer_did", None),
        ])
        
        if not has_issuer_artifact:
            errors.append(
                "At least one issuer artifact required: "
                "issuer_key_ids, issuer_certificate_chain_pem, or issuer_did"
            )
        
        # Check trust profile compatibility (if both are set)
        if template.trust_profile_id and template.compliance_profile_id:
            # TODO: Add trust profile validation logic
            # This would check if the trust profile's validation rules are compatible
            # with the compliance profile's requirements
            logger.warning(
                "Trust/compliance profile compatibility check not implemented — "
                "template %s accepted without cross-validation (trust_profile=%s, compliance_profile=%s)",
                template.id, template.trust_profile_id, template.compliance_profile_id,
            )
        
        return errors
