"""
REST API Schemas - Digital Identity

Pydantic models for API request/response serialization.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------
# Trust Profile Schemas
# ---------------------------------------------------------

class RevocationPolicySchema(BaseModel):
    """Revocation policy configuration (spec: check_mode + cache_ttl_seconds)."""
    
    check_mode: str = Field(default="HARD_FAIL", description="Revocation check mode: HARD_FAIL, SOFT_FAIL, or SKIP")
    cache_ttl_seconds: int = Field(default=300, description="Cache TTL for revocation responses (seconds)")


class TimePolicySchema(BaseModel):
    """Time validation policy configuration."""
    
    clock_skew_seconds: int = Field(default=300, description="Allowed clock skew in seconds")
    max_credential_age_seconds: int | None = Field(default=None, description="Maximum age of credential in seconds")
    require_freshness: bool = Field(default=False, description="Require freshness_window_seconds to be met")
    freshness_window_seconds: int | None = Field(default=None, description="Max seconds since credential was last refreshed (if require_freshness)")


class TrustProfileCreate(BaseModel):
    """Schema for creating a Trust Profile."""
    
    organization_id: str = Field(..., description="Organization UUID this profile belongs to")
    name: str = Field(..., min_length=1, max_length=128, description="Unique name for the trust profile")
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
    revocation_services: dict[str, Any] | None = Field(default=None, description="Revocation service config: {enabled_methods, auto_discover, crl_endpoints, ocsp_urls, status_list_urls}")
    system_issuer_overrides: dict[str, Any] | None = Field(default=None, description="Per-issuer override configuration")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class TrustProfileUpdate(BaseModel):
    """Schema for updating a Trust Profile."""
    
    name: str | None = Field(default=None, min_length=1, max_length=128)
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
    revocation_services: dict[str, Any] | None = None
    system_issuer_overrides: dict[str, Any] | None = None
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
    revocation_services: dict[str, Any] | None
    system_issuer_overrides: dict[str, Any] | None
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
    type: str = Field(..., description="Data type: string, integer, boolean, date, datetime", alias="type")
    required: bool = Field(default=True, description="Whether this claim is required")
    selectively_disclosable: bool = Field(default=False, description="Whether this claim can be selectively disclosed")
    derived_from: str | None = Field(default=None, description="Source claim for derived/predicate claims")
    predicate_type: str | None = Field(default=None, description="Predicate type: age_over, date_before, etc.")
    predicate_value: Any | None = Field(default=None, description="Predicate comparison value")
    validation_regex: str | None = Field(default=None, description="Regex for value validation")
    description: str | None = Field(default=None, description="Claim description")

    model_config = {"populate_by_name": True}


class ValidityRulesSchema(BaseModel):
    """Validity rules configuration (spec shape)."""
    
    ttl_seconds: int = Field(default=31536000, ge=1, description="Default validity period in seconds")
    renewable: bool = Field(default=False, description="Allow credential reissuance")
    reissue_within_seconds: int | None = Field(default=None, ge=0, description="Seconds before expiry to allow reissue")
    not_before_offset_seconds: int = Field(default=0, ge=0, description="Not-before offset in seconds")


class CredentialTemplateCreate(BaseModel):
    """Schema for creating a Credential Template."""
    
    organization_id: str = Field(..., description="Organization UUID")
    name: str = Field(..., min_length=1, max_length=128, description="Template name")
    description: str | None = None
    credential_type: str = Field(..., description="Unique credential type identifier")
    compliance_profile_id: str = Field(..., description="Compliance profile UUID")
    vct: str | None = Field(default=None, description="SD-JWT VC type string")
    credential_payload_format: str = Field(default="SD_JWT_VC", description="Credential format: SD_JWT_VC, MDOC, VC_JWT, JSON_LD")
    claims: list[ClaimDefinitionSchema] = Field(default_factory=list, description="Claim definitions")
    validity_rules: ValidityRulesSchema | None = None
    trust_profile_id: str | None = Field(default=None, description="Reference to trust profile")
    revocation_profile_id: str | None = Field(default=None, description="Reference to revocation profile")
    issuer_key_id: str | None = Field(default=None, description="Reference to signing key in KeyVault/HSM")
    issuer_algorithm: str | None = Field(default=None, description="Signing algorithm: RS256, ES256, EdDSA, BBS_BLS12381_SHA256, etc.")
    key_access_mode: str = Field(default="key_vault", description="Key access mode: key_vault, hsm, local")
    issuer_certificate_chain_pem: str | None = Field(default=None, description="PEM-encoded certificate chain")
    issuer_did: str | None = Field(default=None, description="DID for issuer")
    auto_generate_artifacts: bool = Field(default=False, description="Auto-generate missing artifacts in dev")
    namespace: str | None = Field(default=None, description="Namespace for mDL/mdocs")
    privacy_posture: str | dict[str, Any] = Field(default="selective_disclosure", description="Privacy intent: str (selective_disclosure, full_disclosure, zero_knowledge) or dict with default_disclose_all, prefer_predicates, sd_alg")
    display: dict[str, Any] = Field(default_factory=dict, description="Display configuration")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class CredentialTemplateUpdate(BaseModel):
    """Schema for updating a Credential Template."""
    
    name: str | None = None
    description: str | None = None
    schema_uri: str | None = None
    vct: str | None = None
    status: str | None = Field(default=None, description="DRAFT, ACTIVE, DEPRECATED, ARCHIVED")
    claims: list[ClaimDefinitionSchema] | None = None
    validity_rules: ValidityRulesSchema | None = None
    trust_profile_id: str | None = None
    revocation_profile_id: str | None = None
    issuer_key_id: str | None = None
    issuer_algorithm: str | None = None
    key_access_mode: str | None = None
    issuer_certificate_chain_pem: str | None = None
    issuer_did: str | None = None
    auto_generate_artifacts: bool | None = None
    credential_payload_format: str | None = None
    namespace: str | None = None
    privacy_posture: str | dict[str, Any] | None = None
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
    issuer_key_id: str | None = None
    issuer_algorithm: str | None = None
    key_access_mode: str = "key_vault"
    auto_generate_artifacts: bool = False
    issuer_certificate_chain_pem: str | None = None
    issuer_did: str | None = None
    namespace: str | None
    privacy_posture: dict[str, Any] | None = None
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
    value_constraint: Any | None = Field(default=None, description="Value constraint (for matching)")


class FreshnessRequirementsSchema(BaseModel):
    """Freshness requirements (spec shape: max_age_seconds, require_not_revoked, revocation_grace_seconds)."""
    
    max_age_seconds: int | None = Field(default=None, ge=1, description="Max credential age in seconds")
    require_not_revoked: bool = Field(default=False, description="Require credential not revoked")
    revocation_grace_seconds: int | None = Field(default=None, ge=0, description="Grace period for revocation checks")


class PresentationPolicyCreate(BaseModel):
    """Schema for creating a Presentation Policy."""
    
    organization_id: str = Field(..., description="Organization UUID")
    name: str = Field(..., min_length=1, max_length=128, description="Policy name")
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
    issuer_constraints: dict[str, Any] = Field(default_factory=dict, description="Issuer trust constraints: {min_trust_level, required_compliance_statuses, required_accreditations}")
    fallback_policy: str = Field(default="ACCEPT_RAW", description="Predicate fallback: REQUIRE_PREDICATE, ACCEPT_RAW, DENY")
    supported_circuits: list[str] = Field(default_factory=list, description="Supported ZK circuit identifiers")
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
    issuer_constraints: dict[str, Any] | None = None
    fallback_policy: str | None = None
    supported_circuits: list[str] | None = None
    credential_ranking_strategy: str | None = None
    credential_ranking_weights: dict[str, float] | None = None
    metadata: dict[str, Any] | None = None


class PresentationPolicyResponse(BaseModel):
    """Schema for Presentation Policy response."""
    
    id: str
    organization_id: str
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
    issuer_constraints: dict[str, Any]
    fallback_policy: str
    supported_circuits: list[str]
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
    
    name: str = Field(..., min_length=1, max_length=128, description="Lane name (e.g., 'Gate 12', 'Lane A')")
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
    name: str = Field(..., min_length=1, max_length=128, description="Profile name")
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
    lanes: list[dict[str, Any]] = []
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
    name: str = Field(..., min_length=1, max_length=128, description="Flow name")
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
    status: str | None = Field(default=None, description="Flow status: DRAFT, ACTIVE, PAUSED, ARCHIVED")
    trigger: dict[str, Any] | None = Field(default=None, description="Trigger config: {trigger_type, config}")
    application_template_id: str | None = None
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
# Revocation Profile Schemas
# ---------------------------------------------------------

class RevocationProfileCreate(BaseModel):
    """Schema for creating a Revocation Profile."""
    
    organization_id: str = Field(..., description="Organization UUID")
    name: str = Field(..., min_length=1, max_length=128, description="Profile name")
    revocation_mechanism: list[str] = Field(..., min_length=1, description="Methods: OCSP, CRL, STATUS_LIST_2021, BITSTRING_STATUS_LIST, TOKEN_STATUS_LIST")
    mechanism_priority: list[str] = Field(default_factory=list, description="Preferred check order (subset of revocation_mechanism)")
    check_mode: str = Field(default="ALWAYS", description="Timing mode: ALWAYS, CACHED, OFFLINE_GRACE, DISABLED")
    cache_ttl_seconds: int | None = Field(default=None, ge=1, description="Cache TTL (required when check_mode=CACHED)")
    offline_grace_seconds: int | None = Field(default=None, ge=1, description="Offline grace period (required when check_mode=OFFLINE_GRACE)")
    issuer_config: dict[str, Any] = Field(default_factory=dict, description="Issuer-side config: {auto_allocate_index, batch_update_interval_seconds, list_size, uri_template}")
    status_list_url: str | None = Field(default=None, description="Base URI for published status lists (HTTPS only)")
    metadata: dict[str, Any] = Field(default_factory=dict)


class RevocationProfileUpdate(BaseModel):
    """Schema for updating a Revocation Profile."""
    
    name: str | None = None
    revocation_mechanism: list[str] | None = None
    mechanism_priority: list[str] | None = None
    check_mode: str | None = None
    cache_ttl_seconds: int | None = None
    offline_grace_seconds: int | None = None
    issuer_config: dict[str, Any] | None = None
    status_list_url: str | None = None
    metadata: dict[str, Any] | None = None


class RevocationProfileResponse(BaseModel):
    """Schema for Revocation Profile response."""
    
    id: str
    organization_id: str
    name: str
    revocation_mechanism: list[str]
    mechanism_priority: list[str]
    check_mode: str
    cache_ttl_seconds: int | None
    offline_grace_seconds: int | None
    issuer_config: dict[str, Any]
    status_list_url: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version: int

    class Config:
        from_attributes = True


# ---------------------------------------------------------
# Issued Credential Schemas
# ---------------------------------------------------------

class IssuedCredentialResponse(BaseModel):
    """Schema for Issued Credential response."""
    
    id: str
    credential_id: str
    credential_type: str
    credential_format: str
    flow_execution_id: str
    credential_template_id: str
    application_id: str | None
    revocation_profile_id: str | None
    subject_id: str
    subject_claims_hash: str | None
    issued_at: datetime
    valid_from: datetime | None
    valid_until: datetime | None
    status: str
    status_list_entries: list[dict[str, Any]]
    credential_hash: str | None
    revoked_at: datetime | None
    revocation_reason: str | None
    revoked_by: str | None
    created_at: datetime
    updated_at: datetime
    version: int

    class Config:
        from_attributes = True


class IssuedCredentialRevoke(BaseModel):
    """Schema for revoking an issued credential."""
    
    reason: str = Field(..., description="Reason for revocation")
    revoked_by: str = Field(..., description="Who is revoking the credential")


# ---------------------------------------------------------
# Verification Session Schemas
# ---------------------------------------------------------

class VerificationSessionCreate(BaseModel):
    """Schema for creating a Verification Session."""

    flow_id: str = Field(..., description="Parent flow UUID")
    presentation_policy_id: str = Field(..., description="Policy governing this session")
    flow_instance_id: str | None = Field(default=None, description="Specific flow execution UUID")
    deployment_profile_id: str | None = Field(default=None, description="Deployment profile UUID")
    verifier_nonce: str | None = Field(
        default=None,
        min_length=22,
        description="Base64url-encoded random nonce (min 128 bits / 22 chars)",
    )
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationSessionUpdate(BaseModel):
    """Schema for updating a Verification Session."""

    status: str | None = Field(
        default=None,
        description="PENDING | AWAITING_PRESENTATION | VERIFYING | PASSED | FAILED | EXPIRED | CANCELLED",
    )
    holder_id: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    expires_at: datetime | None = None
    completed_at: datetime | None = None


class VerificationSessionResponse(BaseModel):
    """Schema for Verification Session response."""

    id: str
    flow_id: str
    presentation_policy_id: str
    flow_instance_id: str | None
    deployment_profile_id: str | None
    verifier_nonce: str | None
    holder_id: str | None
    status: str
    result: dict[str, Any] | None
    expires_at: datetime | None
    completed_at: datetime | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    version: int

    class Config:
        from_attributes = True


# ---------------------------------------------------------
# Compliance Profile Schemas
# ---------------------------------------------------------

class ComplianceProfileCreate(BaseModel):
    """Schema for creating a custom Compliance Profile."""

    name: str = Field(..., min_length=1, max_length=255, description="Profile name")
    compliance_code: str = Field(..., min_length=1, max_length=100, description="Unique code e.g. AAMVA_MDL")
    credential_format: str = Field(
        default="SD_JWT_VC",
        description="SD_JWT_VC | MDOC | JWT_VC | LDP_VC",
    )
    organization_id: str | None = Field(default=None, description="Organization UUID (None = global)")
    description: str | None = None
    issuance_protocol: str | None = Field(
        default=None,
        description="OID4VCI_PRE_AUTH | OID4VCI_AUTH_CODE | DIRECT",
    )
    trust_profile_constraints: dict[str, Any] = Field(default_factory=dict)
    discoverable: bool = Field(default=True, description="Visible in profile catalogue")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComplianceProfileUpdate(BaseModel):
    """Schema for updating a custom Compliance Profile."""

    name: str | None = None
    description: str | None = None
    credential_format: str | None = None
    issuance_protocol: str | None = None
    trust_profile_constraints: dict[str, Any] | None = None
    discoverable: bool | None = None
    metadata: dict[str, Any] | None = None


class ComplianceProfileResponse(BaseModel):
    """Schema for Compliance Profile response."""

    id: str
    name: str
    compliance_code: str
    credential_format: str
    organization_id: str | None
    description: str | None
    issuance_protocol: str | None
    trust_profile_constraints: dict[str, Any]
    is_system: bool
    discoverable: bool
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version: int

    class Config:
        from_attributes = True


# ---------------------------------------------------------
# Application Template Schemas
# ---------------------------------------------------------

class ApplicationTemplateCreate(BaseModel):
    """Schema for creating an Application Template."""

    name: str = Field(..., min_length=1, max_length=128, description="Template name")
    organization_id: str | None = Field(default=None, description="Organization UUID")
    description: str | None = None
    status: str = Field(default="DRAFT", description="DRAFT, ACTIVE, or DEPRECATED")
    evidence_requirements: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Evidence items required before issuance",
    )
    form_fields: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Form field definitions for applicant data entry",
    )
    claim_collection_rules: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Rules for collecting claim values from the applicant",
    )
    approval_strategy: str = Field(
        default="AUTO",
        description="AUTO, MANUAL, or RULES_BASED",
    )
    application_validity_days: int = Field(
        default=30,
        ge=1,
        description="Days an application remains valid",
    )
    notifications: dict[str, Any] = Field(default_factory=dict)
    ui_config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApplicationTemplateUpdate(BaseModel):
    """Schema for updating an Application Template."""

    name: str | None = None
    description: str | None = None
    status: str | None = None
    evidence_requirements: list[dict[str, Any]] | None = None
    form_fields: list[dict[str, Any]] | None = None
    claim_collection_rules: list[dict[str, Any]] | None = None
    approval_strategy: str | None = None
    application_validity_days: int | None = Field(default=None, ge=1)
    notifications: dict[str, Any] | None = None
    ui_config: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class ApplicationTemplateResponse(BaseModel):
    """Schema for Application Template response."""

    id: str
    name: str
    organization_id: str | None
    description: str | None
    status: str
    evidence_requirements: list[dict[str, Any]]
    form_fields: list[dict[str, Any]]
    claim_collection_rules: list[dict[str, Any]]
    approval_strategy: str
    application_validity_days: int
    notifications: dict[str, Any]
    ui_config: dict[str, Any]
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


# ---------------------------------------------------------
# Organization Schemas
# ---------------------------------------------------------

class OrganizationCreate(BaseModel):
    """Schema for creating an Organization."""
    
    name: str
    display_name: str
    owner_id: str
    visibility: str = "PRIVATE"
    description: str | None = None
    join_code: str | None = None


class OrganizationUpdate(BaseModel):
    """Schema for updating an Organization."""
    
    display_name: str | None = None
    description: str | None = None
    visibility: str | None = None
    owner_id: str | None = None
    join_code: str | None = None
    status: str | None = None


class OrganizationResponse(BaseModel):
    """Schema for an Organization response."""
    
    id: str
    name: str
    display_name: str
    description: str | None = None
    visibility: str
    owner_id: str
    join_code: str | None = None
    status: str
    created_at: str | datetime
    updated_at: str | datetime


# ---------------------------------------------------------
# Trust Framework Schemas
# ---------------------------------------------------------

class TrustFrameworkCreate(BaseModel):
    """Schema for creating a Trust Framework."""
    
    code: str
    display_name: str
    default_algorithms: list[str]
    default_formats: list[str]
    is_system: bool = True
    description: str | None = None
    pkd_endpoints: dict[str, Any] | None = None
    validation_ruleset: dict[str, Any] | None = None
    sync_config: dict[str, Any] | None = None


class TrustFrameworkUpdate(BaseModel):
    """Schema for updating a Trust Framework."""
    
    display_name: str | None = None
    description: str | None = None
    default_algorithms: list[str] | None = None
    default_formats: list[str] | None = None
    pkd_endpoints: dict[str, Any] | None = None
    validation_ruleset: dict[str, Any] | None = None
    sync_config: dict[str, Any] | None = None


class TrustFrameworkResponse(BaseModel):
    """Schema for a Trust Framework response."""
    
    id: str
    code: str
    display_name: str
    description: str | None = None
    pkd_endpoints: dict[str, Any] = {}
    default_algorithms: list[str] = []
    default_formats: list[str] = []
    validation_ruleset: dict[str, Any] = {}
    sync_config: dict[str, Any] = {}
    is_system: bool = True
    created_at: str
    updated_at: str


# ---------------------------------------------------------
# Organization Trust Profile Schemas
# ---------------------------------------------------------

class OrganizationTrustProfileCreate(BaseModel):
    """Schema for creating an Organization Trust Profile."""
    
    organization_id: str
    framework_id: str
    name: str
    display_name: str | None = None
    description: str | None = None
    enabled: bool = True
    use_case_tags: list[str] | None = None
    compliance_status: str = "SETUP_REQUIRED"
    auto_generated: bool = False
    revocation_policy: dict[str, Any] | None = None
    time_policy: dict[str, Any] | None = None
    allowed_algorithms: list[str] | None = None
    allowed_formats: list[str] | None = None
    allowed_issuers: list[str] | None = None
    denied_issuers: list[str] | None = None
    jurisdiction_filter: list[str] | None = None


class OrganizationTrustProfileUpdate(BaseModel):
    """Schema for updating an Organization Trust Profile."""
    
    display_name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    use_case_tags: list[str] | None = None
    compliance_status: str | None = None
    revocation_policy: dict[str, Any] | None = None
    time_policy: dict[str, Any] | None = None
    allowed_algorithms: list[str] | None = None
    allowed_formats: list[str] | None = None
    allowed_issuers: list[str] | None = None
    denied_issuers: list[str] | None = None
    jurisdiction_filter: list[str] | None = None


class OrganizationTrustProfileResponse(BaseModel):
    """Schema for an Organization Trust Profile response."""
    
    id: str
    organization_id: str
    framework_id: str
    name: str
    display_name: str
    description: str | None = None
    enabled: bool = True
    use_case_tags: list[str] = []
    compliance_status: str = "SETUP_REQUIRED"
    auto_generated: bool = False
    revocation_policy: dict[str, Any] | None = None
    time_policy: dict[str, Any] | None = None
    allowed_algorithms: list[str] | None = None
    allowed_formats: list[str] | None = None
    allowed_issuers: list[str] | None = None
    denied_issuers: list[str] | None = None
    jurisdiction_filter: list[str] | None = None
    created_at: str
    updated_at: str
    version: int = 1


# ---------------------------------------------------------
# Webhook Schemas
# ---------------------------------------------------------

class WebhookCreate(BaseModel):
    """Schema for creating a Webhook."""

    organization_id: str
    name: str = Field(..., min_length=1, max_length=128)
    endpoint_url: str = Field(..., max_length=2048, description="HTTPS endpoint URL")
    events: list[str] = Field(..., min_length=1)
    description: str | None = Field(default=None, max_length=512)
    enabled: bool = True
    api_version: str | None = None
    filter: dict[str, Any] | None = None
    delivery_config: dict[str, Any] | None = None

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint_url(cls, v: str) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(v)
        if parsed.scheme != "https":
            raise ValueError("Webhook endpoint_url must use HTTPS")
        if not parsed.netloc:
            raise ValueError("Webhook endpoint_url must have a valid host")
        return v


class WebhookUpdate(BaseModel):
    """Schema for updating a Webhook."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    endpoint_url: str | None = None
    events: list[str] | None = None
    enabled: bool | None = None
    api_version: str | None = None
    filter: dict[str, Any] | None = None
    delivery_config: dict[str, Any] | None = None
    status: str | None = None


class WebhookResponse(BaseModel):
    """Schema for a Webhook response."""

    id: str
    organization_id: str
    name: str
    description: str | None = None
    endpoint_url: str
    events: list[str]
    signing_secret_masked: str | None = None
    enabled: bool
    api_version: str | None = None
    filter: dict[str, Any] = {}
    delivery_config: dict[str, Any] = {}
    status: str
    failure_count: int = 0
    last_triggered_at: str | None = None
    last_success_at: str | None = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------
# Subscription Schemas
# ---------------------------------------------------------

class SubscriptionCreate(BaseModel):
    """Schema for creating a Subscription."""

    organization_id: str
    name: str = Field(..., min_length=1, max_length=128)
    event_types: list[str] = Field(..., min_length=1)
    delivery: dict[str, Any] = Field(..., description="Channel configuration (channel, url/address, etc.)")
    description: str | None = Field(default=None, max_length=1024)
    filter: dict[str, Any] | None = None
    enabled: bool = True
    retry_policy: dict[str, Any] | None = None


class SubscriptionUpdate(BaseModel):
    """Schema for updating a Subscription."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    event_types: list[str] | None = None
    delivery: dict[str, Any] | None = None
    filter: dict[str, Any] | None = None
    enabled: bool | None = None
    retry_policy: dict[str, Any] | None = None


class SubscriptionResponse(BaseModel):
    """Schema for a Subscription response."""

    id: str
    organization_id: str
    name: str
    description: str | None = None
    event_types: list[str]
    delivery: dict[str, Any]
    filter: dict[str, Any] = {}
    enabled: bool
    retry_policy: dict[str, Any] = {}
    created_at: str
    updated_at: str


# ---------------------------------------------------------
# API Key Schemas
# ---------------------------------------------------------

class ApiKeyCreate(BaseModel):
    """Schema for creating an API Key."""

    organization_id: str
    name: str = Field(..., min_length=1, max_length=128)
    key_prefix: str = Field(..., description="First 8 chars for identification")
    scope_type: str = Field(..., description="ORGANIZATION or DEPLOYMENT")
    scopes: list[str] = Field(..., min_length=1)
    description: str | None = Field(default=None, max_length=512)
    deployment_profile_id: str | None = None
    enabled: bool = True
    expires_at: str | None = None


class ApiKeyUpdate(BaseModel):
    """Schema for updating an API Key."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    scopes: list[str] | None = None
    enabled: bool | None = None
    scope_type: str | None = None
    deployment_profile_id: str | None = None


class ApiKeyResponse(BaseModel):
    """Schema for an API Key response."""

    id: str
    organization_id: str
    name: str
    description: str | None = None
    key_prefix: str
    scope_type: str
    deployment_profile_id: str | None = None
    scopes: list[str]
    enabled: bool
    expires_at: str | None = None
    last_used_at: str | None = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------
# Issuance Record Schemas
# ---------------------------------------------------------

class IssuanceRecordCreate(BaseModel):
    flow_id: str
    credential_template_id: str
    holder_id: str
    flow_execution_id: str | None = None
    application_id: str | None = None
    credential_format: str | None = None
    offer_uri: str | None = None
    offer_expires_at: datetime | None = None

class IssuanceRecordUpdate(BaseModel):
    status: str | None = None
    credential_id: str | None = None
    credential_format: str | None = None
    offer_uri: str | None = None
    offer_expires_at: datetime | None = None
    revocation_index: int | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    claimed_at: datetime | None = None

class IssuanceRecordResponse(BaseModel):
    id: str
    flow_id: str
    flow_execution_id: str | None = None
    application_id: str | None = None
    credential_template_id: str
    holder_id: str
    credential_id: str | None = None
    credential_format: str | None = None
    offer_uri: str | None = None
    offer_expires_at: datetime | None = None
    status: str
    revocation_index: int | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    created_at: datetime
    claimed_at: datetime | None = None
    class Config: from_attributes = True


# ---------------------------------------------------------
# Policy Set Schemas
# ---------------------------------------------------------

class PolicySetCreate(BaseModel):
    organization_id: str
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    policy_type: str = "ACCESS_CONTROL"
    cedar_policies: list[dict[str, Any]] = Field(default_factory=list)
    cedar_schema_version: str | None = None

class PolicySetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    policy_type: str | None = None
    cedar_policies: list[dict[str, Any]] | None = None
    cedar_schema_version: str | None = None
    status: str | None = None

class PolicySetResponse(BaseModel):
    id: str
    organization_id: str
    name: str
    description: str | None = None
    policy_type: str
    cedar_policies: list[dict[str, Any]]
    cedar_schema_version: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime | None = None
    class Config: from_attributes = True


# ---------------------------------------------------------
# Wallet Profile Schemas
# ---------------------------------------------------------

class WalletProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    credential_format: str
    issuance_protocol: str
    organization_id: str | None = None
    description: str | None = None
    compliance_profile_code: str | None = None
    wallet_apps: list[str] | None = None
    merge_strategy: str | None = None
    specifications: list[str] | None = None
    supported_platforms: list[str] | None = None
    deep_link_pattern: str | None = None
    is_override: bool | None = None
    override_precedence: int | None = None

class WalletProfileUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    credential_format: str | None = None
    issuance_protocol: str | None = None
    compliance_profile_code: str | None = None
    wallet_apps: list[str] | None = None
    merge_strategy: str | None = None
    specifications: list[str] | None = None
    supported_platforms: list[str] | None = None
    deep_link_pattern: str | None = None
    is_override: bool | None = None
    override_precedence: int | None = None

class WalletProfileResponse(BaseModel):
    id: str
    organization_id: str | None = None
    is_override: bool | None = None
    override_precedence: int | None = None
    name: str
    description: str | None = None
    credential_format: str
    issuance_protocol: str
    compliance_profile_code: str | None = None
    wallet_apps: list[str] | None = None
    merge_strategy: str | None = None
    specifications: list[str] | None = None
    supported_platforms: list[str] | None = None
    deep_link_pattern: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    class Config: from_attributes = True


# ---------------------------------------------------------
# Device Registration Schemas
# ---------------------------------------------------------

class DeviceRegistrationCreate(BaseModel):
    user_id: str
    device_id: str
    platform: str
    fcm_token: str
    organization_id: str | None = None
    app_version: str | None = None
    os_version: str | None = None
    device_model: str | None = None
    preferences: dict[str, Any] | None = None
    public_key_der: str | None = None
    public_key_kid: str | None = None
    is_active: bool = True

class DeviceRegistrationUpdate(BaseModel):
    fcm_token: str | None = None
    app_version: str | None = None
    os_version: str | None = None
    device_model: str | None = None
    preferences: dict[str, Any] | None = None
    public_key_der: str | None = None
    public_key_kid: str | None = None
    is_active: bool | None = None

class DeviceRegistrationResponse(BaseModel):
    id: str
    user_id: str
    organization_id: str | None = None
    device_id: str
    platform: str
    fcm_token: str
    app_version: str | None = None
    os_version: str | None = None
    device_model: str | None = None
    preferences: dict[str, Any] | None = None
    public_key_der: str | None = None
    public_key_kid: str | None = None
    key_valid_from: datetime | None = None
    key_valid_until: datetime | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None
    last_seen_at: datetime | None = None
    class Config: from_attributes = True


# ---------------------------------------------------------
# Applicant Schemas
# ---------------------------------------------------------

class ApplicantCreate(BaseModel):
    organization_id: str
    flow_id: str
    credential_template_id: str | None = None
    user_id: str | None = None
    external_id: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    email: str | None = None
    phone: str | None = None
    application_data: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

class ApplicantUpdate(BaseModel):
    status: str | None = None
    reviewer_id: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    email: str | None = None
    phone: str | None = None
    application_data: dict[str, Any] | None = None
    rejection_reason: str | None = None
    rejection_code: str | None = None
    metadata: dict[str, Any] | None = None

class ApplicantResponse(BaseModel):
    id: str
    organization_id: str
    flow_id: str
    credential_template_id: str | None = None
    user_id: str | None = None
    external_id: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    email: str | None = None
    phone: str | None = None
    status: str
    reviewer_id: str | None = None
    reviewer_lock_expires_at: datetime | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None
    credentialed_at: datetime | None = None
    rejection_reason: str | None = None
    rejection_code: str | None = None
    application_data: dict[str, Any] | None = None
    vetting_checks: list[dict[str, Any]] | None = None
    issued_credential_id: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime | None = None
    class Config: from_attributes = True


# ---------------------------------------------------------
# Reviewer Lock Schemas
# ---------------------------------------------------------

class ReviewerLockCreate(BaseModel):
    applicant_id: str
    organization_id: str
    holder_user_id: str
    ttl_seconds: int | None = None

class ReviewerLockResponse(BaseModel):
    id: str
    applicant_id: str
    organization_id: str
    holder_user_id: str
    ttl_seconds: int | None = None
    expires_at: datetime
    released_at: datetime | None = None
    status: str | None = None
    created_at: datetime
    class Config: from_attributes = True


# ---------------------------------------------------------
# Vetting Check Schemas
# ---------------------------------------------------------

class VettingCheckCreate(BaseModel):
    applicant_id: str
    organization_id: str
    check_type: str = "MANUAL_REVIEW"
    provider: str | None = None
    provider_reference_id: str | None = None

class VettingCheckUpdate(BaseModel):
    status: str | None = None
    score: float | None = None
    threshold: float | None = None
    failure_reason: str | None = None
    evidence_refs: list[dict[str, Any]] | None = None
    performed_by: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    raw_result: dict[str, Any] | None = None

class VettingCheckResponse(BaseModel):
    id: str
    applicant_id: str
    organization_id: str
    check_type: str
    provider: str | None = None
    provider_reference_id: str | None = None
    status: str
    score: float | None = None
    threshold: float | None = None
    failure_reason: str | None = None
    evidence_refs: list[dict[str, Any]] | None = None
    performed_by: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    raw_result: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime | None = None
    class Config: from_attributes = True


# ---------------------------------------------------------
# Biometric Enrollment Schemas
# ---------------------------------------------------------

class BiometricEnrollmentCreate(BaseModel):
    applicant_id: str
    organization_id: str
    modality: str = "FACE"
    template_hash: str
    hash_algorithm: str = "SHA-256"
    provider: str | None = None
    capture_device: str | None = None
    quality_score: float | None = None
    liveness_verified: bool | None = None

class BiometricEnrollmentUpdate(BaseModel):
    status: str | None = None
    quality_score: float | None = None
    liveness_verified: bool | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None

class BiometricEnrollmentResponse(BaseModel):
    id: str
    applicant_id: str
    organization_id: str
    modality: str
    template_hash: str
    hash_algorithm: str
    provider: str | None = None
    capture_device: str | None = None
    quality_score: float | None = None
    liveness_verified: bool | None = None
    status: str
    revoked_at: datetime | None = None
    revocation_reason: str | None = None
    created_at: datetime
    class Config: from_attributes = True


# ---------------------------------------------------------
# Notification Payload Schemas
# ---------------------------------------------------------

class NotificationTargetSchema(BaseModel):
    organization_id: str | None = None
    user_id: str | None = None
    device_tokens: list[str] | None = None
    webhook_endpoints: list[str] | None = None
    email_addresses: list[str] | None = None
    channels: list[str]

class NotificationPayloadCreate(BaseModel):
    title: str
    body: str
    event_type: str
    priority: str = "NORMAL"
    target: NotificationTargetSchema
    data: dict[str, Any] | None = None
    ttl_seconds: int | None = None
    collapse_key: str | None = None
    correlation_id: str | None = None

class NotificationPayloadResponse(BaseModel):
    id: str
    title: str
    body: str
    data: dict[str, Any] | None = None
    event_type: str
    priority: str
    target: dict[str, Any]
    ttl_seconds: int | None = None
    collapse_key: str | None = None
    correlation_id: str | None = None
    created_at: datetime
    class Config: from_attributes = True
