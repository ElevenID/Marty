"""
REST API Schemas - Digital Identity

Pydantic models for API request/response serialization.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------
# Trust Profile Schemas
# ---------------------------------------------------------

class RevocationPolicySchema(BaseModel):
    """Revocation policy configuration."""
    
    mode: str = Field(default="hard_fail", description="Revocation check mode: hard_fail, soft_fail, or disabled")
    check_ocsp: bool = Field(default=True, description="Check OCSP responders")
    check_crl: bool = Field(default=True, description="Check CRL distribution points")
    check_status_list: bool = Field(default=True, description="Check status lists")
    offline_grace_period_hours: int = Field(default=24, description="Grace period when offline")
    cache_ttl_hours: int = Field(default=1, description="Cache TTL for revocation responses")


class TimePolicySchema(BaseModel):
    """Time validation policy configuration."""
    
    clock_skew_tolerance_seconds: int = Field(default=300, description="Allowed clock skew in seconds")
    max_credential_age_days: int | None = Field(default=None, description="Maximum age of credential in days")
    require_not_before: bool = Field(default=True, description="Enforce notBefore validation")
    require_not_after: bool = Field(default=True, description="Enforce notAfter validation")


class TrustProfileCreate(BaseModel):
    """Schema for creating a Trust Profile."""
    
    name: str = Field(..., min_length=1, max_length=255, description="Unique name for the trust profile")
    description: str | None = Field(default=None, description="Human-readable description")
    profile_type: str = Field(..., description="Profile type: icao, aamva, eudi, or custom")
    trust_sources: list[dict[str, Any]] = Field(default_factory=list, description="Trust anchor sources")
    allowed_algorithms: list[str] = Field(default_factory=list, description="Allowed cryptographic algorithms")
    allowed_formats: list[str] = Field(default_factory=list, description="Allowed credential formats")
    revocation_policy: RevocationPolicySchema | None = None
    time_policy: TimePolicySchema | None = None
    allowed_issuers: list[str] | None = Field(default=None, description="Allowlist of issuer identifiers")
    denied_issuers: list[str] | None = Field(default=None, description="Denylist of issuer identifiers")
    enabled: bool = Field(default=True, description="Whether the profile is active")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class TrustProfileUpdate(BaseModel):
    """Schema for updating a Trust Profile."""
    
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    trust_sources: list[dict[str, Any]] | None = None
    allowed_algorithms: list[str] | None = None
    allowed_formats: list[str] | None = None
    revocation_policy: RevocationPolicySchema | None = None
    time_policy: TimePolicySchema | None = None
    allowed_issuers: list[str] | None = None
    denied_issuers: list[str] | None = None
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None


class TrustProfileResponse(BaseModel):
    """Schema for Trust Profile response."""
    
    id: str
    name: str
    description: str | None
    profile_type: str
    enabled: bool
    trust_sources: list[dict[str, Any]]
    allowed_algorithms: list[str]
    allowed_formats: list[str]
    revocation_policy: dict[str, Any]
    time_policy: dict[str, Any]
    allowed_issuers: list[str] | None
    denied_issuers: list[str] | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version: int

    class Config:
        from_attributes = True


# ---------------------------------------------------------
# Credential Template Schemas
# ---------------------------------------------------------

class ClaimDefinitionSchema(BaseModel):
    """Claim definition configuration."""
    
    name: str = Field(..., description="Claim name")
    display_name: str = Field(..., description="Human-readable display name")
    data_type: str = Field(..., description="Data type: string, integer, boolean, date, datetime")
    required: bool = Field(default=True, description="Whether this claim is required")
    selectively_disclosable: bool = Field(default=True, description="Whether this claim can be selectively disclosed")
    derived_from: str | None = Field(default=None, description="Source claim for derived/predicate claims")
    predicate_type: str | None = Field(default=None, description="Predicate type: age_over, date_before, etc.")
    predicate_value: Any | None = Field(default=None, description="Predicate comparison value")
    validation_regex: str | None = Field(default=None, description="Regex for value validation")
    description: str | None = Field(default=None, description="Claim description")


class ValidityRulesSchema(BaseModel):
    """Validity rules configuration."""
    
    default_ttl_days: int = Field(default=365, description="Default validity period in days")
    max_ttl_days: int | None = Field(default=None, description="Maximum allowed validity")
    min_ttl_hours: int = Field(default=1, description="Minimum validity period in hours")
    allow_reissue: bool = Field(default=True, description="Allow credential reissuance")
    reissue_before_expiry_days: int = Field(default=30, description="Days before expiry to allow reissue")


class CredentialTemplateCreate(BaseModel):
    """Schema for creating a Credential Template."""
    
    name: str = Field(..., min_length=1, max_length=255, description="Template name")
    description: str | None = None
    credential_type: str = Field(..., description="Unique credential type identifier")
    schema_uri: str | None = Field(default=None, description="Schema URI reference")
    claims: list[ClaimDefinitionSchema] = Field(default_factory=list, description="Claim definitions")
    validity_rules: ValidityRulesSchema | None = None
    issuer_key_ids: list[str] | None = Field(default=None, description="Authorized issuer key IDs")
    trust_profile_id: str | None = Field(default=None, description="Reference to trust profile")
    format: str = Field(default="sd_jwt_vc", description="Credential format")
    namespace: str | None = Field(default=None, description="Namespace for mDL/mdocs")
    display: dict[str, Any] = Field(default_factory=dict, description="Display configuration")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class CredentialTemplateUpdate(BaseModel):
    """Schema for updating a Credential Template."""
    
    name: str | None = None
    description: str | None = None
    schema_uri: str | None = None
    claims: list[ClaimDefinitionSchema] | None = None
    validity_rules: ValidityRulesSchema | None = None
    issuer_key_ids: list[str] | None = None
    trust_profile_id: str | None = None
    format: str | None = None
    namespace: str | None = None
    display: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class CredentialTemplateResponse(BaseModel):
    """Schema for Credential Template response."""
    
    id: str
    name: str
    description: str | None
    credential_type: str
    schema_uri: str | None
    claims: list[dict[str, Any]]
    validity_rules: dict[str, Any]
    issuer_key_ids: list[str] | None
    trust_profile_id: str | None
    format: str
    namespace: str | None
    display: dict[str, Any]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version: int

    class Config:
        from_attributes = True


# ---------------------------------------------------------
# Presentation Policy Schemas
# ---------------------------------------------------------

class RequiredClaimSchema(BaseModel):
    """Required claim configuration."""
    
    claim_name: str = Field(..., description="Name of the required claim")
    credential_type: str = Field(..., description="Credential type containing this claim")
    accept_predicate: bool = Field(default=True, description="Accept predicate proofs")
    required_value: Any | None = Field(default=None, description="Required value (for matching)")


class FreshnessRequirementsSchema(BaseModel):
    """Freshness requirements configuration."""
    
    max_credential_age_days: int | None = Field(default=None, description="Max credential age in days")
    max_proof_age_seconds: int = Field(default=300, description="Max age of proof")
    require_live_revocation_check: bool = Field(default=True, description="Require live revocation check")


class PresentationPolicyCreate(BaseModel):
    """Schema for creating a Presentation Policy."""
    
    name: str = Field(..., min_length=1, max_length=255, description="Policy name")
    description: str | None = None
    purpose: str = Field(..., description="Purpose statement shown to user")
    accepted_credential_types: list[str] = Field(..., description="Accepted credential types")
    required_claims: list[RequiredClaimSchema] = Field(default_factory=list, description="Required claims")
    holder_binding: str = Field(default="session_nonce", description="Holder binding method")
    trust_profile_id: str | None = None
    allowed_issuers: list[str] = Field(default_factory=list, description="Explicit issuer DID/certificate allowlist")
    freshness_requirements: FreshnessRequirementsSchema | None = None
    prefer_predicates: bool = Field(default=True, description="Prefer predicates over full values")
    single_presentation: bool = Field(default=False, description="Require single presentation")
    derived_attribute_preferences: dict[str, str] = Field(default_factory=dict, description="Map raw claims to preferred derived forms")
    credential_ranking_strategy: str = Field(default="freshest_first", description="Credential ranking strategy")
    credential_ranking_weights: dict[str, float] = Field(default_factory=dict, description="Custom ranking weights")
    metadata: dict[str, Any] = Field(default_factory=dict)


class PresentationPolicyUpdate(BaseModel):
    """Schema for updating a Presentation Policy."""
    
    name: str | None = None
    description: str | None = None
    purpose: str | None = None
    accepted_credential_types: list[str] | None = None
    required_claims: list[RequiredClaimSchema] | None = None
    holder_binding: str | None = None
    trust_profile_id: str | None = None
    allowed_issuers: list[str] | None = None
    freshness_requirements: FreshnessRequirementsSchema | None = None
    prefer_predicates: bool | None = None
    single_presentation: bool | None = None
    derived_attribute_preferences: dict[str, str] | None = None
    credential_ranking_strategy: str | None = None
    credential_ranking_weights: dict[str, float] | None = None
    metadata: dict[str, Any] | None = None


class PresentationPolicyResponse(BaseModel):
    """Schema for Presentation Policy response."""
    
    id: str
    name: str
    description: str | None
    purpose: str
    accepted_credential_types: list[str]
    required_claims: list[dict[str, Any]]
    holder_binding: str
    trust_profile_id: str | None
    allowed_issuers: list[str]
    freshness_requirements: dict[str, Any]
    prefer_predicates: bool
    single_presentation: bool
    derived_attribute_preferences: dict[str, str]
    credential_ranking_strategy: str
    credential_ranking_weights: dict[str, float]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version: int

    class Config:
        from_attributes = True


# ---------------------------------------------------------
# Deployment Profile Schemas
# ---------------------------------------------------------

class UXConfigSchema(BaseModel):
    """UX configuration."""
    
    language: str = Field(default="en", description="Default language")
    theme: str = Field(default="default", description="UI theme")
    show_operator_mode: bool = Field(default=False, description="Show operator controls")
    accessibility_enabled: bool = Field(default=True, description="Enable accessibility features")
    custom_branding: dict[str, Any] = Field(default_factory=dict, description="Branding customization")
    signage_text: dict[str, str] | None = Field(default=None, description="Multilingual signage text")


class UpdatePolicySchema(BaseModel):
    """Update policy configuration."""
    
    auto_update: bool = Field(default=True, description="Enable auto-updates")
    update_channel: str = Field(default="stable", description="Update channel")
    rollout_percentage: int = Field(default=100, ge=0, le=100, description="Rollout percentage")
    version_pinned: str | None = Field(default=None, description="Pinned version")
    rollout_ring: str | None = Field(default=None, description="Named rollout ring")


class LaneCreate(BaseModel):
    """Schema for creating a Lane."""
    
    name: str = Field(..., min_length=1, max_length=255, description="Lane name (e.g., 'Gate 12', 'Lane A')")
    default_policy_id: str | None = Field(default=None, description="Optional lane-specific policy override")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional configuration")


class LaneUpdate(BaseModel):
    """Schema for updating a Lane."""
    
    name: str | None = None
    default_policy_id: str | None = None
    metadata: dict[str, Any] | None = None


class LaneDeviceAssignment(BaseModel):
    """Schema for assigning devices to a lane."""
    
    device_ids: list[str] = Field(..., description="List of device IDs to assign to the lane")


class LaneResponse(BaseModel):
    """Schema for Lane response."""
    
    id: str
    name: str
    deployment_profile_id: str
    default_policy_id: str | None
    device_ids: list[str]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version: int

    class Config:
        from_attributes = True


class DeploymentProfileCreate(BaseModel):
    """Schema for creating a Deployment Profile."""
    
    name: str = Field(..., min_length=1, max_length=255, description="Profile name")
    description: str | None = None
    site_id: str | None = Field(default=None, description="Unique site identifier")
    enabled_flow_ids: list[str] = Field(default_factory=list, description="Enabled flow IDs")
    default_presentation_policy_id: str | None = None
    network_mode: str = Field(default="online", description="Network mode: online, offline, or hybrid")
    key_access_mode: str = Field(default="key_vault", description="Key access mode")
    ux_config: UXConfigSchema | None = None
    update_policy: UpdatePolicySchema | None = None
    offline_cache_ttl_hours: int = Field(default=24, ge=1, description="Offline cache TTL")
    biometric_required: bool = Field(default=False, description="Require biometric auth")
    audit_all_events: bool = Field(default=True, description="Audit all events")
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeploymentProfileUpdate(BaseModel):
    """Schema for updating a Deployment Profile."""
    
    name: str | None = None
    description: str | None = None
    site_id: str | None = None
    enabled_flow_ids: list[str] | None = None
    default_presentation_policy_id: str | None = None
    network_mode: str | None = None
    key_access_mode: str | None = None
    ux_config: UXConfigSchema | None = None
    update_policy: UpdatePolicySchema | None = None
    offline_cache_ttl_hours: int | None = None
    biometric_required: bool | None = None
    audit_all_events: bool | None = None
    metadata: dict[str, Any] | None = None


class DeploymentProfileResponse(BaseModel):
    """Schema for Deployment Profile response."""
    
    id: str
    name: str
    description: str | None
    site_id: str | None
    enabled_flow_ids: list[str]
    default_presentation_policy_id: str | None
    network_mode: str
    key_access_mode: str
    ux_config: dict[str, Any]
    update_policy: dict[str, Any]
    offline_cache_ttl_hours: int
    biometric_required: bool
    audit_all_events: bool
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version: int

    class Config:
        from_attributes = True


# ---------------------------------------------------------
# Flow Schemas
# ---------------------------------------------------------

class FlowCreate(BaseModel):
    """Schema for creating a Flow."""
    
    name: str = Field(..., min_length=1, max_length=255, description="Flow name")
    description: str | None = None
    flow_type: str = Field(..., description="Flow type identifier")
    trust_profile_id: str | None = None
    credential_template_id: str | None = None
    presentation_policy_id: str | None = None
    deployment_profile_ids: list[str] = Field(default_factory=list)
    approval_strategy: str = Field(default="auto", description="Approval strategy: auto, manual, rules_based, external")
    enabled: bool = Field(default=True)
    hooks: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FlowUpdate(BaseModel):
    """Schema for updating a Flow."""
    
    name: str | None = None
    description: str | None = None
    trust_profile_id: str | None = None
    credential_template_id: str | None = None
    presentation_policy_id: str | None = None
    deployment_profile_ids: list[str] | None = None
    approval_strategy: str | None = None
    enabled: bool | None = None
    hooks: dict[str, list[dict[str, Any]]] | None = None
    metadata: dict[str, Any] | None = None


class FlowResponse(BaseModel):
    """Schema for Flow response."""
    
    id: str
    name: str
    description: str | None
    flow_type: str
    trust_profile_id: str | None
    credential_template_id: str | None
    presentation_policy_id: str | None
    deployment_profile_ids: list[str]
    approval_strategy: str
    enabled: bool
    hooks: dict[str, list[dict[str, Any]]]
    steps: list[str]  # Fixed protocol steps
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version: int

    class Config:
        from_attributes = True


# ---------------------------------------------------------
# Flow Execution Schemas
# ---------------------------------------------------------

class FlowExecutionStart(BaseModel):
    """Schema for starting a flow execution."""
    
    context_data: dict[str, Any] = Field(default_factory=dict, description="Initial context data")
    metadata: dict[str, Any] = Field(default_factory=dict)


class FlowExecutionApproval(BaseModel):
    """Schema for approving/rejecting a flow execution."""
    
    reason: str | None = Field(default=None, description="Reason for approval/rejection")


class FlowExecutionResponse(BaseModel):
    """Schema for Flow Execution response."""
    
    id: str
    flow_id: str
    status: str
    current_step: str | None
    current_step_index: int
    step_results: dict[str, Any]
    context_data: dict[str, Any]
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version: int

    class Config:
        from_attributes = True


# ---------------------------------------------------------
# Common Schemas
# ---------------------------------------------------------

class PaginatedResponse(BaseModel):
    """Generic paginated response."""
    
    items: list[Any]
    total: int
    skip: int
    limit: int
    has_more: bool


class ErrorResponse(BaseModel):
    """API error response."""
    
    error: str
    detail: str | None = None
    code: str | None = None
