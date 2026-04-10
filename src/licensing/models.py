"""
License Models

SQLAlchemy models for license management, issuance tracking, and revocation.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class JSONBType(TypeDecorator):
    """Platform-independent JSONB type.

    Uses JSONB for PostgreSQL and JSON for SQLite/other databases.
    """
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class Base(DeclarativeBase):
    """Base class for licensing models."""
    pass


class LicenseStatus(str, Enum):
    """License lifecycle status."""
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"  # replaced by a newer license for the same org


class RegistryCredentialStatus(str, Enum):
    """Registry credential lifecycle status."""
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class License(Base):
    """
    Issued license record.

    Each license is a signed JWT granting an organization access to
    specific Marty products and features for a bounded time period.
    """
    __tablename__ = "licenses"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    license_jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=LicenseStatus.ACTIVE.value)

    # Plan and entitlements snapshot (denormalized from subscription at issuance time)
    plan_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    entitled_products: Mapped[Optional[dict]] = mapped_column(JSONBType(), nullable=True)
    features: Mapped[Optional[dict]] = mapped_column(JSONBType(), nullable=True)
    max_instances: Mapped[Optional[dict]] = mapped_column(JSONBType(), nullable=True)
    registry_access: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    api_calls_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # The signed JWT itself
    license_jwt: Mapped[str] = mapped_column(Text, nullable=False)

    # Timestamps
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<License {self.license_jti} org={self.org_id} status={self.status}>"


class LicenseRevocation(Base):
    """
    Revocation record for online validation (phone-home) checks.

    Clients query this list to verify a license hasn't been revoked
    between its issuance and expiry.
    """
    __tablename__ = "license_revocations"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    license_jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    org_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class RegistryCredential(Base):
    """
    Per-org container registry pull credential.

    Issued when a license with registry_access=True is created.
    The token is stored as a SHA-256 hash; the plaintext is returned
    only once at issuance time.
    """
    __tablename__ = "registry_credentials"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    org_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    license_jti: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    registry_url: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    allowed_images: Mapped[Optional[dict]] = mapped_column(JSONBType(), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=RegistryCredentialStatus.ACTIVE.value)

    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<RegistryCredential {self.id} org={self.org_id} status={self.status}>"
