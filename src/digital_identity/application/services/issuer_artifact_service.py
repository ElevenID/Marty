"""
Issuer Artifact Service

Application service for managing issuer cryptographic artifacts.
Handles auto-generation in development and validation in production.
"""

from __future__ import annotations

import logging
from typing import Protocol

from digital_identity.domain.entities import ApplicationTemplate, ComplianceProfile
from digital_identity.domain.value_objects import (
    CredentialFormat,
    CryptoAlgorithm,
    ARTIFACT_REQUIREMENTS,
)

logger = logging.getLogger(__name__)


class KeyVaultClientPort(Protocol):
    """Port for key vault operations."""
    
    async def ensure_key(self, key_id: str, algorithm: str) -> None:
        """Ensure a key exists, creating if necessary."""
        ...
    
    async def key_exists(self, key_id: str) -> bool:
        """Check if a key exists."""
        ...


class KeyManagerPort(Protocol):
    """Port for key management operations."""
    
    def generate_key(self, algorithm: str) -> dict[str, str]:
        """Generate a key pair and return DID + JWK."""
        ...


class IssuerArtifactMissingError(Exception):
    """Raised when required issuer artifacts are missing in production."""
    
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Missing issuer artifacts: {', '.join(errors)}")


class IssuerArtifactService:
    """
    Service for managing issuer cryptographic artifacts.
    
    Implements environment-aware artifact management:
    - Development: Auto-generates missing artifacts via KeyVault.ensure_key()
    - Production: Validates artifacts exist, enforces HSM for sensitive formats
    
    Supports hybrid approach:
    - Compliance profiles define per-format requirements
    - ApplicationTemplate references artifacts or enables auto-generation
    - Service resolves artifacts based on environment
    """
    
    def __init__(
        self,
        key_vault: KeyVaultClientPort,
        key_manager: KeyManagerPort | None = None,
    ):
        self._key_vault = key_vault
        self._key_manager = key_manager
    
    async def ensure_issuer_artifacts(
        self,
        template: ApplicationTemplate,
        compliance_profile: ComplianceProfile,
        environment: str = "development",
    ) -> ApplicationTemplate:
        """
        Ensure required issuer artifacts exist for the application template.
        
        Args:
            template: Application template to validate/update
            compliance_profile: Compliance profile with artifact requirements
            environment: Deployment environment ("development", "staging", "production")
        
        Returns:
            Updated application template with artifacts
        
        Raises:
            IssuerArtifactMissingError: If artifacts missing in production
        """
        requirements = compliance_profile.get_artifact_requirements()
        
        # Validate production environments
        if environment == "production":
            errors = self._validate_artifacts(template, requirements)
            if errors:
                logger.error(
                    f"Missing artifacts for template {template.id} in production: {errors}"
                )
                raise IssuerArtifactMissingError(errors)
            logger.info(f"Validated issuer artifacts for template {template.id}")
            return template
        
        # Auto-generate for development if enabled
        if template.auto_generate_artifacts and environment != "production":
            await self._auto_generate_artifacts(template, requirements)
            logger.info(f"Auto-generated artifacts for template {template.id}")
        else:
            # Still validate even in dev if auto-generate is disabled
            errors = self._validate_artifacts(template, requirements)
            if errors:
                logger.warning(
                    f"Artifacts missing for template {template.id}: {errors}"
                )
        
        return template
    
    def _validate_artifacts(
        self,
        template: ApplicationTemplate,
        requirements,
    ) -> list[str]:
        """
        Validate that required artifacts are present.
        
        Returns list of error messages for missing artifacts.
        """
        errors = []
        
        if requirements.requires_x509_cert and not template.issuer_certificate_chain_pem:
            errors.append(
                f"X.509 certificate required for {template.credential_type}"
            )
        
        if requirements.requires_did and not template.issuer_did:
            errors.append(
                f"Issuer DID required for {template.credential_type}"
            )
        
        return errors
    
    async def _auto_generate_artifacts(
        self,
        template: ApplicationTemplate,
        requirements,
    ) -> None:
        """
        Auto-generate missing artifacts for development.
        
        Uses KeyVault.ensure_key() pattern to create keys if missing.
        """
        # Generate signing key if required and missing
        if not template.issuer_key_id:
            key_id = f"app-template-{template.id}-signing"
            algorithm = requirements.recommended_algorithms[0]  # Use first recommended
            
            await self._key_vault.ensure_key(key_id, algorithm.value)
            template.issuer_key_id = key_id
            logger.debug(f"Generated signing key: {key_id} ({algorithm})")
        
        # Generate DID if required and missing
        if requirements.requires_did and not template.issuer_did and self._key_manager:
            algorithm = requirements.recommended_algorithms[0]
            key_pair = self._key_manager.generate_key(algorithm.value)
            template.issuer_did = key_pair.get("did")
            logger.debug(f"Generated issuer DID: {template.issuer_did}")
        
        # Note: Certificate chain generation is complex and typically requires
        # external CA infrastructure. For mDoc, this would involve:
        # 1. Generating a Document Signer Certificate (DSC)
        # 2. Getting it signed by an IACA
        # 3. Building the full chain: DSC -> IACA -> CSCA
        # This is intentionally not auto-generated in dev mode.
        if requirements.requires_x509_cert and not template.issuer_certificate_chain_pem:
            logger.warning(
                f"Certificate chain required for {template.credential_type} but cannot be auto-generated. "
                "Manual certificate provisioning required."
            )
    
    async def validate_artifacts_for_format(
        self,
        credential_format: CredentialFormat,
        issuer_key_id: str | None,
        issuer_certificate_chain_pem: str | None,
        issuer_did: str | None,
    ) -> list[str]:
        """
        Validate artifacts for a specific credential format.
        
        Returns list of error messages if validation fails.
        """
        requirements = ARTIFACT_REQUIREMENTS.get(
            credential_format,
            ARTIFACT_REQUIREMENTS[CredentialFormat.SD_JWT_VC],
        )
        
        errors = []
        
        if requirements.requires_x509_cert and not issuer_certificate_chain_pem:
            errors.append(f"X.509 certificate required for {credential_format}")
        
        if requirements.requires_did and not issuer_did:
            errors.append(f"Issuer DID required for {credential_format}")
        
        return errors
