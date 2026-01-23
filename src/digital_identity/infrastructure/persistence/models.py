"""
SQLAlchemy Models for Digital Identity

Database models for persisting domain entities.
Uses SQLAlchemy 2.0 async patterns.
"""

from __future__ import annotations

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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    
    type_annotation_map = {
        dict[str, Any]: JSON,  # Use JSON instead of JSONB for SQLite compatibility
        list[str]: JSON,
        list[dict[str, Any]]: JSON,
    }


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
    anchor_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 'csca', 'iaca', 'eudi_qtsp'
    jurisdiction: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)  # 'US-CA', 'DE', etc.
    
    # Certificate data
    certificate_der: Mapped[bytes] = mapped_column(nullable=False)
    certificate_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 hash for deduplication
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    issuer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    not_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Sync metadata
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # 'icao_pkd', 'aamva_dts', 'eudi_lotl'
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
    allowed_formats: Mapped[list[str]] = mapped_column(JSON, default=list)
    revocation_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    time_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Issuer constraints
    allowed_issuers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    denied_issuers: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    
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
    
    # Claims
    claims: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    
    # Validity
    validity_rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Issuer constraints
    issuer_key_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    trust_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_trust_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Format
    format: Mapped[str] = mapped_column(String(50), default="sd_jwt_vc", nullable=False)
    namespace: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
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
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    
    # Format configuration
    credential_format: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Artifact requirements (JSON serialized IssuerArtifactRequirements)
    issuer_artifact_requirements: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    
    # Default verification rules
    default_claim_verification_rules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    
    # Trust profile requirements
    trust_profile_requirements: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # System flag
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
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
    credential_template_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("digital_identity_credential_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    compliance_profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("digital_identity_compliance_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    
    # Evidence and verification requirements
    evidence_requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    claim_verification_rules: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    
    # Issuer artifact configuration
    issuer_key_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issuer_certificate_chain_pem: Mapped[str | None] = mapped_column(Text, nullable=True)
    issuer_did: Mapped[str | None] = mapped_column(String(500), nullable=True)
    auto_generate_artifacts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Workflow configuration
    approval_strategy: Mapped[str] = mapped_column(String(50), default="auto", nullable=False)
    application_validity_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    
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
    
    # Accepted credentials
    accepted_credential_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    
    # Required claims
    required_claims: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    
    # Holder binding
    holder_binding: Mapped[str] = mapped_column(String(50), default="session_nonce", nullable=False)
    
    # Trust constraints
    trust_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_trust_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    allowed_issuers: Mapped[list[str]] = mapped_column(JSON, default=list)
    
    # Freshness
    freshness_requirements: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Data minimization
    prefer_predicates: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    single_presentation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    derived_attribute_preferences: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    
    # Credential ranking
    credential_ranking_strategy: Mapped[str] = mapped_column(String(50), default="freshest_first", nullable=False)
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
    approval_strategy: Mapped[str] = mapped_column(String(50), default="auto", nullable=False)
    
    # State
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Extensibility
    hooks: Mapped[dict[str, list[dict[str, Any]]]] = mapped_column(JSON, default=dict)
    
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
    
    # State
    status: Mapped[str] = mapped_column(String(50), default="created", nullable=False, index=True)
    current_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_step_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Results
    step_results: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    context_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    issued_credential_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    
    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Error
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    
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
    
    # Subject
    subject_id: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    subject_claims_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    
    # Validity
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
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
