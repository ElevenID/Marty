"""
SQLAlchemy Models for Digital Identity

Database models for persisting domain entities.
Uses SQLAlchemy 2.0 async patterns.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class PublishStatus(str, enum.Enum):
    """Publish status for credential templates."""
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


class Base(DeclarativeBase):
    """Base class for all models."""
    
    type_annotation_map = {
        dict[str, Any]: JSON,  # Use JSON instead of JSONB for SQLite compatibility
        list[str]: JSON,
        list[dict[str, Any]]: JSON,
    }


class OrganizationModel(Base):
    """SQLAlchemy model for Organization (primary multi-tenant boundary)."""

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[str] = mapped_column(String(20), default="PRIVATE", nullable=False)
    owner_id: Mapped[str] = mapped_column(String(255), nullable=False)
    join_code: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TrustFrameworkModel(Base):
    """SQLAlchemy model for Trust Framework (system-level, shared across all orgs)."""
    
    __tablename__ = "trust_frameworks"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Framework configuration
    pkd_endpoints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # Official PKD URLs
    default_algorithms: Mapped[list[str]] = mapped_column(JSON, default=list)  # Required algorithms
    default_formats: Mapped[list[str]] = mapped_column(JSON, default=list)     # Supported formats
    validation_ruleset: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # Framework rules
    sync_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)    # How to refresh trust data
    
    # System flag
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TrustFrameworkAnchorModel(Base):
    """SQLAlchemy model for Trust Framework Anchors (global trust anchors synced from PKD)."""
    
    __tablename__ = "trust_framework_anchors"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    framework_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("trust_frameworks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Anchor metadata
    anchor_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 'csca', 'iaca', 'eudi_qtsp', 'issuer_did'
    jurisdiction: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)  # 'US-CA', 'DE', etc.
    
    # Certificate data (nullable for DID-based anchors)
    certificate_der: Mapped[bytes | None] = mapped_column(nullable=True)
    certificate_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # SHA-256 hash for deduplication
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    issuer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    not_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # DID / JWK data (for Open Badge and other DID-based anchors)
    issuer_did: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    issuer_jwk: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    
    # Sync metadata
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # 'icao_pkd', 'aamva_dts', 'eudi_lotl', 'pinned_issuer'
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    __table_args__ = (
        # Unique constraint on framework + certificate hash
        # Prevents duplicate anchors per framework
    )


class OrganizationTrustProfileModel(Base):
    """SQLAlchemy model for Organization Trust Profile (org-specific configuration)."""
    
    __tablename__ = "organization_trust_profiles"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    framework_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("trust_frameworks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Business context
    use_case_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    compliance_status: Mapped[str] = mapped_column(String(50), default="SETUP_REQUIRED", nullable=False)
    auto_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Policy overrides (NULL = use framework defaults)
    revocation_policy: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    time_policy: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    allowed_algorithms: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    allowed_formats: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    
    # Issuer constraints
    allowed_issuers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    denied_issuers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    jurisdiction_filter: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # ['US-CA', 'US-NY']
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    __table_args__ = (
        # Unique constraint on organization + name
    )


class OrganizationCustomAnchorModel(Base):
    """SQLAlchemy model for Organization Custom Anchors (BYOK certificates)."""
    
    __tablename__ = "organization_custom_anchors"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organization_trust_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Anchor metadata
    anchor_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'root_ca', 'intermediate', 'leaf'
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # Certificate data
    certificate_pem: Mapped[str] = mapped_column(Text, nullable=False)
    certificate_der: Mapped[bytes] = mapped_column(nullable=False)
    not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    not_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Purpose
    purpose: Mapped[str] = mapped_column(String(50), nullable=False, default="verification")  # 'signing', 'verification', 'both'
    
    # Upload metadata
    uploaded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# Legacy model - kept for backwards compatibility during transition
class TrustProfileModel(Base):
    """SQLAlchemy model for Trust Profile."""
    
    __tablename__ = "digital_identity_trust_profiles"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Organization scoping (v2)
    organization_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    use_case_tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    auto_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    compliance_status: Mapped[str] = mapped_column(String(50), default="SETUP_REQUIRED", nullable=False)
    manually_configured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Trust configuration
    trust_sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    allowed_algorithms: Mapped[list[str]] = mapped_column(JSON, default=list)
    supported_formats: Mapped[list[str]] = mapped_column(JSON, default=list)
    revocation_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    time_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Revocation service configuration
    # Structure: {
    #   "enabled_methods": ["CRL", "OCSP", "STATUS_LIST"],
    #   "auto_discover": true,
    #   "merge_discovered": false,
    #   "crl_endpoints": ["https://..."],
    #   "ocsp_urls": ["https://..."],
    #   "status_list_urls": ["https://..."]
    # }
    revocation_services: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Revocation profile reference
    revocation_profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    
    # Issuer constraints
    allowed_issuers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    denied_issuers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    
    # System issuer overrides
    # Structure: {"issuer_id": {"action": "DENY" | "DOWNGRADE", "trust_level": 50, "reason": "..."}, ...}
    # Allows organizations to override trust for system issuers (ICAO/AAMVA)
    system_issuer_overrides: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Unique constraints
    __table_args__ = (
        # Composite unique: (organization_id, name)
        # Allows same name across different organizations
        # But ensures unique names within an organization
        # Index constraint for partial unique (org, type) WHERE enabled AND type != 'CUSTOM'
        # is handled in migration SQL
    )


class CredentialTemplateModel(Base):
    """SQLAlchemy model for Credential Template."""
    
    __tablename__ = "digital_identity_credential_templates"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_type: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    schema_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # Publish status
    status: Mapped[PublishStatus] = mapped_column(
        SQLEnum(PublishStatus),
        default=PublishStatus.DRAFT,
        nullable=False,
        index=True,
    )
    
    # References to required entities
    compliance_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_compliance_profiles.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    application_template_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_application_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trust_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_trust_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    # Claims
    claims: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    
    # Validity
    validity_rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Organization scoping
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    
    # Revocation profile reference
    revocation_profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    
    # Issuer cryptographic configuration
    issuer_key_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issuer_algorithm: Mapped[str | None] = mapped_column(String(50), nullable=True)
    key_access_mode: Mapped[str] = mapped_column(String(50), default="key_vault", nullable=False)
    issuer_key_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # Legacy
    issuer_certificate_chain_pem: Mapped[str | None] = mapped_column(Text, nullable=True)
    issuer_did: Mapped[str | None] = mapped_column(String(500), nullable=True)
    auto_generate_artifacts: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Format
    format: Mapped[str] = mapped_column(String(50), default="sd_jwt_vc", nullable=False)
    namespace: Mapped[str | None] = mapped_column(String(255), nullable=True)
    privacy_posture: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    vct: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # Display
    display: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ComplianceProfileModel(Base):
    """SQLAlchemy model for Compliance Profile."""
    
    __tablename__ = "digital_identity_compliance_profiles"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    compliance_code: Mapped[str] = mapped_column("code", String(100), nullable=False, unique=True, index=True)
    
    # Format configuration
    credential_format: Mapped[str] = mapped_column(String(50), nullable=False)
    issuance_protocol: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    
    # Artifact requirements (JSON serialized IssuerArtifactRequirements)
    issuer_artifact_requirements: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    
    # Default verification rules
    default_verification_rules: Mapped[list[dict[str, Any]]] = mapped_column("default_claim_verification_rules", JSON, default=list)
    
    # Trust profile constraints
    trust_profile_constraints: Mapped[dict[str, Any]] = mapped_column("trust_profile_requirements", JSON, default=dict)
    
    # System flag
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Organization
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    discoverable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class ApplicationTemplateModel(Base):
    """SQLAlchemy model for Application Template."""
    
    __tablename__ = "digital_identity_application_templates"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # References
    credential_template_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_credential_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    compliance_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_compliance_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    
    # Organization scoping
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    
    # Publish status (DRAFT → ACTIVE → DEPRECATED)
    status: Mapped[str] = mapped_column(String(50), default="DRAFT", nullable=False)
    
    # Evidence and verification requirements
    evidence_requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    claim_verification_rules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    
    # Form fields and claim collection
    form_fields: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    claim_collection_rules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    
    # Legacy issuer artifact configuration (moved to CredentialTemplate)
    issuer_key_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issuer_certificate_chain_pem: Mapped[str | None] = mapped_column(Text, nullable=True)
    issuer_did: Mapped[str | None] = mapped_column(String(500), nullable=True)
    auto_generate_artifacts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Workflow configuration
    approval_strategy: Mapped[str] = mapped_column(String(50), default="auto", nullable=False)
    application_validity_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    
    # Notification and UI configuration
    notifications: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ui_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class PresentationPolicyModel(Base):
    """SQLAlchemy model for Presentation Policy."""
    
    __tablename__ = "digital_identity_presentation_policies"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    organization_id: Mapped[str] = mapped_column(String(36), default="", nullable=False, index=True)
    
    # Accepted credentials
    accepted_credential_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    
    # Required claims
    required_claims: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    
    # Holder binding
    holder_binding: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    
    # ZK predicate configuration
    fallback_policy: Mapped[str] = mapped_column(String(50), default="ACCEPT_RAW", nullable=False)
    supported_circuits: Mapped[list[str]] = mapped_column(JSON, default=list)
    
    # Trust constraints
    trust_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_trust_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    allowed_issuers: Mapped[list[str]] = mapped_column(JSON, default=list)
    
    # Issuer constraints (enforced at verification time)
    issuer_constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Freshness
    freshness_requirements: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Data minimization
    prefer_predicates: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    single_presentation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    derived_attribute_preferences: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    
    # Credential ranking
    credential_ranking_strategy: Mapped[str] = mapped_column(String(50), default="FRESHEST_FIRST", nullable=False)
    credential_ranking_weights: Mapped[dict[str, float]] = mapped_column(JSON, default=dict)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class DeploymentProfileModel(Base):
    """SQLAlchemy model for Deployment Profile."""
    
    __tablename__ = "digital_identity_deployment_profiles"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    site_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True, index=True)
    
    # Enabled flows
    enabled_flow_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    default_presentation_policy_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_presentation_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Network
    network_mode: Mapped[str] = mapped_column(String(50), default="online", nullable=False)
    
    # Key access
    key_access_mode: Mapped[str] = mapped_column(String(50), default="key_vault", nullable=False)
    
    # UX
    ux_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Updates
    update_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Operational
    offline_cache_ttl_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    biometric_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    audit_all_events: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Organization scoping
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    
    # Lanes (serialized child entities)
    lanes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class FlowModel(Base):
    """SQLAlchemy model for Flow."""
    
    __tablename__ = "digital_identity_flows"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    flow_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # References
    trust_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_trust_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    credential_template_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_credential_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    application_template_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_application_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    presentation_policy_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_presentation_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    deployment_profile_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    
    # Approval
    approval_strategy: Mapped[str] = mapped_column(String(50), default="AUTO", nullable=False)
    
    # State
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Flow status (DRAFT, ACTIVE, PAUSED, ARCHIVED)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False, index=True)
    
    # Organization scope
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, default="")
    
    # Extensibility
    hooks: Mapped[dict[str, list[dict[str, Any]]]] = mapped_column(JSON, default=dict)
    
    # Trigger configuration
    trigger: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Relationships
    executions: Mapped[list["FlowExecutionModel"]] = relationship(
        "FlowExecutionModel",
        back_populates="flow",
        cascade="all, delete-orphan",
    )


class FlowExecutionModel(Base):
    """SQLAlchemy model for Flow Execution."""
    
    __tablename__ = "digital_identity_flow_executions"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    flow_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("digital_identity_flows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Denormalized from Flow at instantiation
    flow_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True, default="")
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, default="")
    
    # State
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False, index=True)
    current_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_step_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Results
    step_results: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    context_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    issued_credential_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    
    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Error
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Relationships
    flow: Mapped["FlowModel"] = relationship("FlowModel", back_populates="executions")


class IssuedCredentialModel(Base):
    """SQLAlchemy model for Issued Credential."""
    
    __tablename__ = "digital_identity_issued_credentials"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    
    # Credential identification
    credential_id: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    credential_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    credential_format: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # Lineage
    flow_execution_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("digital_identity_flow_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    credential_template_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    application_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    revocation_profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    
    # Subject
    subject_id: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    subject_claims_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    
    # Validity
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False, index=True)
    status_list_entries: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    
    # Audit (do NOT store actual credential, only hash)
    credential_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    
    # Revocation
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class RevocationBatchModel(Base):
    """SQLAlchemy model for Revocation Batch - tracks batch revocation operations."""
    
    __tablename__ = "digital_identity_revocation_batches"
    
    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    
    # Organization context
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    
    # Template identification
    credential_template_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    
    # Batch metadata
    credential_format: Mapped[str] = mapped_column(String(50), nullable=False, index=True, default="")
    batch_interval: Mapped[str] = mapped_column(String(10), nullable=False, default="6h")  # 1h, 6h, 24h
    
    # Credential tracking
    pending_credential_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    published_credential_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status_list_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    
    # Status tracking
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    # Status values: PENDING, PUBLISHING, PUBLISHED, FAILED
    
    # Scheduling
    scheduled_publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class IssuerEntityModel(Base):
    """
    SQLAlchemy model for Issuer Entity.
    
    Represents a trusted issuer with lifecycle management, separate from Trust Anchors.
    Supports organization scoping and system issuers (ICAO/AAMVA).
    """
    
    __tablename__ = "digital_identity_issuers"
    
    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    
    # Organization scoping (NULL = global/system issuer)
    organization_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    
    # Issuer identification
    issuer_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)  # DID or identifier
    issuer_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # ORGANIZATION, GOVERNMENT, DEVICE
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # System issuer flag (auto-visible to all orgs, e.g., ICAO/AAMVA issuers)
    is_system_issuer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    
    # Compliance and accreditation
    compliance_status: Mapped[str] = mapped_column(
        String(50), default="COMPLIANT", nullable=False, index=True
    )  # ACCREDITED, COMPLIANT, SUSPENDED, REVOKED
    accreditation_body: Mapped[str | None] = mapped_column(String(255), nullable=True)
    accreditation_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Validity period
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    
    # Link to trust anchor (optional, for X.509-based issuers)
    trust_anchor_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    
    # Revocation
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class TrustProfileIssuerModel(Base):
    """
    SQLAlchemy model for Trust Profile to Issuer relationship.
    
    Join table with additional relationship metadata including trust level and cascade policy.
    """
    
    __tablename__ = "digital_identity_trust_profile_issuers"
    
    # Standalone UUID primary key (spec requires addressable id)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    
    # Relationship keys (unique together)
    trust_profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("digital_identity_trust_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    issuer_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("digital_identity_issuers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    __table_args__ = (
        UniqueConstraint("trust_profile_id", "issuer_id", name="uq_trust_profile_issuer"),
    )
    
    # Relationship metadata
    trust_level: Mapped[int] = mapped_column(Integer, default=100, nullable=False)  # 0-100 score
    # TODO: Future feature - auto-adjust trust_level based on issuer history (validation failures, revocation events)
    relationship_status: Mapped[str] = mapped_column(
        String(50), default="TRUSTED", nullable=False, index=True
    )  # TRUSTED, DENIED, UNDER_REVIEW
    
    # Cascade policy for issuer revocation
    cascade_revocation_policy: Mapped[str] = mapped_column(
        String(50), default="MANUAL", nullable=False
    )  # AUTO_CASCADE, MANUAL, NOTIFY_ONLY
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class CascadeRevocationOperationModel(Base):
    """
    SQLAlchemy model for Cascade Revocation Operation.
    
    Tracks cascade revocation operations with rollback support.
    When an issuer or trust anchor is revoked, tracks affected credentials.
    """
    
    __tablename__ = "digital_identity_cascade_operations"
    
    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    
    # Organization scoping
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    
    # Operation metadata
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # ISSUER_REVOCATION, ANCHOR_REVOCATION
    trigger_entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ISSUER, TRUST_ANCHOR
    trigger_entity_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Status tracking
    status: Mapped[str] = mapped_column(
        String(50), default="PENDING_CONFIRMATION", nullable=False, index=True
    )  # PENDING_CONFIRMATION, IN_PROGRESS, COMPLETED, ROLLED_BACK, FAILED
    
    # Impact assessment
    affected_credential_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    affected_credential_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    
    # Confirmation requirement (for high-impact operations)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Cascade depth and circuit breaker
    max_cascade_depth: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    current_depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    circuit_breaker_threshold: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    circuit_breaker_triggered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Rollback support
    can_rollback: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rollback_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # Stores pre-revocation state
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class AuditEventModel(Base):
    """SQLAlchemy model for Audit Event."""
    
    __tablename__ = "digital_identity_audit_events"
    
    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    
    # Event identification
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    
    # Actor and action
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # Event data
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    
    # Correlation
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    
    # Timestamps
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class RevocationProfileModel(Base):
    """SQLAlchemy model for Revocation Profile."""
    
    __tablename__ = "digital_identity_revocation_profiles"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    
    # Revocation mechanisms
    revocation_mechanism: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    mechanism_priority: Mapped[list[str]] = mapped_column(JSON, default=list)
    
    # Check timing
    check_mode: Mapped[str] = mapped_column(String(50), default="ALWAYS", nullable=False)
    cache_ttl_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offline_grace_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Issuer config
    issuer_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status_list_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class VerificationSessionModel(Base):
    """SQLAlchemy model for Verification Session."""
    
    __tablename__ = "digital_identity_verification_sessions"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    
    # References
    flow_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("digital_identity_flows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    flow_instance_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    presentation_policy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("digital_identity_presentation_policies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    deployment_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_deployment_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Session data
    verifier_nonce: Mapped[str | None] = mapped_column(String(255), nullable=True)
    holder_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False, index=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    
    # Timing
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Error
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class WebhookModel(Base):
    """SQLAlchemy model for Webhook."""

    __tablename__ = "webhooks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    endpoint_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    events: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    signing_secret_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signing_secret_masked: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    api_version: Mapped[str | None] = mapped_column(String(10), nullable=True)
    filter: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    delivery_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SubscriptionModel(Base):
    """SQLAlchemy model for Subscription."""

    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_types: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    delivery: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    filter: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    retry_policy: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApiKeyModel(Base):
    """SQLAlchemy model for API Key."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    key_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(20), default="ORGANIZATION", nullable=False)
    deployment_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_deployment_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IssuanceRecordModel(Base):
    """SQLAlchemy model for IssuanceRecord (OID4VCI offer lifecycle)."""

    __tablename__ = "issuance_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    flow_id: Mapped[str] = mapped_column(String(36), ForeignKey("digital_identity_flows.id", ondelete="CASCADE"), nullable=False, index=True)
    flow_execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    application_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    credential_template_id: Mapped[str] = mapped_column(String(36), ForeignKey("digital_identity_credential_templates.id", ondelete="RESTRICT"), nullable=False, index=True)
    holder_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    credential_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credential_format: Mapped[str] = mapped_column(String(20), default="SD_JWT_VC", nullable=False)
    offer_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    revocation_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PolicySetModel(Base):
    """SQLAlchemy model for PolicySet (Cedar policy collections)."""

    __tablename__ = "policy_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_type: Mapped[str] = mapped_column(String(30), default="ACCESS_CONTROL", nullable=False)
    cedar_policies: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    cedar_schema_version: Mapped[str] = mapped_column(String(20), default="MIP/1.0", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WalletProfileModel(Base):
    """SQLAlchemy model for WalletProfile (wallet compatibility records)."""

    __tablename__ = "wallet_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    is_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    override_precedence: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_format: Mapped[str] = mapped_column(String(20), nullable=False)
    issuance_protocol: Mapped[str] = mapped_column(String(30), nullable=False)
    compliance_profile_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    wallet_apps: Mapped[list[str]] = mapped_column(JSON, default=list)
    merge_strategy: Mapped[str] = mapped_column(String(10), default="APPEND", nullable=False)
    specifications: Mapped[list[str]] = mapped_column(JSON, default=list)
    supported_platforms: Mapped[list[str]] = mapped_column(JSON, default=list)
    deep_link_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DeviceRegistrationModel(Base):
    """SQLAlchemy model for DeviceRegistration."""

    __tablename__ = "device_registrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    device_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(10), nullable=False)
    fcm_token: Mapped[str] = mapped_column(Text, nullable=False)
    app_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    device_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    preferences: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    public_key_der: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_key_kid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    key_valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    key_valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApplicantModel(Base):
    """SQLAlchemy model for Applicant."""

    __tablename__ = "applicants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    flow_id: Mapped[str] = mapped_column(String(36), ForeignKey("digital_identity_flows.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_template_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    external_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    given_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    family_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", nullable=False, index=True)
    reviewer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewer_lock_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    credentialed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    application_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    vetting_checks: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    issued_credential_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReviewerLockModel(Base):
    """SQLAlchemy model for ReviewerLock."""

    __tablename__ = "reviewer_locks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    applicant_id: Mapped[str] = mapped_column(String(36), ForeignKey("applicants.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    holder_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class VettingCheckModel(Base):
    """SQLAlchemy model for VettingCheck."""

    __tablename__ = "vetting_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    applicant_id: Mapped[str] = mapped_column(String(36), ForeignKey("applicants.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    check_type: Mapped[str] = mapped_column(String(30), default="MANUAL_REVIEW", nullable=False)
    provider: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_reference_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    score: Mapped[float | None] = mapped_column(nullable=True)
    threshold: Mapped[float | None] = mapped_column(nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_refs: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    performed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BiometricEnrollmentModel(Base):
    """SQLAlchemy model for BiometricEnrollment."""

    __tablename__ = "biometric_enrollments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    applicant_id: Mapped[str] = mapped_column(String(36), ForeignKey("applicants.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    modality: Mapped[str] = mapped_column(String(20), nullable=False)
    template_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    hash_algorithm: Mapped[str] = mapped_column(String(10), default="SHA-256", nullable=False)
    provider: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capture_device: Mapped[str | None] = mapped_column(String(256), nullable=True)
    quality_score: Mapped[float | None] = mapped_column(nullable=True)
    liveness_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ENROLLED", nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationPayloadModel(Base):
    """SQLAlchemy model for NotificationPayload."""

    __tablename__ = "notification_payloads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(10), default="NORMAL", nullable=False)
    target: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=86400, nullable=False)
    collapse_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
