"""
Digital Identity API Schemas

Pydantic models for API request/response validation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# Compliance Profile Schemas
# =============================================================================

class ComplianceProfileBase(BaseModel):
    """Base schema for Compliance Profile."""
    
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    compliance_code: str = Field(..., min_length=1, max_length=100)
    credential_format: str = Field(..., description="Credential format: MDOC, SD_JWT_VC, VC_JWT, JSON_LD, ZK_MDOC")
    issuance_protocol: str | None = Field(default=None, description="Issuance protocol: OID4VCI_PRE_AUTH, OID4VCI_AUTH_CODE, DIRECT")
    issuer_artifact_requirements: dict[str, Any] | None = None
    default_verification_rules: list[dict[str, Any]] = Field(default_factory=list)
    trust_profile_constraints: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComplianceProfileCreate(ComplianceProfileBase):
    """Schema for creating a Compliance Profile."""
    pass


class ComplianceProfileUpdate(BaseModel):
    """Schema for updating a Compliance Profile."""
    
    name: str | None = None
    description: str | None = None
    compliance_code: str | None = None
    credential_format: str | None = None
    issuance_protocol: str | None = None
    issuer_artifact_requirements: dict[str, Any] | None = None
    default_verification_rules: list[dict[str, Any]] | None = None
    trust_profile_constraints: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class ComplianceProfileResponse(ComplianceProfileBase):
    """Schema for Compliance Profile response."""
    
    id: str
    is_system: bool
    created_at: datetime
    updated_at: datetime
    version: int
    
    class Config:
        from_attributes = True


# =============================================================================
# Application Template Schemas
# =============================================================================

class ApplicationTemplateBase(BaseModel):
    """Base schema for Application Template."""
    
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    credential_template_id: str = Field(..., description="ID of the Credential Template")
    compliance_profile_id: str = Field(..., description="ID of the Compliance Profile")
    evidence_requirements: list[dict[str, Any]] = Field(default_factory=list)
    claim_verification_rules: list[dict[str, Any]] = Field(default_factory=list)
    issuer_key_id: str | None = Field(None, description="Reference to signing key in KeyVault")
    issuer_certificate_chain_pem: str | None = Field(None, description="PEM-encoded certificate chain")
    issuer_did: str | None = Field(None, description="DID for issuer")
    auto_generate_artifacts: bool = Field(
        default=True,
        description="Auto-generate missing artifacts in development"
    )
    approval_strategy: str = Field(default="auto", description="Approval strategy: auto, manual, rules_based, external")
    application_validity_days: int = Field(default=30, ge=1, le=365)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApplicationTemplateCreate(ApplicationTemplateBase):
    """Schema for creating an Application Template."""
    pass


class ApplicationTemplateUpdate(BaseModel):
    """Schema for updating an Application Template."""
    
    name: str | None = None
    description: str | None = None
    credential_template_id: str | None = None
    compliance_profile_id: str | None = None
    evidence_requirements: list[dict[str, Any]] | None = None
    claim_verification_rules: list[dict[str, Any]] | None = None
    issuer_key_id: str | None = None
    issuer_certificate_chain_pem: str | None = None
    issuer_did: str | None = None
    auto_generate_artifacts: bool | None = None
    approval_strategy: str | None = None
    application_validity_days: int | None = Field(None, ge=1, le=365)
    metadata: dict[str, Any] | None = None


class ApplicationTemplateResponse(ApplicationTemplateBase):
    """Schema for Application Template response."""
    
    id: str
    created_at: datetime
    updated_at: datetime
    version: int
    
    class Config:
        from_attributes = True


# =============================================================================
# Evidence Requirement Schemas
# =============================================================================

class EvidenceRequirementSchema(BaseModel):
    """Schema for Evidence Requirement."""
    
    evidence_type: str = Field(..., description="Type of evidence required")
    required: bool = True
    provider_config: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    auto_validate: bool = False


class ClaimVerificationRuleSchema(BaseModel):
    """Schema for Claim Verification Rule."""
    
    claim_name: str = Field(..., description="Name of the claim to verify")
    verification_method: str = Field(..., description="Method for verifying claim")
    source_evidence_type: str | None = None
    validation_rules: dict[str, Any] = Field(default_factory=dict)
    required: bool = True
    description: str | None = None


# =============================================================================
# List Response Schemas
# =============================================================================

class ComplianceProfileListResponse(BaseModel):
    """Schema for paginated Compliance Profile list."""
    
    items: list[ComplianceProfileResponse]
    total: int
    page: int = 1
    page_size: int = 50


class ApplicationTemplateListResponse(BaseModel):
    """Schema for paginated Application Template list."""
    
    items: list[ApplicationTemplateResponse]
    total: int
    page: int = 1
    page_size: int = 50


# =============================================================================
# Artifact Validation Schemas
# =============================================================================

class ArtifactValidationRequest(BaseModel):
    """Schema for validating issuer artifacts."""
    
    credential_format: str = Field(..., description="Credential format to validate against")
    issuer_key_id: str | None = None
    issuer_certificate_chain_pem: str | None = None
    issuer_did: str | None = None


class ArtifactValidationResponse(BaseModel):
    """Schema for artifact validation response."""
    
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
