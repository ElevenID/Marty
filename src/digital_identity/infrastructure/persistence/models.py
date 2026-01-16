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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    
    type_annotation_map = {
        dict[str, Any]: JSONB,
        list[str]: JSONB,
        list[dict[str, Any]]: JSONB,
    }


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
    use_case_tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    auto_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    compliance_status: Mapped[str] = mapped_column(String(50), default="SETUP_REQUIRED", nullable=False)
    manually_configured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Trust configuration
    trust_sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    allowed_algorithms: Mapped[list[str]] = mapped_column(JSONB, default=list)
    allowed_formats: Mapped[list[str]] = mapped_column(JSONB, default=list)
    revocation_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    time_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    # Issuer constraints
    allowed_issuers: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    denied_issuers: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    
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
    claims: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    
    # Validity
    validity_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    # Issuer constraints
    issuer_key_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    trust_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_trust_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Format
    format: Mapped[str] = mapped_column(String(50), default="sd_jwt_vc", nullable=False)
    namespace: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Display
    display: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    
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
    accepted_credential_types: Mapped[list[str]] = mapped_column(JSONB, default=list)
    
    # Required claims
    required_claims: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    
    # Holder binding
    holder_binding: Mapped[str] = mapped_column(String(50), default="session_nonce", nullable=False)
    
    # Trust constraints
    trust_profile_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_trust_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    
    # Freshness
    freshness_requirements: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    # Data minimization
    prefer_predicates: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    single_presentation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    
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
    enabled_flow_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
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
    ux_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    # Updates
    update_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    # Operational
    offline_cache_ttl_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    biometric_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    audit_all_events: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    
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
    presentation_policy_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("digital_identity_presentation_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    deployment_profile_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    
    # Approval
    approval_strategy: Mapped[str] = mapped_column(String(50), default="auto", nullable=False)
    
    # State
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Extensibility
    hooks: Mapped[dict[str, list[dict[str, Any]]]] = mapped_column(JSONB, default=dict)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    
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
    step_results: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    context_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Error
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Relationships
    flow: Mapped["FlowModel"] = relationship("FlowModel", back_populates="executions")
