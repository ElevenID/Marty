"""Database models for VDS-NC key management and trust store."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from marty_common.crypto.vds_nc_keys import KeyRole, KeyStatus

Base = declarative_base()


class VDSNCKeyModel(Base):
    """Database model for VDS-NC keys."""

    __tablename__ = "vds_nc_keys"

    # Primary key
    kid: Mapped[str] = mapped_column(String(255), primary_key=True)

    # Key metadata
    issuer_country: Mapped[str] = mapped_column(String(3), nullable=False)  # ISO 3166-1 alpha-3
    role: Mapped[KeyRole] = mapped_column(Enum(KeyRole), nullable=False)
    status: Mapped[KeyStatus] = mapped_column(
        Enum(KeyStatus), nullable=False, default=KeyStatus.ACTIVE
    )
    algorithm: Mapped[str] = mapped_column(String(10), nullable=False, default="ES256")

    # Key validity period
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Rotation information
    rotation_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    superseded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supersedes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Key material (stored as JWK)
    public_key_jwk: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    private_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata and tracking
    custom_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Revocation information
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Trust and distribution
    is_trusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    distribution_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Indexes for efficient queries
    __table_args__ = (
        Index("idx_vds_nc_keys_country", "issuer_country"),
        Index("idx_vds_nc_keys_role", "role"),
        Index("idx_vds_nc_keys_status", "status"),
        Index("idx_vds_nc_keys_validity", "not_before", "not_after"),
        Index("idx_vds_nc_keys_country_role", "issuer_country", "role"),
        Index("idx_vds_nc_keys_active", "status", "not_before", "not_after"),
        Index("idx_vds_nc_keys_rotation", "rotation_generation", "issuer_country", "role"),
    )

    def is_valid_at(self, timestamp: datetime) -> bool:
        """Check if key is valid at given timestamp."""
        return (
            self.status == KeyStatus.ACTIVE
            and self.not_before <= timestamp <= self.not_after
            and self.is_trusted
        )

    def is_valid_now(self) -> bool:
        """Check if key is currently valid."""
        return self.is_valid_at(datetime.now(timezone.utc))

    def needs_rotation(self, warning_days: int = 30) -> bool:
        """Check if key needs rotation soon."""
        if self.status != KeyStatus.ACTIVE:
            return False

        from datetime import timedelta

        warning_time = datetime.now(timezone.utc) + timedelta(days=warning_days)
        return self.not_after <= warning_time


class CSCAKeyModel(Base):
    """Database model for CSCA keys (Country Signing CA)."""

    __tablename__ = "csca_keys"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Certificate identifier
    subject_key_identifier: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    authority_key_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Issuer information
    issuer_country: Mapped[str] = mapped_column(String(3), nullable=False)  # ISO 3166-1 alpha-3
    issuer_dn: Mapped[str] = mapped_column(Text, nullable=False)
    subject_dn: Mapped[str] = mapped_column(Text, nullable=False)

    # Certificate data
    certificate_pem: Mapped[str] = mapped_column(Text, nullable=False)
    serial_number: Mapped[str] = mapped_column(String(255), nullable=False)

    # Validity period
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Status and metadata
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    is_trusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    custom_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Tracking
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Revocation
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Indexes
    __table_args__ = (
        Index("idx_csca_keys_country", "issuer_country"),
        Index("idx_csca_keys_status", "status"),
        Index("idx_csca_keys_validity", "not_before", "not_after"),
        Index("idx_csca_keys_ski", "subject_key_identifier"),
        Index("idx_csca_keys_active", "status", "is_trusted", "not_before", "not_after"),
    )


class DSCKeyModel(Base):
    """Database model for DSC keys (Document Signer Certificate)."""

    __tablename__ = "dsc_keys"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Certificate identifier
    subject_key_identifier: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    authority_key_identifier: Mapped[str] = mapped_column(String(255), nullable=False)

    # Issuer information
    issuer_country: Mapped[str] = mapped_column(String(3), nullable=False)
    issuer_dn: Mapped[str] = mapped_column(Text, nullable=False)
    subject_dn: Mapped[str] = mapped_column(Text, nullable=False)

    # Certificate data
    certificate_pem: Mapped[str] = mapped_column(Text, nullable=False)
    serial_number: Mapped[str] = mapped_column(String(255), nullable=False)

    # Validity period
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Status and metadata
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    is_trusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    document_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    custom_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Chain validation
    csca_ski: Mapped[str] = mapped_column(String(255), nullable=False)  # References CSCA
    chain_validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_validation: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Tracking
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Revocation
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Indexes
    __table_args__ = (
        Index("idx_dsc_keys_country", "issuer_country"),
        Index("idx_dsc_keys_status", "status"),
        Index("idx_dsc_keys_validity", "not_before", "not_after"),
        Index("idx_dsc_keys_ski", "subject_key_identifier"),
        Index("idx_dsc_keys_aki", "authority_key_identifier"),
        Index("idx_dsc_keys_csca", "csca_ski"),
        Index("idx_dsc_keys_active", "status", "is_trusted", "not_before", "not_after"),
        Index("idx_dsc_keys_validation", "chain_validated", "last_validation"),
    )


class TrustStoreSnapshot(Base):
    """Database model for trust store snapshots."""

    __tablename__ = "trust_store_snapshots"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Snapshot metadata
    snapshot_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    country_code: Mapped[str | None] = mapped_column(String(3), nullable=True)  # None for global
    format_version: Mapped[str] = mapped_column(String(10), nullable=False, default="1.0")

    # Content counts
    csca_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dsc_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vds_nc_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Snapshot data (compressed JSON)
    snapshot_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Distribution tracking
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_downloaded: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Indexes
    __table_args__ = (
        Index("idx_trust_snapshots_country", "country_code"),
        Index("idx_trust_snapshots_current", "is_current", "created_at"),
        Index("idx_trust_snapshots_hash", "data_hash"),
        Index("idx_trust_snapshots_expires", "expires_at"),
    )


class KeyRotationLog(Base):
    """Database model for key rotation audit log."""

    __tablename__ = "key_rotation_log"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Key information
    key_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "vds_nc", "csca", "dsc"
    key_id: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer_country: Mapped[str] = mapped_column(String(3), nullable=False)

    # Rotation details
    action: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "created", "rotated", "revoked"
    old_key_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    new_key_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Timing
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Status and metadata
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    rotation_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Indexes
    __table_args__ = (
        Index("idx_rotation_log_key", "key_type", "key_id"),
        Index("idx_rotation_log_country", "issuer_country"),
        Index("idx_rotation_log_action", "action", "executed_at"),
        Index("idx_rotation_log_status", "status"),
        Index("idx_rotation_log_timeline", "executed_at"),
    )


class TrustAnchor(Base):
    """Database model for trust anchors."""

    __tablename__ = "trust_anchors"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Entity identification
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "country", "organization", etc.
    entity_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Trust status
    is_trusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trust_level: Mapped[str] = mapped_column(String(20), nullable=False, default="none")

    # Configuration
    allowed_document_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    security_policies: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Metadata
    custom_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Indexes
    __table_args__ = (
        Index("idx_trust_anchors_entity", "entity_id"),
        Index("idx_trust_anchors_type", "entity_type"),
        Index("idx_trust_anchors_trusted", "is_trusted", "trust_level"),
    )


# Migration script for database setup
def create_migration_script() -> str:
    """Generate Alembic migration script."""
    return '''"""Add VDS-NC key management and enhanced trust store

Revision ID: add_vds_nc_support
Revises:
Create Date: 2024-12-19 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'add_vds_nc_support'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Create VDS-NC and trust management tables."""

    # Create enum types
    op.execute("CREATE TYPE keyrole AS ENUM ('document_signer', 'visa_issuer', 'health_authority', 'other')")
    op.execute("CREATE TYPE keystatus AS ENUM ('active', 'deprecated', 'revoked', 'pending')")

    # VDS-NC keys table
    op.create_table('vds_nc_keys',
        sa.Column('kid', sa.String(255), primary_key=True),
        sa.Column('issuer_country', sa.String(3), nullable=False),
        sa.Column('role', postgresql.ENUM('document_signer', 'visa_issuer', 'health_authority', 'other', name='keyrole'), nullable=False),
        sa.Column('status', postgresql.ENUM('active', 'deprecated', 'revoked', 'pending', name='keystatus'), nullable=False),
        sa.Column('algorithm', sa.String(10), nullable=False, default='ES256'),
        sa.Column('not_before', sa.DateTime(timezone=True), nullable=False),
        sa.Column('not_after', sa.DateTime(timezone=True), nullable=False),
        sa.Column('rotation_generation', sa.Integer, nullable=False, default=1),
        sa.Column('superseded_by', sa.String(255), nullable=True),
        sa.Column('supersedes', sa.String(255), nullable=True),
        sa.Column('public_key_jwk', postgresql.JSONB, nullable=False),
        sa.Column('private_key_encrypted', sa.Text, nullable=True),
        sa.Column('custom_metadata', postgresql.JSONB, nullable=False, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revocation_reason', sa.Text, nullable=True),
        sa.Column('is_trusted', sa.Boolean, nullable=False, default=True),
        sa.Column('distribution_enabled', sa.Boolean, nullable=False, default=True),
    )

    # Create indexes for VDS-NC keys
    op.create_index('idx_vds_nc_keys_country', 'vds_nc_keys', ['issuer_country'])
    op.create_index('idx_vds_nc_keys_role', 'vds_nc_keys', ['role'])
    op.create_index('idx_vds_nc_keys_status', 'vds_nc_keys', ['status'])
    op.create_index('idx_vds_nc_keys_validity', 'vds_nc_keys', ['not_before', 'not_after'])
    op.create_index('idx_vds_nc_keys_country_role', 'vds_nc_keys', ['issuer_country', 'role'])
    op.create_index('idx_vds_nc_keys_active', 'vds_nc_keys', ['status', 'not_before', 'not_after'])
    op.create_index('idx_vds_nc_keys_rotation', 'vds_nc_keys', ['rotation_generation', 'issuer_country', 'role'])

    # Continue with other tables...
    # (Additional table creation code would go here)


def downgrade():
    """Drop VDS-NC and trust management tables."""
    op.drop_table('vds_nc_keys')
    op.execute("DROP TYPE IF EXISTS keyrole")
    op.execute("DROP TYPE IF EXISTS keystatus")
'''
