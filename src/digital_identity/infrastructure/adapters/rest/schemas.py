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
    
    check_mode: str = Field(default="HARD_FAIL", description="Revocation check mode: HARD_FAIL, SOFT_FAIL, or SKIP")
    check_ocsp: bool = Field(default=True, description="Check OCSP responders")
    check_crl: bool = Field(default=True, description="Check CRL distribution points")
    check_status_list: bool = Field(default=True, description="Check status lists")
    offline_grace_period_seconds: int = Field(default=86400, description="Grace period when offline (seconds)")
    cache_ttl_seconds: int = Field(default=3600, description="Cache TTL for revocation responses (seconds)")


class TimePolicySchema(BaseModel):
    """Time validation policy configuration."""
    
    clock_skew_seconds: int = Field(default=300, description="Allowed clock skew in seconds")
    max_credential_age_seconds: int | None = Field(default=None, description="Maximum age of credential in seconds")
    require_freshness: bool = Field(default=False, description="Require freshness_window_seconds to be met")
    freshness_window_seconds: int | None = Field(default=None, description="Max seconds since credential was last refreshed (if require_freshness)")


class TrustProfileCreate(BaseModel):
    """Schema for creating a Trust Profile."""
    
    organization_id: str = Field(..., description="Organization UUID this profile belongs to")
    name: str = Field(..., min_length=1, max_length=255, description="Unique name for the trust profile")
    description: str | None = Field(default=None, description="Human-readable description")
    profile_type: str = Field(..., description="Profile type: ICAO, AAMVA, EUDI, or CUSTOM")
    trust_sources: list[dict[str, Any]] = Field(default_factory=list, description="Trust anchor sources")
    allowed_algorithms: list[str] = Field(default_factory=list, description="Allowed cryptographic algorithms")
    supported_formats: list[str] = Field(default_factory=list, description="Allowed credential formats")
    revocation_policy: RevocationPolicySchema | None = None
    time_policy: TimePolicySchema | None = None
    revocation_profile_id: str | None = Field(default=None, description="Optional RevocationProfile UUID")
    allowed_issuers: list[str] | None = Field(default=None, description="Allowlist of issuer identifiers")
    denied_issuers: list[str] | None = Field(default=None, description="Denylist of issuer identifiers")
    enabled: bool = Field(default=True, description="Whether the profile is active")
    auto_generated: bool = Field(default=False, description="Created by onboarding wizard vs manual")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class TrustProfileUpdate(BaseModel):
    """Schema for updating a Trust Profile."""
    
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    trust_sources: list[dict[str, Any]] | None = None
    allowed_algorithms: list[str] | None = None
    supported_formats: list[str] | None = None
    revocation_policy: RevocationPolicySchema | None = None
    time_policy: TimePolicySchema | None = None
    revocation_profile_id: str | None = None
    allowed_issuers: list[str] | None = None
    denied_issuers: list[str] | None = None
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None


class TrustProfileResponse(BaseModel):
    """Schema for Trust Profile response."""
    
    id: str
    organization_id: str
    name: str
    description: str | None
    profile_type: str
    enabled: bool
    trust_sources: list[dict[str, Any]]
    allowed_algorithms: list[str]
    supported_formats: list[str]
    revocation_policy: dict[str, Any]
    time_policy: dict[str, Any]
    revocation_profile_id: str | None
    allowed_issuers: list[str] | None
    denied_issuers: list[str] | None
    compliance_status: str
    auto_generated: bool
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
    """Validity rules configuration (spec shape)."""
    
    ttl_seconds: int = Field(default=31536000, ge=1, description="Default validity period in seconds")
    renewable: bool = Field(default=True, description="Allow credential reissuance")
    reissue_within_seconds: int | None = Field(default=None, ge=0, description="Seconds before expiry to allow reissue")
    not_before_offset_seconds: int = Field(default=0, ge=0, description="Not-before offset in seconds")


class CredentialTemplateCreate(BaseModel):
    """Schema for creating a Credential Template."""
    
    organization_id: str = Field(..., description="Organization UUID")
    name: str = Field(..., min_length=1, max_length=255, description="Template name")
    description: str | None = None
    credential_type: str = Field(..., description="Unique credential type identifier")
    compliance_profile_id: str = Field(..., description="Compliance profile UUID")
    vct: str | None = Field(default=None, description="SD-JWT VC type string")
    credential_payload_format: str = Field(default="SD_JWT_VC", description="Credential format: SD_JWT_VC, MDOC, VC_JWT, JSON_LD")
    claims: list[ClaimDefinitionSchema] = Field(default_factory=list, description="Claim definitions")
    validity_rules: ValidityRulesSchema | None = None
    trust_profile_id: str | None = Field(default=None, description="Reference to trust profile")
    revocation_profile_id: str | None = Field(default=None, description="Reference to revocation profile")
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
    organization_id: str
    name: str
    description: str | None
    credential_type: str
    compliance_profile_id: str | None
    vct: str | None = None
    credential_payload_format: str
    claims: list[dict[str, Any]]
    validity_rules: dict[str, Any]
    trust_profile_id: str | None
    revocation_profile_id: str | None = None
    namespace: str | None
    status: str
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
    """Freshness requirements (spec shape: max_age_seconds, require_not_revoked, revocation_grace_seconds)."""
    
    max_age_seconds: int | None = Field(default=None, ge=1, description="Max credential age in seconds")
    require_not_revoked: bool = Field(default=False, description="Require credential not revoked")
    revocation_grace_seconds: int | None = Field(default=None, ge=0, description="Grace period for revocation checks")


class PresentationPolicyCreate(BaseModel):
    """Schema for creating a Presentation Policy."""
    
    name: str = Field(..., min_length=1, max_length=255, description="Policy name")
    description: str | None = None
    purpose: str = Field(..., description="Purpose statement shown to user")
    accepted_credential_types: list[str] = Field(..., description="Accepted credential types")
    required_claims: list[RequiredClaimSchema] = Field(default_factory=list, description="Required claims")
    holder_binding: dict[str, Any] = Field(default_factory=lambda: {"required": False}, description="Holder binding config: {required, binding_methods, nonce_required}")
    trust_profile_id: str | None = None
    allowed_issuers: list[str] = Field(default_factory=list, description="Explicit issuer DID/certificate allowlist")
    freshness_requirements: FreshnessRequirementsSchema | None = None
    prefer_predicates: bool = Field(default=False, description="Prefer predicates over full values")
    single_presentation: bool = Field(default=False, description="Require single presentation")
    derived_attribute_preferences: dict[str, str] = Field(default_factory=dict, description="Map raw claims to preferred derived forms")
    credential_ranking_strategy: str = Field(default="FRESHEST_FIRST", description="Credential ranking strategy")
    credential_ranking_weights: dict[str, float] = Field(default_factory=dict, description="Custom ranking weights")
    metadata: dict[str, Any] = Field(default_factory=dict)


class PresentationPolicyUpdate(BaseModel):
    """Schema for updating a Presentation Policy."""
    
    name: str | None = None
    description: str | None = None
    purpose: str | None = None
    accepted_credential_types: list[str] | None = None
    required_claims: list[RequiredClaimSchema] | None = None
    holder_binding: str | dict[str, Any] | None = None
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
    holder_binding: dict[str, Any]
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
    """UX configuration (spec shape)."""
    
    language: str = Field(default="en-US", description="Default language")
    signage_text: dict[str, str] | None = Field(default=None, description="Multilingual signage text")
    operator_mode: bool = Field(default=False, description="Enable operator mode")
    accessibility_mode: bool = Field(default=False, description="Enable accessibility mode")
    theme: str = Field(default="light", description="UI theme: light, dark, high_contrast")


class UpdatePolicySchema(BaseModel):
    """Update policy configuration (spec shape)."""
    
    channel: str = Field(default="stable", description="Update channel: stable, beta, pinned")
    pinned_version: str | None = Field(default=None, description="Pinned version")
    auto_update: bool = Field(default=True, description="Enable auto-updates")


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
    
    organization_id: str = Field(..., description="Organization UUID this profile belongs to")
    name: str = Field(..., min_length=1, max_length=255, description="Profile name")
    description: str | None = None
    site_id: str | None = Field(default=None, description="Unique site identifier")
    enabled_flow_ids: list[str] = Field(default_factory=list, description="Enabled flow IDs")
    default_presentation_policy_id: str | None = None
    network_mode: str = Field(default="ONLINE", description="Network mode: ONLINE, OFFLINE, or HYBRID")
    key_access_mode: str = Field(default="KEY_VAULT", description="Key access mode: KEY_VAULT, HSM, DEVICE_KEYSTORE")
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
    organization_id: str
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
    
    organization_id: str = Field(..., description="Organization UUID")
    name: str = Field(..., min_length=1, max_length=255, description="Flow name")
    description: str | None = None
    flow_type: str = Field(..., description="Flow type identifier")
    trust_profile_id: str | None = None
    credential_template_id: str | None = None
    application_template_id: str | None = None
    presentation_policy_id: str | None = None
    deployment_profile_ids: list[str] = Field(default_factory=list)
    approval_strategy: str = Field(default="AUTO", description="Approval strategy: AUTO, MANUAL, RULES_BASED, EXTERNAL")
    enabled: bool = Field(default=True)
    status: str = Field(default="DRAFT", description="Flow status: DRAFT, ACTIVE, PAUSED, ARCHIVED")
    hooks: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    trigger: dict[str, Any] | None = Field(default=None, description="Trigger config: {trigger_type, config}")
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
    organization_id: str
    name: str
    description: str | None
    flow_type: str
    trust_profile_id: str | None
    credential_template_id: str | None
    application_template_id: str | None = None
    presentation_policy_id: str | None
    deployment_profile_ids: list[str]
    approval_strategy: str
    enabled: bool
    status: str
    hooks: dict[str, list[dict[str, Any]]]
    trigger: dict[str, Any] | None = None
    flow_category: str  # Derived from flow_type (read-only)
    steps: list[str]  # Fixed protocol steps (gateway extension)
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
    flow_type: str
    organization_id: str
    status: str
    current_step: str | None
    current_step_index: int
    step_results: dict[str, Any]
    context_data: dict[str, Any]
    issued_credential_id: str | None
    started_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime | None
    error_code: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version: int

    class Config:
        from_attributes = True


# ---------------------------------------------------------
# Issuer Registry Schemas
# ---------------------------------------------------------

class IssuerCreate(BaseModel):
    """Schema for creating an Issuer."""
    
    issuer_id: str = Field(..., min_length=1, max_length=255, description="Unique issuer identifier (DID, domain, etc.)")
    display_name: str = Field(..., min_length=1, max_length=255, description="Human-readable name")
    issuer_type: str = Field(default="ORGANIZATION", description="Issuer type: ORGANIZATION, GOVERNMENT, DEVICE")
    description: str | None = Field(default=None, description="Optional description")
    organization_id: str | None = Field(default=None, description="Organization ID (NULL for global issuers)")
    trust_anchor_id: str | None = Field(default=None, description="Optional trust anchor linkage")
    is_system_issuer: bool = Field(default=False, description="System issuer (auto-visible to all orgs)")
    compliance_status: str = Field(default="COMPLIANT", description="Compliance status")
    accreditation_body: str | None = Field(default=None, description="Accreditation body")
    valid_from: datetime | None = Field(default=None, description="Validity start (defaults to now)")
    valid_until: datetime | None = Field(default=None, description="Validity end (NULL = indefinite)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class IssuerUpdate(BaseModel):
    """Schema for updating an Issuer."""
    
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    trust_anchor_id: str | None = None
    compliance_status: str | None = None
    accreditation_body: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    metadata: dict[str, Any] | None = None


class IssuerResponse(BaseModel):
    """Schema for Issuer response."""
    
    id: str
    issuer_id: str
    display_name: str
    issuer_type: str
    description: str | None
    organization_id: str | None
    trust_anchor_id: str | None
    is_system_issuer: bool
    compliance_status: str
    accreditation_body: str | None
    accreditation_date: datetime | None
    valid_from: datetime
    valid_until: datetime | None
    revoked_at: datetime | None
    revocation_reason: str | None
    revoked_by: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version: int
    
    class Config:
        from_attributes = True


class TrustProfileIssuerAdd(BaseModel):
    """Schema for adding an issuer to a trust profile."""
    
    issuer_id: str = Field(..., description="Issuer entity ID")
    trust_level: int = Field(default=100, ge=0, le=100, description="Trust score 0-100")
    cascade_revocation_policy: str = Field(default="MANUAL", description="CASCADE policy: AUTO_CASCADE, MANUAL, NOTIFY_ONLY")
    relationship_status: str = Field(default="TRUSTED", description="Status: TRUSTED, DENIED, UNDER_REVIEW")


class TrustProfileIssuerUpdate(BaseModel):
    """Schema for updating an issuer relationship."""
    
    trust_level: int | None = Field(default=None, ge=0, le=100, description="Trust score 0-100")
    cascade_revocation_policy: str | None = Field(default=None, description="CASCADE policy")
    relationship_status: str | None = Field(default=None, description="Status")
    reason: str | None = Field(default=None, description="Reason for changes")


class TrustProfileIssuerResponse(BaseModel):
    """Schema for trust profile issuer relationship response."""
    
    trust_profile_id: str
    issuer_id: str
    trust_level: int
    relationship_status: str
    cascade_revocation_policy: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class RevocationServicesConfig(BaseModel):
    """Schema for revocation services configuration."""
    
    enabled_methods: list[str] = Field(default_factory=list, description="Enabled methods: CRL, OCSP, STATUS_LIST")
    auto_discover: bool = Field(default=False, description="Auto-discover endpoints from credentials")
    merge_discovered: bool = Field(default=False, description="Merge discovered with explicit endpoints")
    crl_endpoints: list[str] = Field(default_factory=list, description="Explicit CRL endpoints")
    ocsp_urls: list[str] = Field(default_factory=list, description="Explicit OCSP URLs")
    status_list_urls: list[str] = Field(default_factory=list, description="Explicit Status List URLs")


class SystemIssuerOverride(BaseModel):
    """Schema for system issuer override."""
    
    action: str = Field(..., description="Action: DENY or DOWNGRADE")
    trust_level: int | None = Field(default=None, ge=0, le=100, description="Trust level for DOWNGRADE action")
    reason: str | None = Field(default=None, description="Reason for override")


class CascadeOperationConfirm(BaseModel):
    """Schema for confirming cascade operation."""
    
    confirmed_by: str = Field(..., description="Who confirmed the operation")


class CascadeOperationRollback(BaseModel):
    """Schema for rolling back cascade operation."""
    
    rolled_back_by: str = Field(..., description="Who initiated rollback")


class CascadeOperationResponse(BaseModel):
    """Schema for cascade operation response."""
    
    id: str
    operation_type: str
    trigger_entity_type: str
    trigger_entity_id: str
    status: str
    affected_credential_count: int
    affected_credential_ids: list[str]
    requires_confirmation: bool
    confirmed_at: datetime | None
    confirmed_by: str | None
    max_cascade_depth: int
    current_depth: int
    circuit_breaker_threshold: int
    circuit_breaker_triggered: bool
    can_rollback: bool
    rolled_back_at: datetime | None
    rolled_back_by: str | None
    error_message: str | None
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
