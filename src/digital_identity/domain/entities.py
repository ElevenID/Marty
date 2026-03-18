"""
Domain Entities for Digital Identity

Core domain entities representing the five identity primitives:
- Trust Profile: Who is trusted and how crypto validation occurs
- Credential Template: What is issued (schema + semantics)
- Presentation Policy: What must be shown (minimum disclosure)
- Deployment Profile: Where it runs (device/site behavior)
- Flow: How identity moves (apply → issue → verify)

These are aggregate roots that encapsulate domain logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar
from uuid import uuid4

from digital_identity.domain.value_objects import (
    TrustProfileType,
    RevocationPolicy,
    TimePolicy,
    CryptoAlgorithm,
    CredentialFormat,
    CredentialStatus,
    ClaimDefinition,
    ValidityRules,
    RequiredClaim,
    FreshnessRequirements,
    HolderBindingMethod,
    HolderBindingConfig,
    CredentialRankingStrategy,
    NetworkMode,
    KeyAccessMode,
    UXConfig,
    UpdatePolicy,
    FlowType,
    FlowStatus,
    ApprovalStrategy,
    FLOW_STEPS,
    IssuerArtifactRequirements,
    ARTIFACT_REQUIREMENTS,
    EvidenceType,
    EvidenceRequirement,
    ClaimVerificationRule,
    StatusListEntryRef,
    PredicateFallbackPolicy,
    PredicateSpecification,
    PrivacyPosture,
    RevocationTimingMode,
    RevocationMethod,
)


# =============================================================================
# Base Entity
# =============================================================================

@dataclass
class Entity:
    """
    Base class for domain entities.
    
    Provides common identity and timestamp fields.
    """
    
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1
    
    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1


# =============================================================================
# Organization
# =============================================================================

@dataclass
class Organization(Entity):
    """
    Organization entity - primary multi-tenant boundary.
    
    All configuration resources (trust profiles, credential templates,
    deployment profiles, etc.) are scoped to an organization.
    
    Attributes:
        name: Machine-friendly slug (globally unique, lowercase alphanumeric + hyphens)
        display_name: Human-readable name
        description: Optional description
        visibility: PUBLIC (discoverable/joinable) or PRIVATE (invite-only)
        owner_id: User ID of the current organization owner
        join_code: Alphanumeric code for joining PUBLIC organizations
        status: ACTIVE, SUSPENDED, or DELETED
    """
    
    name: str = ""
    display_name: str = ""
    description: str | None = None
    visibility: str = "PRIVATE"
    owner_id: str = ""
    join_code: str | None = None
    status: str = "ACTIVE"


# =============================================================================
# Trust Framework (System-level)
# =============================================================================

@dataclass
class TrustFramework(Entity):
    """
    Trust Framework entity - system-level trust model shared across all organizations.
    
    A Trust Framework represents a standardized trust ecosystem like:
    - ICAO PKD for ePassports/eMRTD
    - AAMVA for mDL (ISO 18013-5)
    - EUDI for EU Digital Identity Wallet
    - CUSTOM for organization-specific X.509/PKI
    
    These are immutable system records that define default configurations,
    PKD endpoints, and validation rulesets. Organizations reference frameworks
    and apply their own policy overrides.
    
    Attributes:
        code: Unique identifier (e.g., "icao", "aamva", "eudi", "custom")
        display_name: Human-readable name (e.g., "ICAO PKD (Passports)")
        description: Optional description
        pkd_endpoints: Official PKD URLs for trust anchor sync
        default_algorithms: Required algorithms for this framework
        default_formats: Supported credential formats
        validation_ruleset: Framework-specific validation rules
        sync_config: Configuration for periodic trust anchor refresh
        is_system: Whether this is a system-managed framework
    """
    
    code: str = ""
    display_name: str = ""
    description: str | None = None
    pkd_endpoints: dict[str, Any] = field(default_factory=dict)
    default_algorithms: list[CryptoAlgorithm] = field(default_factory=list)
    default_formats: list[CredentialFormat] = field(default_factory=list)
    validation_ruleset: dict[str, Any] = field(default_factory=dict)
    sync_config: dict[str, Any] = field(default_factory=dict)
    is_system: bool = True


# =============================================================================
# Trust Profile (Organization-specific)
# =============================================================================

@dataclass
class OrganizationTrustProfile(Entity):
    """
    Organization Trust Profile entity - org-specific configuration of a trust framework.
    
    This entity links an organization to a trust framework (ICAO, AAMVA, EUDI, CUSTOM)
    and allows policy overrides specific to that organization's needs.
    
    The split model separates:
    - SHARED: Framework definitions, global trust anchors (in TrustFramework)
    - ORG-SPECIFIC: Selected framework, policy overrides, custom anchors (here)
    
    Attributes:
        organization_id: Organization this profile belongs to
        framework_id: Reference to the trust framework being used
        name: Technical identifier (e.g., "travel-documents")
        display_name: Business-friendly name (e.g., "Travel Documents")
        description: Optional description
        enabled: Whether the profile is active
        use_case_tags: Business context tags (e.g., ["travel_documents"])
        compliance_status: Current status (COMPLIANT, NEEDS_ATTENTION, SETUP_REQUIRED)
        auto_generated: Whether created by onboarding wizard vs manual
        revocation_policy: Override revocation policy (None = use framework default)
        time_policy: Override time policy (None = use framework default)
        allowed_algorithms: Override algorithms (None = use framework default)
        allowed_formats: Override formats (None = use framework default)
        allowed_issuers: Optional allowlist of issuer identifiers
        denied_issuers: Optional denylist of issuer identifiers
        jurisdiction_filter: Filter by jurisdiction codes (e.g., ['US-CA', 'US-NY'])
        metadata: Additional configuration data
    """
    
    organization_id: str = ""
    framework_id: str = ""
    name: str = ""
    display_name: str = ""
    description: str | None = None
    enabled: bool = True
    
    # Business context
    use_case_tags: list[str] = field(default_factory=list)
    compliance_status: str = "SETUP_REQUIRED"  # COMPLIANT, NEEDS_ATTENTION, SETUP_REQUIRED
    auto_generated: bool = False
    
    # Policy overrides (None = use framework defaults)
    revocation_policy: RevocationPolicy | None = None
    time_policy: TimePolicy | None = None
    allowed_algorithms: list[CryptoAlgorithm] | None = None
    allowed_formats: list[CredentialFormat] | None = None
    
    # Issuer constraints
    allowed_issuers: list[str] | None = None
    denied_issuers: list[str] | None = None
    jurisdiction_filter: list[str] | None = None  # ['US-CA', 'DE', etc.]
    
    # Extension point
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def is_issuer_allowed(self, issuer_id: str) -> bool:
        """Check if an issuer is allowed by this profile."""
        if self.denied_issuers and issuer_id in self.denied_issuers:
            return False
        if self.allowed_issuers is not None:
            return issuer_id in self.allowed_issuers
        return True
    
    def is_algorithm_allowed(self, algorithm: CryptoAlgorithm) -> bool:
        """Check if an algorithm is allowed by this profile."""
        if self.allowed_algorithms is None:
            return True  # Use framework defaults
        return algorithm in self.allowed_algorithms
    
    def is_format_allowed(self, format: CredentialFormat) -> bool:
        """Check if a credential format is allowed by this profile."""
        if self.allowed_formats is None:
            return True  # Use framework defaults
        return format in self.allowed_formats


# =============================================================================
# Trust Profile (Simplified - for API)
# =============================================================================

@dataclass
class TrustProfile(Entity):
    """
    Trust Profile entity - simplified trust configuration.
    
    A standalone trust profile that defines trust sources and validation policies
    for credential verification. This is the simpler API-focused entity used by
    the REST endpoints and services.
    
    Attributes:
        name: Unique name for the trust profile
        description: Optional description
        profile_type: Type of trust profile (ICAO, AAMVA, EUDI, CUSTOM)
        enabled: Whether the profile is active
        trust_sources: List of trust anchor sources
        allowed_algorithms: Allowed cryptographic algorithms
        allowed_formats: Allowed credential formats
        revocation_policy: Revocation checking policy
        time_policy: Time validation policy
        allowed_issuers: Optional allowlist of issuer identifiers
        denied_issuers: Optional denylist of issuer identifiers
        metadata: Additional configuration data
    """
    
    name: str = ""
    description: str | None = None
    organization_id: str = ""
    profile_type: TrustProfileType = TrustProfileType.CUSTOM
    enabled: bool = True
    compliance_status: str = "SETUP_REQUIRED"
    auto_generated: bool = False
    manually_configured: bool = False
    trust_sources: list[dict[str, Any]] = field(default_factory=list)
    allowed_algorithms: list[CryptoAlgorithm] = field(default_factory=list)
    supported_formats: list[CredentialFormat] = field(default_factory=list)
    revocation_policy: RevocationPolicy = field(default_factory=RevocationPolicy)
    time_policy: TimePolicy = field(default_factory=TimePolicy)
    revocation_profile_id: str | None = None
    
    # Revocation service configuration
    revocation_services: dict[str, Any] = field(default_factory=dict)
    
    # Issuer constraints
    allowed_issuers: list[str] | None = None
    denied_issuers: list[str] | None = None
    
    # System issuer overrides
    system_issuer_overrides: dict[str, Any] = field(default_factory=dict)
    
    # Compliance code compatibility
    compatible_compliance_codes: list[str] | None = None
    
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def is_issuer_allowed(self, issuer_id: str, is_system_issuer: bool = False) -> bool:
        """
        Check if an issuer is allowed by this profile.
        
        Args:
            issuer_id: The issuer identifier
            is_system_issuer: Whether this is a system issuer (ICAO/AAMVA)
            
        Returns:
            True if allowed, False otherwise
        """
        # Check system issuer overrides first
        if is_system_issuer and issuer_id in self.system_issuer_overrides:
            override = self.system_issuer_overrides[issuer_id]
            if override.get("action") == "DENY":
                return False
        
        # Apply standard allow/deny lists
        if self.denied_issuers and issuer_id in self.denied_issuers:
            return False
        if self.allowed_issuers is not None:
            return issuer_id in self.allowed_issuers
        return True
    
    def get_effective_trust_level(self, issuer_id: str, default_level: int = 100) -> int:
        """
        Get effective trust level for an issuer considering overrides.
        
        Args:
            issuer_id: The issuer identifier
            default_level: Default trust level if no override exists
            
        Returns:
            Effective trust level (0-100)
        """
        if issuer_id in self.system_issuer_overrides:
            override = self.system_issuer_overrides[issuer_id]
            if override.get("action") == "DOWNGRADE":
                return override.get("trust_level", default_level)
        return default_level
    
    def is_algorithm_allowed(self, algorithm: CryptoAlgorithm) -> bool:
        """Check if an algorithm is allowed by this profile."""
        return algorithm in self.allowed_algorithms
    
    def is_format_allowed(self, format: CredentialFormat) -> bool:
        """Check if a credential format is allowed by this profile."""
        return format in self.supported_formats
    
    def get_revocation_methods(self) -> list[str]:
        """Get enabled revocation methods from revocation_services config."""
        return self.revocation_services.get("enabled_methods", [])
    
    def should_auto_discover_revocation(self) -> bool:
        """Check if auto-discovery of revocation endpoints is enabled."""
        return self.revocation_services.get("auto_discover", False)
    
    def should_merge_discovered_endpoints(self) -> bool:
        """Check if discovered endpoints should be merged with explicit ones."""
        return self.revocation_services.get("merge_discovered", False)
    
    def get_explicit_revocation_endpoints(self, method: str) -> list[str]:
        """
        Get explicit revocation endpoints for a specific method.
        
        Args:
            method: Revocation method (CRL, OCSP, STATUS_LIST)
            
        Returns:
            List of endpoint URLs
        """
        method_key = f"{method.lower()}_endpoints" if method == "CRL" else f"{method.lower()}_urls"
        return self.revocation_services.get(method_key, [])
    
    def add_trust_source(
        self,
        source_type: str,
        source_uri: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Add a trust source to this profile."""
        source = {
            "type": source_type,
            **({"uri": source_uri} if source_uri else {}),
            **({"config": config} if config else {}),
        }
        self.trust_sources.append(source)
        self.touch()

    # Default mapping: compliance_code → compatible profile_types
    _DEFAULT_COMPLIANCE_MAP: ClassVar[dict[str, list[str]]] = {
        "ICAO_DTC": ["ICAO", "CUSTOM"],
        "ICAO_MRZ": ["ICAO", "CUSTOM"],
        "AAMVA_MDL": ["AAMVA", "CUSTOM"],
        "EUDI_PID": ["EUDI", "CUSTOM"],
        "EUDI_MDL": ["EUDI", "CUSTOM"],
        "OB3_JWT": ["CUSTOM"],
        "OB3_JSONLD": ["CUSTOM"],
        "OB2_COMPATIBILITY": ["CUSTOM"],
        "SD_JWT_VC": ["CUSTOM"],
        "ENTERPRISE_VC": ["CUSTOM"],
        "OID4VC": ["CUSTOM"],
        "PEX": ["CUSTOM"],
        "CUSTOM": ["ICAO", "AAMVA", "EUDI", "CUSTOM"],
    }

    def is_compatible_with_compliance_code(self, compliance_code: str) -> bool:
        """Check if this trust profile is compatible with a compliance code.
        
        When ``compatible_compliance_codes`` is set explicitly, the code must
        appear in that list.  Otherwise the default mapping from compliance
        code → profile_type is used (see §10.5 of the specification).
        """
        if self.compatible_compliance_codes is not None:
            return compliance_code in self.compatible_compliance_codes

        profile_type_str = (
            self.profile_type.value
            if isinstance(self.profile_type, TrustProfileType)
            else str(self.profile_type)
        )
        allowed_types = self._DEFAULT_COMPLIANCE_MAP.get(compliance_code, ["CUSTOM"])
        return profile_type_str in allowed_types


# =============================================================================
# Issuer Registry
# =============================================================================

@dataclass
class IssuerEntity(Entity):
    """
    Issuer Entity - represents a trusted issuer with lifecycle management.
    
    Separate from Trust Anchors. An Issuer is an organization or authority
    that issues credentials. Trust Anchors are cryptographic roots used for
    validation. An Issuer may be backed by one or more Trust Anchors.
    
    Attributes:
        organization_id: Organization this issuer belongs to (NULL = global/system)
        issuer_id: Unique issuer identifier (DID, domain, or custom ID)
        issuer_type: Type of issuer (ORGANIZATION, GOVERNMENT, DEVICE)
        display_name: Human-readable name
        description: Optional description
        is_system_issuer: Auto-visible to all organizations (ICAO/AAMVA issuers)
        compliance_status: Current compliance state
        accreditation_body: Who accredited this issuer
        accreditation_date: When accreditation was granted
        valid_from: Start of validity period
        valid_until: End of validity period (NULL = indefinite)
        trust_anchor_id: Optional link to trust anchor (for X.509 chains)
        revoked_at: Revocation timestamp
        revocation_reason: Why revoked
        revoked_by: Who revoked
        metadata: Additional issuer data
    """
    
    organization_id: str | None = None
    issuer_id: str = ""
    issuer_type: str = "ORGANIZATION"  # ORGANIZATION, GOVERNMENT, DEVICE
    display_name: str = ""
    description: str | None = None
    is_system_issuer: bool = False
    compliance_status: str = "COMPLIANT"  # ACCREDITED, COMPLIANT, SUSPENDED, REVOKED
    accreditation_body: str | None = None
    accreditation_date: datetime | None = None
    valid_from: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    valid_until: datetime | None = None
    trust_anchor_id: str | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None
    revoked_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def is_active(self) -> bool:
        """Check if issuer is currently active (not revoked, within validity)."""
        if self.revoked_at is not None:
            return False
        now = datetime.now(timezone.utc)
        if now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True
    
    def is_compliant(self) -> bool:
        """Check if issuer has acceptable compliance status."""
        return self.compliance_status in ["ACCREDITED", "COMPLIANT"]
    
    def revoke(self, reason: str, revoked_by: str) -> None:
        """Revoke this issuer."""
        self.revoked_at = datetime.now(timezone.utc)
        self.revocation_reason = reason
        self.revoked_by = revoked_by
        self.compliance_status = "REVOKED"
        self.touch()
    
    def suspend(self, reason: str) -> None:
        """Suspend this issuer (reversible)."""
        self.compliance_status = "SUSPENDED"
        self.metadata["suspension_reason"] = reason
        self.metadata["suspended_at"] = datetime.now(timezone.utc).isoformat()
        self.touch()
    
    def reinstate(self) -> None:
        """Reinstate a suspended issuer."""
        if self.compliance_status == "SUSPENDED":
            self.compliance_status = "COMPLIANT"
            self.metadata.pop("suspension_reason", None)
            self.metadata.pop("suspended_at", None)
            self.touch()


@dataclass
class TrustProfileIssuer(Entity):
    """
    Trust Profile to Issuer relationship with trust scoring.
    
    Represents the relationship between a Trust Profile and an Issuer,
    including trust level scoring and cascade revocation policy.
    
    Attributes:
        trust_profile_id: Trust profile ID
        issuer_id: Issuer entity ID
        trust_level: Trust score 0-100 (future: auto-adjust based on history)
        relationship_status: Current status (TRUSTED, DENIED, UNDER_REVIEW)
        cascade_revocation_policy: What happens when issuer is revoked
        metadata: Additional relationship data
    """
    
    trust_profile_id: str = ""
    issuer_id: str = ""
    trust_level: int = 100  # 0-100 score
    # TODO: Future feature - auto-adjust trust_level based on issuer history:
    #       - Failed validations, revocation events, compliance lapses
    #       - Implement reputation scoring algorithm with configurable decay
    relationship_status: str = "TRUSTED"  # TRUSTED, DENIED, UNDER_REVIEW
    cascade_revocation_policy: str = "MANUAL"  # AUTO_CASCADE, MANUAL, NOTIFY_ONLY
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def is_trusted(self) -> bool:
        """Check if relationship is in trusted status."""
        return self.relationship_status == "TRUSTED"
    
    def meets_minimum_trust_level(self, minimum: int) -> bool:
        """Check if trust level meets minimum threshold."""
        return self.trust_level >= minimum
    
    def update_trust_level(self, new_level: int, reason: str | None = None) -> None:
        """Update trust level with optional reason tracking."""
        if not 0 <= new_level <= 100:
            raise ValueError("Trust level must be between 0 and 100")
        old_level = self.trust_level
        self.trust_level = new_level
        if reason:
            if "trust_level_history" not in self.metadata:
                self.metadata["trust_level_history"] = []
            self.metadata["trust_level_history"].append({
                "from": old_level,
                "to": new_level,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        self.touch()


@dataclass
class CascadeRevocationOperation(Entity):
    """
    Cascade Revocation Operation - tracks issuer/anchor revocation cascades.
    
    When an issuer or trust anchor is revoked, this tracks the cascade operation
    to dependent credentials, with rollback support and circuit breaker protection.
    
    Attributes:
        operation_type: Type of cascade (ISSUER_REVOCATION, ANCHOR_REVOCATION)
        trigger_entity_type: What triggered it (ISSUER, TRUST_ANCHOR)
        trigger_entity_id: ID of entity that was revoked
        status: Current operation status
        affected_credential_count: How many credentials affected
        affected_credential_ids: List of credential IDs
        requires_confirmation: Whether manual confirmation needed (high impact)
        confirmed_at: When operation was confirmed
        confirmed_by: Who confirmed
        max_cascade_depth: Maximum depth to cascade
        current_depth: Current depth in cascade tree
        circuit_breaker_threshold: Max credentials before requiring confirmation
        circuit_breaker_triggered: Whether circuit breaker stopped cascade
        can_rollback: Whether operation can be rolled back
        rollback_snapshot: Pre-revocation state for rollback
        rolled_back_at: When rolled back
        rolled_back_by: Who rolled back
        error_message: Error if operation failed
        metadata: Additional operation data
    """
    
    operation_type: str = "ISSUER_REVOCATION"  # ISSUER_REVOCATION, ANCHOR_REVOCATION
    organization_id: str | None = None
    trigger_entity_type: str = "ISSUER"  # ISSUER, TRUST_ANCHOR
    trigger_entity_id: str = ""
    status: str = "PENDING_CONFIRMATION"  # PENDING_CONFIRMATION, IN_PROGRESS, COMPLETED, ROLLED_BACK, FAILED
    affected_credential_count: int = 0
    affected_credential_ids: list[str] = field(default_factory=list)
    requires_confirmation: bool = False
    confirmed_at: datetime | None = None
    confirmed_by: str | None = None
    max_cascade_depth: int = 3
    current_depth: int = 0
    circuit_breaker_threshold: int = 1000
    circuit_breaker_triggered: bool = False
    can_rollback: bool = True
    rollback_snapshot: dict[str, Any] = field(default_factory=dict)
    rolled_back_at: datetime | None = None
    rolled_back_by: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def is_pending_confirmation(self) -> bool:
        """Check if operation awaits manual confirmation."""
        return self.status == "PENDING_CONFIRMATION" and self.requires_confirmation
    
    def can_be_executed(self) -> bool:
        """Check if operation can proceed."""
        if self.requires_confirmation and not self.confirmed_at:
            return False
        return self.status in ["PENDING_CONFIRMATION", "IN_PROGRESS"]
    
    def can_be_rolled_back(self) -> bool:
        """Check if operation can be rolled back."""
        return self.can_rollback and self.status == "COMPLETED" and not self.rolled_back_at
    
    def confirm(self, confirmed_by: str) -> None:
        """Confirm high-impact operation."""
        if not self.requires_confirmation:
            raise ValueError("Operation does not require confirmation")
        self.confirmed_at = datetime.now(timezone.utc)
        self.confirmed_by = confirmed_by
        self.status = "IN_PROGRESS"
        self.touch()
    
    def complete(self) -> None:
        """Mark operation as completed."""
        self.status = "COMPLETED"
        self.touch()
    
    def fail(self, error: str) -> None:
        """Mark operation as failed."""
        self.status = "FAILED"
        self.error_message = error
        self.touch()
    
    def rollback(self, rolled_back_by: str) -> None:
        """Roll back the operation."""
        if not self.can_be_rolled_back():
            raise ValueError("Operation cannot be rolled back")
        self.rolled_back_at = datetime.now(timezone.utc)
        self.rolled_back_by = rolled_back_by
        self.status = "ROLLED_BACK"
        self.touch()


@dataclass
class OrganizationCustomAnchor(Entity):
    """
    Organization Custom Anchor entity - BYOK certificates for custom trust.
    
    Represents a custom trust anchor (certificate) uploaded by an organization
    for use with CUSTOM trust profiles or as supplements to standard frameworks.
    
    Attributes:
        profile_id: Trust profile this anchor belongs to
        anchor_type: Type of anchor ('root_ca', 'intermediate', 'leaf')
        subject: Certificate subject DN
        issuer: Certificate issuer DN
        certificate_pem: PEM-encoded certificate
        certificate_der: DER-encoded certificate
        not_before: Certificate validity start
        not_after: Certificate validity end
        purpose: Usage purpose ('signing', 'verification', 'both')
        uploaded_by: User who uploaded the certificate
        uploaded_at: When the certificate was uploaded
    """
    
    profile_id: str = ""
    anchor_type: str = "root_ca"
    subject: str = ""
    issuer: str = ""
    certificate_pem: str = ""
    certificate_der: bytes = field(default_factory=bytes)
    not_before: datetime | None = None
    not_after: datetime | None = None
    purpose: str = "verification"
    uploaded_by: str | None = None
    uploaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Credential Template
# =============================================================================

@dataclass
class CredentialTemplate(Entity):
    """
    Credential Template entity - the complete credential issuance definition.
    
    A Credential Template is the master configuration combining:
    - Schema/claims definition (what claims exist, their types)
    - Compliance Profile reference (format, framework selection)
    - Application Template reference (optional - for application-based issuance)
    - Cryptographic configuration (keys, certificates, DIDs)
    - Validity and revocation settings
    
    This entity represents the COMPLETE issuance configuration, not just the schema.
    For direct issuance (API/batch), application_template_id is None.
    For application-based issuance, it references an ApplicationTemplate.
    
    Attributes:
        name: Human-readable name for the template
        description: Optional description
        credential_type: Type identifier (e.g., "org.iso.18013.5.1.mDL")
        schema_uri: Optional URI to credential schema
        claims: List of claim definitions
        
        application_template_id: Optional reference to Application Template (INVERTED)
        compliance_profile_id: Reference to Compliance Profile (format abstraction)
        trust_profile_id: Optional reference to required Trust Profile
        revocation_profile_id: Optional reference to Revocation Profile
        
        validity_rules: TTL and reissue configuration
        
        issuer_key_id: Reference to signing key (KeyVault, HSM, etc.)
        issuer_key_algorithm: Signing algorithm (RS256, ES256, EdDSA)
        key_access_mode: How to access keys (key_vault, hsm, local)
        issuer_certificate_chain_pem: X.509 certificate chain (for mDoc)
        issuer_did: DID for issuer (for DID-based credentials)
        auto_generate_artifacts: Auto-generate missing artifacts in non-production
        
        format: Default credential format
        namespace: Credential namespace (for mDoc)
        privacy_posture: Selective disclosure intent
        display: Display metadata for wallet rendering
        metadata: Additional configuration
    """
    
    name: str = ""
    description: str | None = None
    credential_type: str = ""
    schema_uri: str | None = None
    vct: str | None = None  # SD-JWT VC type identifier
    
    # Organization scoping
    organization_id: str | None = None
    
    # Publish status (DRAFT → ACTIVE → DEPRECATED)
    status: str = "DRAFT"
    
    # Claims definition
    claims: list[ClaimDefinition] = field(default_factory=list)
    
    # INVERTED RELATIONSHIP: Credential Template references Application Template
    application_template_id: str | None = None  # Optional - for application-based issuance
    
    # Profile references
    compliance_profile_id: str = ""  # Required - defines format and framework
    trust_profile_id: str | None = None
    revocation_profile_id: str | None = None
    
    # Validity configuration
    validity_rules: ValidityRules = field(default_factory=ValidityRules)
    
    # ========== CRYPTOGRAPHIC CONFIGURATION (MOVED FROM Application Template) ==========
    
    # Signing key configuration
    issuer_key_id: str | None = None
    issuer_algorithm: str | None = None  # RS256, ES256, EdDSA, etc. (spec: issuer_algorithm)
    key_access_mode: str = "key_vault"  # key_vault, hsm, local (dev only)
    
    # Certificate chain (for mDoc/X.509-based credentials)
    issuer_certificate_chain_pem: str | None = None
    
    # DID configuration (for DID-based credentials)
    issuer_did: str | None = None
    
    # Development mode
    auto_generate_artifacts: bool = False  # Auto-generate in non-production
    
    # ========== END CRYPTOGRAPHIC CONFIGURATION ==========
    
    # Format and structure
    format: CredentialFormat = CredentialFormat.SD_JWT_VC
    namespace: str | None = None  # For mDoc: e.g., "org.iso.18013.5.1"
    privacy_posture: PrivacyPosture = field(default_factory=PrivacyPosture)
    
    # Display metadata
    display: dict[str, Any] = field(default_factory=dict)
    
    # Extension point
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # Legacy field (for backward compatibility during migration)
    issuer_key_ids: list[str] | None = None
    
    def add_claim(self, claim: ClaimDefinition) -> None:
        """Add a claim definition to this template."""
        self.claims.append(claim)
        self.touch()
    
    def get_required_claims(self) -> list[ClaimDefinition]:
        """Get all required claims."""
        return [c for c in self.claims if c.required]
    
    def get_disclosable_claims(self) -> list[ClaimDefinition]:
        """Get all selectively disclosable claims."""
        return [c for c in self.claims if c.selectively_disclosable]
    
    def get_derived_claims(self) -> list[ClaimDefinition]:
        """Get all derived claims (predicates)."""
        return [c for c in self.claims if c.derived_from is not None]


# =============================================================================
# Compliance Profile
# =============================================================================

@dataclass
class ComplianceProfile(Entity):
    """
    Compliance Profile entity - abstracts credential format complexity.
    
    A Compliance Profile bundles credential format, issuer artifact requirements,
    and default verification rules into a reusable configuration. Profiles can be
    system-provided presets (ICAO_DTC, AAMVA_MDL, EUDI_PID) or custom org-defined.
    
    This entity hides the complexity of choosing between mdoc, SD-JWT, JSON-LD, etc.,
    by presenting compliance-focused options like "AAMVA mDL Standard" or "ICAO DTC".
    
    Attributes:
        name: Human-readable name (e.g., "ICAO DTC - Digital Travel Credential")
        description: Optional description
        code: Unique code identifier (e.g., "ICAO_DTC", "AAMVA_MDL")
        credential_format: The credential format this profile uses
        issuer_artifact_requirements: Required cryptographic artifacts
        default_claim_verification_rules: Default claim verification rules
        trust_profile_requirements: Optional trust profile constraints
        is_system: Whether this is a system-provided preset (immutable)
        metadata: Additional configuration
    """
    
    name: str = ""
    description: str | None = None
    compliance_code: str = ""  # spec: compliance_code (was: code)
    credential_format: CredentialFormat = CredentialFormat.SD_JWT_VC
    issuance_protocol: str | None = None  # spec: OID4VCI_PRE_AUTH | OID4VCI_AUTH_CODE | DIRECT
    issuer_artifact_requirements: IssuerArtifactRequirements | None = None
    default_verification_rules: list[ClaimVerificationRule] = field(default_factory=list)  # spec: default_verification_rules
    trust_profile_constraints: dict[str, Any] = field(default_factory=dict)  # spec: trust_profile_constraints
    is_system: bool = False
    organization_id: str | None = None
    discoverable: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def get_artifact_requirements(self) -> IssuerArtifactRequirements:
        """Get artifact requirements for this profile."""
        if self.issuer_artifact_requirements:
            return self.issuer_artifact_requirements
        # Fall back to default for format
        return ARTIFACT_REQUIREMENTS.get(
            self.credential_format,
            ARTIFACT_REQUIREMENTS[CredentialFormat.SD_JWT_VC],
        )
    
    def validate_artifacts(
        self,
        issuer_key_id: str | None,
        issuer_certificate_chain_pem: str | None,
        issuer_did: str | None,
    ) -> list[str]:
        """
        Validate that required artifacts are present.
        
        Returns list of error messages if artifacts are missing.
        """
        requirements = self.get_artifact_requirements()
        errors = []
        
        if requirements.requires_x509_cert and not issuer_certificate_chain_pem:
            errors.append(f"X.509 certificate required for {self.credential_format}")
        
        if requirements.requires_did and not issuer_did:
            errors.append(f"Issuer DID required for {self.credential_format}")
        
        return errors


# =============================================================================
# Application Template
# =============================================================================

@dataclass
class ApplicationTemplate(Entity):
    """
    Application Template entity - defines what users fill out to apply for credentials.
    
    An Application Template is a PURE USER-FACING entity with NO cryptographic concerns.
    It defines the application workflow and data collection process, not the credential
    structure or issuance mechanics.
    
    Key responsibilities:
    - Define what evidence must be collected (documents, biometrics, etc.)
    - Define form fields for user data entry
    - Specify how to collect claim values from the applicant
    - Configure approval workflow and notifications
    - Customize UI/UX for the application process
    
    NOTE: Application Templates are referenced by Credential Templates, not the other way around.
    A Credential Template may optionally reference an Application Template if it supports
    application-based issuance (as opposed to direct/batch issuance).
    
    Attributes:
        name: Human-readable name for the application template
        description: Optional description
        evidence_requirements: List of required evidence before issuance
        form_fields: Form field definitions for user data entry
        claim_collection_rules: How to collect claim values from applicant
        approval_strategy: How approvals are handled (auto, manual, rules_based)
        application_validity_days: How long applications remain valid
        notifications: Notification configuration (email, SMS)
        ui_config: UI/UX customization (theme, welcome message, etc.)
        metadata: Additional configuration
    """
    
    name: str = ""
    description: str | None = None
    
    # Organization scoping
    organization_id: str | None = None
    
    # Publish status (DRAFT → ACTIVE → DEPRECATED)
    status: str = "DRAFT"
    
    # Evidence collection requirements
    evidence_requirements: list[EvidenceRequirement] = field(default_factory=list)
    
    # Form field definitions (NEW)
    form_fields: list[dict] = field(default_factory=list)  # Will be FormFieldDefinition
    
    # Claim collection (how to gather claim values from applicant)
    claim_collection_rules: list[dict] = field(default_factory=list)  # Will be ClaimCollectionRule
    
    # Workflow configuration
    approval_strategy: ApprovalStrategy = ApprovalStrategy.AUTO
    application_validity_days: int = 30
    
    # Notification settings (NEW)
    notifications: dict[str, Any] = field(default_factory=dict)  # NotificationConfig
    
    # UI/UX configuration (NEW)
    ui_config: dict[str, Any] = field(default_factory=dict)  # ApplicationUIConfig
    
    # Extension point
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # Legacy fields (for backward compatibility - will be removed in future versions)
    claim_verification_rules: list[ClaimVerificationRule] = field(default_factory=list)
    
    def add_evidence_requirement(self, requirement: EvidenceRequirement) -> None:
        """Add an evidence requirement to this template."""
        self.evidence_requirements.append(requirement)
        self.touch()
    
    def add_form_field(self, field: dict) -> None:
        """Add a form field definition to this template."""
        self.form_fields.append(field)
        self.touch()
    
    def add_claim_collection_rule(self, rule: dict) -> None:
        """Add a claim collection rule to this template."""
        self.claim_collection_rules.append(rule)
        self.touch()
    
    def add_claim_verification_rule(self, rule: ClaimVerificationRule) -> None:
        """Add a claim verification rule to this template (legacy)."""
        self.claim_verification_rules.append(rule)
        self.touch()
    
    def get_required_evidence_types(self) -> list[EvidenceType]:
        """Get all required evidence types."""
        return [
            req.evidence_type
            for req in self.evidence_requirements
            if req.required
        ]
    
    def get_required_form_fields(self) -> list[dict]:
        """Get all required form fields."""
        return [f for f in self.form_fields if f.get("required", True)]
    
    def get_required_claims_to_verify(self) -> list[str]:
        """Get list of claim names that require verification (legacy)."""
        return [
            rule.claim_name
            for rule in self.claim_verification_rules
            if rule.required
        ]


# =============================================================================
# Presentation Policy
# =============================================================================

@dataclass
class PresentationPolicy(Entity):
    """
    Presentation Policy entity - defines what must be shown.
    
    A Presentation Policy encapsulates:
    - Accepted credential templates
    - Required claims or predicates
    - Holder-binding requirements
    - Issuer constraints (via Trust Profile reference)
    - Freshness and revocation expectations
    - Data-minimization rules
    
    Attributes:
        name: Human-readable name for the policy
        description: Optional description
        purpose: Purpose description for consent
        accepted_credential_types: List of accepted credential type IDs
        required_claims: List of required claims
        holder_binding: Required holder binding method
        trust_profile_id: Reference to Trust Profile for issuer validation
        freshness_requirements: How fresh credentials must be
        prefer_predicates: Prefer predicate proofs over raw values
        single_presentation: Require all claims in single credential
        metadata: Additional configuration
    """
    
    name: str = ""
    description: str | None = None
    purpose: str = ""
    organization_id: str = ""
    
    # Accepted credentials
    accepted_credential_types: list[str] = field(default_factory=list)
    
    # Required claims
    required_claims: list[RequiredClaim] = field(default_factory=list)
    
    # Holder binding
    holder_binding: HolderBindingConfig = field(default_factory=HolderBindingConfig)
    
    # Trust constraints
    trust_profile_id: str | None = None
    allowed_issuers: list[str] = field(default_factory=list)  # Explicit issuer DID/certificate allowlist
    
    # Issuer constraints (enforced at verification time)
    # Structure: {
    #   "min_trust_level": 80,
    #   "required_compliance_statuses": ["ACCREDITED", "COMPLIANT"],
    #   "required_accreditations": ["ISO27001", "FIPS140-2"]
    # }
    issuer_constraints: dict[str, Any] = field(default_factory=dict)
    
    # Freshness
    freshness_requirements: FreshnessRequirements = field(
        default_factory=FreshnessRequirements
    )
    
    # Data minimization
    prefer_predicates: bool = False
    single_presentation: bool = False
    derived_attribute_preferences: dict[str, str] = field(default_factory=dict)  # Map raw claims to preferred derived forms
    
    # ZK Predicate Configuration
    fallback_policy: PredicateFallbackPolicy = PredicateFallbackPolicy.ACCEPT_RAW
    supported_circuits: list[str] = field(default_factory=list)  # Allowed ZK circuits for this policy
    
    # Credential ranking
    credential_ranking_strategy: CredentialRankingStrategy = CredentialRankingStrategy.FRESHEST_FIRST
    credential_ranking_weights: dict[str, float] = field(default_factory=dict)  # For CUSTOM strategy
    
    # Extension point
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def add_required_claim(
        self,
        claim_name: str,
        credential_type: str,
        accept_predicate: bool = True,
        value_constraint: Any = None,
    ) -> None:
        """Add a required claim to this policy."""
        self.required_claims.append(RequiredClaim(
            claim_name=claim_name,
            credential_type=credential_type,
            accept_predicate=accept_predicate,
            value_constraint=value_constraint,
        ))
        self.touch()
    
    def get_claims_by_credential_type(self, credential_type: str) -> list[RequiredClaim]:
        """Get required claims for a specific credential type."""
        return [c for c in self.required_claims if c.credential_type == credential_type]
    
    def get_min_trust_level(self) -> int | None:
        """Get minimum required trust level for issuers."""
        return self.issuer_constraints.get("min_trust_level")
    
    def get_required_compliance_statuses(self) -> list[str]:
        """Get required compliance statuses for issuers."""
        return self.issuer_constraints.get("required_compliance_statuses", [])
    
    def get_required_accreditations(self) -> list[str]:
        """Get required accreditations for issuers."""
        return self.issuer_constraints.get("required_accreditations", [])
    
    def set_issuer_constraints(
        self,
        min_trust_level: int | None = None,
        required_compliance_statuses: list[str] | None = None,
        required_accreditations: list[str] | None = None,
    ) -> None:
        """
        Set issuer constraints for this policy.
        
        Args:
            min_trust_level: Minimum trust level (0-100) required for issuers
            required_compliance_statuses: Required compliance statuses (e.g., ["ACCREDITED", "COMPLIANT"])
            required_accreditations: Required accreditation standards (e.g., ["ISO27001"])
        """
        if min_trust_level is not None:
            if not 0 <= min_trust_level <= 100:
                raise ValueError("min_trust_level must be between 0 and 100")
            self.issuer_constraints["min_trust_level"] = min_trust_level
        
        if required_compliance_statuses is not None:
            self.issuer_constraints["required_compliance_statuses"] = required_compliance_statuses
        
        if required_accreditations is not None:
            self.issuer_constraints["required_accreditations"] = required_accreditations
        
        self.touch()
    
    def add_required_claim_with_predicate(
        self,
        claim_name: str,
        credential_type: str,
        predicate_spec: PredicateSpecification,
        value_constraint: Any = None,
    ) -> None:
        """
        Add a required claim with a structured ZK predicate specification.
        
        Args:
            claim_name: Name of the claim (e.g., "age", "birth_date")
            credential_type: Type of credential containing this claim
            predicate_spec: Structured ZK predicate specification
            value_constraint: Optional exact value requirement
        """
        self.required_claims.append(RequiredClaim(
            claim_name=claim_name,
            credential_type=credential_type,
            accept_predicate=True,
            value_constraint=value_constraint,
            predicate_spec=predicate_spec,
        ))
        self.touch()
    
    def get_claims_accepting_predicates(self) -> list[RequiredClaim]:
        """Get all required claims that accept ZK predicate proofs."""
        return [c for c in self.required_claims if c.allows_predicate()]
    
    def get_all_supported_circuits(self) -> set[str]:
        """Get all ZK circuits supported by this policy (from policy + claims)."""
        circuits = set(self.supported_circuits)
        for claim in self.required_claims:
            circuits.update(claim.get_supported_circuits())
        return circuits
    
    def is_circuit_supported(self, circuit_id: str) -> bool:
        """Check if a specific ZK circuit is supported by this policy."""
        return circuit_id in self.get_all_supported_circuits()
    
    def get_effective_fallback_policy(self, claim: RequiredClaim) -> PredicateFallbackPolicy:
        """
        Get the effective fallback policy for a specific claim.
        
        Claim-level fallback takes precedence over policy-level fallback.
        """
        claim_fallback = claim.get_fallback_policy()
        # If claim has explicit predicate_spec, use its fallback
        if claim.predicate_spec is not None:
            return claim_fallback
        # Otherwise use policy-level fallback
        return self.fallback_policy


# =============================================================================
# Deployment Profile
# =============================================================================

@dataclass
class Lane(Entity):
    """
    Lane entity - child of Deployment Profile.
    
    A Lane represents a logical grouping of devices (e.g., Gate 12, Checkpoint North)
    under a Deployment Profile. Each lane can have its own default policy override
    and device assignments.
    
    Attributes:
        name: Human-readable name (e.g., "Lane A", "Gate 12")
        deployment_profile_id: Parent Deployment Profile ID
        default_policy_id: Optional lane-specific policy override
        device_ids: List of device IDs assigned to this lane
        metadata: Additional configuration (zone info, operator assignments, etc.)
    """
    
    name: str = ""
    deployment_profile_id: str = ""
    default_policy_id: str | None = None
    device_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def assign_device(self, device_id: str) -> None:
        """Assign a device to this lane."""
        if device_id not in self.device_ids:
            self.device_ids.append(device_id)
            self.touch()
    
    def unassign_device(self, device_id: str) -> None:
        """Remove a device from this lane."""
        if device_id in self.device_ids:
            self.device_ids.remove(device_id)
            self.touch()


@dataclass
class DeploymentProfile(Entity):
    """
    Deployment Profile entity - defines where identity runs.
    
    A Deployment Profile packages identity behavior for real endpoints:
    - Enabled flows and default policies
    - Network mode (online/offline)
    - Device UX configuration
    - Update and rollout rules
    - Key-access strategy
    - Lanes for logical device grouping
    
    Attributes:
        name: Human-readable name for the profile
        description: Optional description
        site_id: Optional site/location identifier
        enabled_flow_ids: List of enabled Flow IDs
        default_presentation_policy_id: Default policy for verifications
        network_mode: Online/offline/hybrid connectivity
        key_access_mode: How signing keys are accessed
        ux_config: User experience configuration
        update_policy: Software update policy
        offline_cache_ttl_hours: Hours to cache trust data offline
        biometric_required: Require biometric verification
        audit_all_events: Log all verification events
        lanes: Child lanes for device grouping
        metadata: Additional configuration
    """
    
    name: str = ""
    description: str | None = None
    site_id: str | None = None
    
    # Organization scoping
    organization_id: str | None = None
    
    # Enabled flows and policies
    enabled_flow_ids: list[str] = field(default_factory=list)
    default_presentation_policy_id: str | None = None
    
    # Network configuration
    network_mode: NetworkMode = NetworkMode.ONLINE
    
    # Key access
    key_access_mode: KeyAccessMode = KeyAccessMode.KEY_VAULT
    
    # UX
    ux_config: UXConfig = field(default_factory=UXConfig)
    
    # Updates
    update_policy: UpdatePolicy = field(default_factory=UpdatePolicy)
    
    # Operational settings
    offline_cache_ttl_hours: int = 24
    biometric_required: bool = False
    audit_all_events: bool = True
    
    # Lanes
    lanes: list[Lane] = field(default_factory=list)
    
    # Extension point
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def is_flow_enabled(self, flow_id: str) -> bool:
        """Check if a flow is enabled for this deployment."""
        return flow_id in self.enabled_flow_ids
    
    def enable_flow(self, flow_id: str) -> None:
        """Enable a flow for this deployment."""
        if flow_id not in self.enabled_flow_ids:
            self.enabled_flow_ids.append(flow_id)
            self.touch()
    
    def disable_flow(self, flow_id: str) -> None:
        """Disable a flow for this deployment."""
        if flow_id in self.enabled_flow_ids:
            self.enabled_flow_ids.remove(flow_id)
            self.touch()


# =============================================================================
# Flow
# =============================================================================

@dataclass
class Flow(Entity):
    """
    Flow entity - orchestrates end-to-end identity journeys.
    
    A Flow ties together:
    - A Trust Profile
    - A Credential Template (if issuing directly)
    - An Application Template (if issuing via application process)
    - A Presentation Policy (if verifying)
    - One or more Deployment Profiles
    - An approval strategy
    
    Flows encode ordering, approvals, state transitions, and auditability.
    The flow type determines the fixed protocol sequence, while hooks
    allow business logic customization.
    
    IMPORTANT: credential_template_id and application_template_id are mutually exclusive.
    Use application_template_id for APPLICATION_APPROVAL_ISSUANCE flows,
    use credential_template_id for direct issuance flows (OID4VCI, MDL_ISSUANCE).
    
    Attributes:
        name: Human-readable name for the flow
        description: Optional description
        flow_type: Type of flow (determines step sequence)
        trust_profile_id: Reference to Trust Profile
        credential_template_id: Reference to Credential Template (for direct issuance)
        application_template_id: Reference to Application Template (for application-based issuance)
        presentation_policy_id: Reference to Presentation Policy (for verification)
        deployment_profile_ids: References to Deployment Profiles
        approval_strategy: How approvals are handled
        enabled: Whether the flow is active
        hooks: Custom hook configurations (pre/post step)
        metadata: Additional configuration
    """
    
    name: str = ""
    description: str | None = None
    flow_type: FlowType = FlowType.APPLICATION_APPROVAL_ISSUANCE
    
    # Organization scope (required by spec)
    organization_id: str = ""
    
    # Flow lifecycle status (DRAFT, ACTIVE, PAUSED, ARCHIVED)
    status: str = "DRAFT"
    
    # Referenced entities
    trust_profile_id: str | None = None
    credential_template_id: str | None = None
    application_template_id: str | None = None  # For application-based issuance
    presentation_policy_id: str | None = None
    deployment_profile_ids: list[str] = field(default_factory=list)
    
    # Approval configuration
    approval_strategy: ApprovalStrategy = ApprovalStrategy.AUTO
    
    # State
    enabled: bool = True
    
    # Extensibility
    hooks: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    
    # Trigger configuration (spec: how the flow is initiated)
    trigger: dict[str, Any] | None = None
    
    # Extension point
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @property
    def flow_category(self) -> str:
        """Derived flow category (read-only, per spec)."""
        from digital_identity.domain.value_objects import FLOW_CATEGORY
        ft = self.flow_type.value if hasattr(self.flow_type, 'value') else str(self.flow_type)
        return FLOW_CATEGORY.get(ft, "ISSUANCE")
    
    def validate(self) -> None:
        """
        Validate flow configuration.
        
        Raises:
            ValueError: If configuration is invalid
        """
        # Mutual exclusivity check
        if self.credential_template_id and self.application_template_id:
            raise ValueError(
                "Flow cannot reference both credential_template_id and "
                "application_template_id. Use one or the other."
            )
        
        # Flow type requirements
        if self.flow_type == FlowType.APPLICATION_APPROVAL_ISSUANCE:
            if not self.application_template_id:
                raise ValueError(
                    f"Flow type {self.flow_type} requires application_template_id"
                )
        elif self.flow_type in (
            FlowType.OID4VCI_PRE_AUTHORIZED,
            FlowType.OID4VCI_AUTHORIZATION_CODE,
            FlowType.MDL_ISSUANCE,
        ):
            if not self.credential_template_id:
                raise ValueError(
                    f"Flow type {self.flow_type} requires credential_template_id"
                )
        elif self.flow_type in (
            FlowType.OID4VP_PRESENTATION,
            FlowType.MDL_PRESENTATION,
        ):
            if not self.presentation_policy_id:
                raise ValueError(
                    f"Flow type {self.flow_type} requires presentation_policy_id"
                )
        elif self.flow_type == FlowType.COMBINED:
            if not self.credential_template_id and not self.application_template_id:
                raise ValueError(
                    f"Flow type {self.flow_type} requires credential_template_id or application_template_id"
                )
            if not self.presentation_policy_id:
                raise ValueError(
                    f"Flow type {self.flow_type} requires presentation_policy_id"
                )
    
    def get_steps(self) -> list:
        """Get the fixed step sequence for this flow type."""
        return FLOW_STEPS.get(self.flow_type, [])
    
    def get_extensible_steps(self) -> list:
        """Get steps that can be customized via hooks."""
        return [s for s in self.get_steps() if s.extensible]
    
    def add_pre_hook(self, step_name: str, hook_config: dict[str, Any]) -> None:
        """Add a pre-execution hook for a step."""
        key = f"pre_{step_name}"
        if key not in self.hooks:
            self.hooks[key] = []
        self.hooks[key].append(hook_config)
        self.touch()
    
    def add_post_hook(self, step_name: str, hook_config: dict[str, Any]) -> None:
        """Add a post-execution hook for a step."""
        key = f"post_{step_name}"
        if key not in self.hooks:
            self.hooks[key] = []
        self.hooks[key].append(hook_config)
        self.touch()
    
    def get_pre_hooks(self, step_name: str) -> list[dict[str, Any]]:
        """Get pre-execution hooks for a step."""
        return self.hooks.get(f"pre_{step_name}", [])
    
    def get_post_hooks(self, step_name: str) -> list[dict[str, Any]]:
        """Get post-execution hooks for a step."""
        return self.hooks.get(f"post_{step_name}", [])


# =============================================================================
# Flow Execution (Runtime State)
# =============================================================================

@dataclass
class FlowExecution(Entity):
    """
    Flow Execution entity - tracks runtime state of a flow instance.
    
    This entity captures the execution state of a specific flow run,
    including current step, status, and step results.
    
    Attributes:
        flow_id: Reference to the Flow being executed
        status: Current execution status
        current_step: Name of the current step
        current_step_index: Index of current step in sequence
        step_results: Results from completed steps
        context_data: Execution context data
        started_at: When execution started
        completed_at: When execution completed (if done)
        error: Error message if failed
        metadata: Additional runtime data
    """
    
    flow_id: str = ""
    flow_type: str = ""  # Copied from Flow at instantiation time
    organization_id: str = ""  # Copied from Flow at instantiation time
    status: FlowStatus = FlowStatus.PENDING
    current_step: str | None = None
    current_step_index: int = 0
    step_results: dict[str, Any] = field(default_factory=dict)
    context_data: dict[str, Any] = field(default_factory=dict)
    issued_credential_id: str | None = None  # ID of credential issued by this execution
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None        # Hard expiry deadline
    error_code: str | None = None             # Terminal error code when status is FAILED
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def start(self) -> None:
        """Mark execution as started."""
        self.status = FlowStatus.IN_PROGRESS
        self.started_at = datetime.now(timezone.utc)
        self.touch()
    
    def complete_step(self, step_name: str, result: Any) -> None:
        """Record step completion."""
        self.step_results[step_name] = {
            "result": result,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        self.current_step_index += 1
        self.touch()
    
    def await_approval(self) -> None:
        """Mark execution as awaiting approval."""
        self.status = FlowStatus.AWAITING_APPROVAL
        self.touch()
    
    def approve(self) -> None:
        """Resume execution after approval (transitions AWAITING_APPROVAL → IN_PROGRESS)."""
        self.status = FlowStatus.IN_PROGRESS
        self.touch()
    
    def reject(self, reason: str | None = None) -> None:
        """Cancel execution on rejection (transitions AWAITING_APPROVAL → CANCELLED)."""
        self.status = FlowStatus.CANCELLED
        if reason:
            self.error_code = reason
        self.touch()
    
    def complete(self) -> None:
        """Mark execution as completed."""
        self.status = FlowStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.touch()
    
    def fail(self, error_code: str) -> None:
        """Mark execution as failed."""
        self.status = FlowStatus.FAILED
        self.error_code = error_code
        self.completed_at = datetime.now(timezone.utc)
        self.touch()
    
    def cancel(self) -> None:
        """Cancel execution."""
        self.status = FlowStatus.CANCELLED
        self.completed_at = datetime.now(timezone.utc)
        self.touch()


# =============================================================================
# Issued Credential
# =============================================================================

@dataclass
class IssuedCredential(Entity):
    """
    Issued Credential entity - tracks an issued credential for lifecycle management.
    
    Links Flow execution to the actual credential and its status entries.
    Stores metadata about the credential without storing the actual credential data
    (only hash for integrity verification).
    
    Attributes:
        credential_id: Unique identifier (urn:uuid:... or custom issuer-defined URI)
        credential_type: Credential type from template
        credential_format: Format (mdoc, sd_jwt_vc, jwt_vc, ldp_vc)
        flow_execution_id: Which FlowExecution issued this
        credential_template_id: Which template was used
        application_id: Source application if any
        subject_id: DID, device key, or holder identifier
        subject_claims_hash: Privacy-preserving hash of subject claims
        issued_at: When credential was issued
        valid_from: Start of validity period
        valid_until: End of validity period
        status: Current status (active, suspended, revoked, expired)
        status_list_entries: References to status list entries
        credential_hash: SHA-256 hash of credential for audit
        revoked_at: When credential was revoked
        revocation_reason: Reason for revocation
        revoked_by: Who revoked the credential
    """
    
    credential_id: str = ""
    credential_type: str = ""
    credential_format: CredentialFormat = CredentialFormat.JWT_VC
    flow_execution_id: str = ""
    credential_template_id: str = ""
    application_id: str | None = None
    revocation_profile_id: str | None = None  # Ref to RevocationProfile
    organization_id: str | None = None  # Multi-tenant scoping
    subject_id: str = ""
    subject_claims_hash: str | None = None
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    status: CredentialStatus = CredentialStatus.ACTIVE
    status_list_entries: list[StatusListEntryRef] = field(default_factory=list)
    credential_hash: str | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None
    revoked_by: str | None = None
    
    def revoke(self, reason: str | None = None, revoked_by: str | None = None) -> None:
        """Mark credential as revoked."""
        self.status = CredentialStatus.REVOKED
        self.revoked_at = datetime.now(timezone.utc)
        self.revocation_reason = reason
        self.revoked_by = revoked_by
        self.touch()
    
    def suspend(self) -> None:
        """Temporarily suspend credential."""
        self.status = CredentialStatus.SUSPENDED
        self.touch()
    
    def reactivate(self) -> None:
        """Reactivate a suspended credential."""
        if self.status == CredentialStatus.SUSPENDED:
            self.status = CredentialStatus.ACTIVE
            self.touch()
    
    def check_expired(self) -> bool:
        """Check if credential has expired."""
        if self.valid_until and datetime.now(timezone.utc) > self.valid_until:
            self.status = CredentialStatus.EXPIRED
            self.touch()
            return True
        return False


class RevocationBatch(Entity):
    """
    Revocation Batch entity - tracks batch revocation operations for privacy.
    
    Implements privacy-preserving revocation by batching updates at regular intervals
    (1h, 6h, or 24h) instead of immediate updates. This prevents timing correlation
    attacks where observing status list changes could reveal which credential was revoked.
    
    Attributes:
        organization_id: Which organization owns this batch
        credential_template_id: Which template these credentials use
        credential_count: Number of credentials in this batch
        credential_ids: List of credential IDs to revoke
        status: Current batch status (queued, processing, completed, failed)
        scheduled_for: When the batch should be processed
        completed_at: When the batch was completed
        revocation_interval: Privacy interval (1h, 6h, 24h)
        error_message: Error message if batch failed
    """
    
    organization_id: str = ""
    credential_template_id: str = ""
    credential_format: str = ""  # Required by spec (MDOC, SD_JWT_VC, VC_JWT, JSON_LD)
    batch_interval: str = "6h"  # 1h, 6h, 24h (spec: batch_interval)
    pending_credential_ids: list[str] = field(default_factory=list)
    published_credential_count: int = 0
    status_list_uri: str | None = None
    status: str = "PENDING"  # PENDING, PUBLISHING, PUBLISHED, FAILED
    scheduled_publish_at: datetime | None = None
    published_at: datetime | None = None
    error_message: str | None = None
    
    def mark_processing(self) -> None:
        """Mark batch as currently processing."""
        self.status = "PUBLISHING"
        self.touch()
    
    def mark_completed(self) -> None:
        """Mark batch as successfully completed."""
        self.status = "PUBLISHED"
        self.published_at = datetime.now(timezone.utc)
        self.touch()
    
    def mark_failed(self, error: str) -> None:
        """Mark batch as failed."""
        self.status = "FAILED"
        self.error_message = error
        self.touch()


# =============================================================================
# Audit Event
# =============================================================================

@dataclass
class AuditEvent:
    """
    Audit Event entity - immutable log of domain events for compliance.
    
    Captures all significant actions on identity resources for:
    - Compliance auditing (who did what, when)
    - Security investigations
    - Change history tracking
    - Event correlation
    
    Attributes:
        event_type: Type of domain event (e.g., FlowCreated, FlowExecutionApproved)
        entity_type: Type of entity affected (e.g., Flow, FlowExecution, TrustProfile)
        entity_id: ID of the entity affected
        action: Human-readable action (e.g., "created", "approved", "rejected")
        payload: Full event data (JSON)
        occurred_at: When the event occurred (from DomainEvent.occurred_at)
        actor_id: ID of the user/system that triggered the event
        correlation_id: ID to correlate related events (e.g., all events in a flow execution)
        id: Unique identifier for the audit event
        created_at: When the audit event was created
        updated_at: When the audit event was last updated (immutable, so always equals created_at)
        version: Version number (always 1 for immutable events)
    """
    
    event_type: str
    entity_type: str
    entity_id: str
    action: str
    payload: dict[str, Any]
    occurred_at: datetime
    actor_id: str | None = None
    correlation_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1


# =============================================================================
# Revocation Profile
# =============================================================================

@dataclass
class RevocationProfile(Entity):
    """Format-agnostic revocation configuration for issuers and verifiers.
    
    Spec: schemas/revocation-profile.json
    
    Attributes:
        organization_id: Owning organization
        name: Human-readable name
        revocation_mechanism: Supported revocation methods (ordered)
        mechanism_priority: Preferred order for checking
        check_mode: Timing behavior for revocation checks
        cache_ttl_seconds: Cache TTL when check_mode is CACHED
        offline_grace_seconds: Grace period when check_mode is OFFLINE_GRACE
        issuer_config: Issuer-side revocation configuration
        status_list_url: Base URI for published status lists
    """
    
    organization_id: str = ""
    name: str = ""
    revocation_mechanism: list[str] = field(default_factory=list)
    mechanism_priority: list[str] = field(default_factory=list)
    check_mode: RevocationTimingMode = RevocationTimingMode.ALWAYS
    cache_ttl_seconds: int | None = None
    offline_grace_seconds: int | None = None
    issuer_config: dict[str, Any] = field(default_factory=dict)
    status_list_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Verification Session
# =============================================================================

@dataclass
class VerificationSession(Entity):
    """A single presentation-request/response cycle instance.
    
    Spec: schemas/verification-session.json
    
    Attributes:
        flow_id: Parent flow
        flow_instance_id: Specific flow execution instance
        presentation_policy_id: Policy governing this session
        deployment_profile_id: Deployment where session runs
        verifier_nonce: Base64url random nonce (min 128 bits)
        holder_id: Holder identifier (set after presentation)
        status: Session lifecycle status
        result: Verification outcome (set on completion)
        expires_at: Session expiry
        completed_at: When verification completed
        error: Error reason if session terminated abnormally
    """
    
    flow_id: str = ""
    flow_instance_id: str | None = None
    presentation_policy_id: str = ""
    deployment_profile_id: str | None = None
    verifier_nonce: str | None = None
    holder_id: str | None = None
    status: str = "PENDING"
    result: dict[str, Any] | None = None
    expires_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


# =============================================================================
# Webhook
# =============================================================================

@dataclass
class Webhook(Entity):
    """Webhook endpoint for event delivery.

    Spec: schemas/webhook.json

    Attributes:
        organization_id: Owning organization
        name: Human-readable name
        endpoint_url: HTTPS endpoint receiving payloads
        events: Event patterns to subscribe to (e.g. ``credential.issued``, ``*``)
        signing_secret_hash: Hashed HMAC signing secret
        signing_secret_masked: Masked display value (readOnly)
        enabled: Whether webhook delivers events
        api_version: Date-based API version (YYYY-MM-DD)
        filter: Optional flow/template scoping
        delivery_config: Timeout, retry and backoff settings
        status: ACTIVE / PAUSED / DISABLED_PERMANENTLY
        failure_count: Consecutive delivery failures
        last_triggered_at: Last delivery attempt
        last_success_at: Last successful delivery
    """

    organization_id: str = ""
    name: str = ""
    description: str | None = None
    endpoint_url: str = ""
    events: list[str] = field(default_factory=list)
    signing_secret_hash: str | None = None
    signing_secret_masked: str | None = None
    enabled: bool = True
    api_version: str | None = None
    filter: dict[str, Any] = field(default_factory=dict)
    delivery_config: dict[str, Any] = field(default_factory=dict)
    status: str = "ACTIVE"
    failure_count: int = 0
    last_triggered_at: datetime | None = None
    last_success_at: datetime | None = None


# =============================================================================
# Subscription
# =============================================================================

@dataclass
class Subscription(Entity):
    """Multi-channel event subscription.

    Spec: schemas/subscription.json

    Attributes:
        organization_id: Owning organization
        name: Human-readable name
        description: Optional description
        event_types: Event patterns to subscribe to
        delivery: Channel config (WEBHOOK / EMAIL / SSE)
        filter: Optional scoping (credential_types, flow_ids, deployment_profile_ids)
        enabled: Whether subscription is active
        retry_policy: Retry configuration
    """

    organization_id: str = ""
    name: str = ""
    description: str | None = None
    event_types: list[str] = field(default_factory=list)
    delivery: dict[str, Any] = field(default_factory=dict)
    filter: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    retry_policy: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# API Key
# =============================================================================

@dataclass
class ApiKey(Entity):
    """Scoped API key for programmatic access.

    Spec: schemas/api-key.json

    Attributes:
        organization_id: Owning organization
        name: Human-readable name
        description: Optional description
        key_prefix: First 8 chars for identification (e.g. ``mk_live_ab``)
        key_hash: Hashed full key (never returned)
        scope_type: ORGANIZATION or DEPLOYMENT
        deployment_profile_id: Required when scope_type is DEPLOYMENT
        scopes: Granted permission scopes
        enabled: Whether key is active
        expires_at: Optional expiry (None = no expiry)
        last_used_at: Last usage timestamp
    """

    organization_id: str = ""
    name: str = ""
    description: str | None = None
    key_prefix: str = ""
    key_hash: str | None = None
    scope_type: str = "ORGANIZATION"
    deployment_profile_id: str | None = None
    scopes: list[str] = field(default_factory=list)
    enabled: bool = True
    expires_at: datetime | None = None
    last_used_at: datetime | None = None


# =============================================================================
# Issuance Record
# =============================================================================

@dataclass
class IssuanceRecord(Entity):
    """OID4VCI credential issuance lifecycle record.

    Spec: schemas/issuance.json
    """

    flow_id: str = ""
    flow_execution_id: str | None = None
    application_id: str | None = None
    credential_template_id: str = ""
    holder_id: str = ""
    credential_id: str | None = None
    credential_format: str = "SD_JWT_VC"
    offer_uri: str | None = None
    offer_expires_at: datetime | None = None
    status: str = "PENDING"
    revocation_index: int | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    claimed_at: datetime | None = None


# =============================================================================
# Policy Set
# =============================================================================

@dataclass
class PolicySet(Entity):
    """Named collection of Cedar policies for authorization.

    Spec: schemas/policy-set.json
    """

    organization_id: str = ""
    name: str = ""
    description: str | None = None
    policy_type: str = "ACCESS_CONTROL"
    cedar_policies: list[dict[str, Any]] = field(default_factory=list)
    cedar_schema_version: str = "MIP/1.0"
    status: str = "DRAFT"


# =============================================================================
# Wallet Profile
# =============================================================================

@dataclass
class WalletProfile(Entity):
    """Wallet compatibility record for format × protocol × compliance.

    Spec: schemas/wallet-profile.json
    """

    organization_id: str | None = None
    is_override: bool = False
    override_precedence: int = 50
    name: str = ""
    description: str | None = None
    credential_format: str = "SD_JWT_VC"
    issuance_protocol: str = "OID4VCI_PRE_AUTH"
    compliance_profile_code: str | None = None
    wallet_apps: list[str] = field(default_factory=list)
    merge_strategy: str = "APPEND"
    specifications: list[str] = field(default_factory=list)
    supported_platforms: list[str] = field(default_factory=list)
    deep_link_pattern: str | None = None


# =============================================================================
# Device Registration
# =============================================================================

@dataclass
class DeviceRegistration(Entity):
    """User device record for push notifications and challenge-response auth.

    Spec: schemas/device-registration.json
    """

    user_id: str = ""
    organization_id: str | None = None
    device_id: str = ""
    platform: str = "ios"
    fcm_token: str = ""
    app_version: str | None = None
    os_version: str | None = None
    device_model: str | None = None
    preferences: dict[str, Any] = field(default_factory=dict)
    public_key_der: str | None = None
    public_key_kid: str | None = None
    key_valid_from: datetime | None = None
    key_valid_until: datetime | None = None
    is_active: bool = True
    last_seen_at: datetime | None = None


# =============================================================================
# Applicant
# =============================================================================

@dataclass
class Applicant(Entity):
    """Person/entity applying for a credential through an application-approval flow.

    Spec: schemas/applicant.json
    """

    organization_id: str = ""
    flow_id: str = ""
    credential_template_id: str | None = None
    user_id: str | None = None
    external_id: str | None = None
    given_name: str = ""
    family_name: str = ""
    email: str | None = None
    phone: str | None = None
    status: str = "DRAFT"
    reviewer_id: str | None = None
    reviewer_lock_expires_at: datetime | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None
    credentialed_at: datetime | None = None
    rejection_reason: str | None = None
    rejection_code: str | None = None
    application_data: dict[str, Any] = field(default_factory=dict)
    vetting_checks: list[dict[str, Any]] = field(default_factory=list)
    issued_credential_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Reviewer Lock
# =============================================================================

@dataclass
class ReviewerLock(Entity):
    """Time-bounded exclusive lock on an applicant for a reviewer.

    Spec: schemas/reviewer-lock.json
    """

    applicant_id: str = ""
    organization_id: str = ""
    holder_user_id: str = ""
    ttl_seconds: int = 1800
    expires_at: datetime | None = None
    released_at: datetime | None = None
    status: str = "ACTIVE"


# =============================================================================
# Vetting Check
# =============================================================================

@dataclass
class VettingCheck(Entity):
    """A discrete identity/document verification check during applicant review.

    Spec: schemas/vetting-check.json
    """

    applicant_id: str = ""
    organization_id: str = ""
    check_type: str = "MANUAL_REVIEW"
    provider: str | None = None
    provider_reference_id: str | None = None
    status: str = "PENDING"
    score: float | None = None
    threshold: float | None = None
    failure_reason: str | None = None
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    performed_by: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    raw_result: dict[str, Any] | None = None


# =============================================================================
# Biometric Enrollment
# =============================================================================

@dataclass
class BiometricEnrollment(Entity):
    """Biometric enrollment record – stores only template hash, never raw data.

    Spec: schemas/biometric-enrollment.json
    """

    applicant_id: str = ""
    organization_id: str = ""
    modality: str = "FACE"
    template_hash: str = ""
    hash_algorithm: str = "SHA-256"
    provider: str | None = None
    capture_device: str | None = None
    quality_score: float | None = None
    liveness_verified: bool = False
    status: str = "ENROLLED"
    revoked_at: datetime | None = None
    revocation_reason: str | None = None


# =============================================================================
# Notification Payload
# =============================================================================

@dataclass
class NotificationPayload(Entity):
    """Multi-channel identity event notification with routing metadata.

    Spec: schemas/notification-payload.json
    NotificationTarget is embedded as the ``target`` dict.
    """

    title: str = ""
    body: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    event_type: str = ""
    priority: str = "NORMAL"
    target: dict[str, Any] = field(default_factory=dict)
    ttl_seconds: int = 86400
    collapse_key: str | None = None
    correlation_id: str | None = None
