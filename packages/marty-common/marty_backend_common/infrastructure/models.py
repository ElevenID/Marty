"""Shared SQLAlchemy models used across services."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TrustEntity(Base):
    __tablename__ = "trust_entities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entity_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    trusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    attributes: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class CertificateRecord(Base):
    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    certificate_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    certificate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    issuer: Mapped[str] = mapped_column(String(128), nullable=True)
    subject: Mapped[str] = mapped_column(String(128), nullable=True)
    pem: Mapped[str] = mapped_column(Text, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class DigitalTravelCredentialRecord(Base):
    __tablename__ = "digital_travel_credentials"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dtc_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    passport_number: Mapped[str] = mapped_column(String(32), nullable=False)
    dtc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    access_control: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_location: Mapped[str] = mapped_column(String(256), nullable=False)
    signature: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)


class MobileDrivingLicenseRecord(Base):
    __tablename__ = "mobile_driving_licenses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mdl_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    license_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_SIGNATURE")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_location: Mapped[str] = mapped_column(String(256), nullable=False)
    disclosure_policies: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    signature: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)


class PassportRecord(Base):
    __tablename__ = "passports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    passport_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ISSUED")
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    payload_location: Mapped[str] = mapped_column(String(256), nullable=False)
    signature: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class EventOutboxRecord(Base):
    __tablename__ = "event_outbox"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    key: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    headers: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class EventDeadLetterRecord(Base):
    """Dead-letter queue for events that failed after max retries."""

    __tablename__ = "event_dead_letter"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    original_topic: Mapped[str] = mapped_column(String(255), nullable=False)
    key: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    headers: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    last_error: Mapped[str] = mapped_column(String(1024), nullable=False)
    dead_lettered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    original_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CredentialEventLog(Base):
    __tablename__ = "credential_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    partition: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offset: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class CredentialLedgerEntry(Base):
    __tablename__ = "credential_ledger"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    credential_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    credential_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_event_topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_event_offset: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class SdJwtCredentialRecord(Base):
    __tablename__ = "sd_jwt_credentials"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    credential_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    credential_type: Mapped[str] = mapped_column(String(128), nullable=False)
    issuer: Mapped[str] = mapped_column(String(256), nullable=False)
    audience: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ISSUED", index=True)
    sd_jwt_location: Mapped[str] = mapped_column(String(512), nullable=False)
    disclosures_location: Mapped[str] = mapped_column(String(512), nullable=False)
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    wallet_attestation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Oidc4VciSessionRecord(Base):
    __tablename__ = "oidc4vci_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    offer_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    credential_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="OFFER_CREATED", index=True
    )
    offer_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    base_claims: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    selective_disclosures: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    pre_authorized_code_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    pre_authorized_code_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    access_token_hash: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    nonce: Mapped[str | None] = mapped_column(String(256), nullable=True)
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    wallet_attestation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
