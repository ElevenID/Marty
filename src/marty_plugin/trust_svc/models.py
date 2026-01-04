"""
Trust Services Data Models

Pydantic models for trust services API requests, responses, and database entities.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TrustLevel(str, Enum):
    """Trust levels for certificates and anchors."""

    STANDARD = "standard"
    HIGH = "high"
    EMERGENCY = "emergency"


class CertificateStatus(str, Enum):
    """Certificate status enumeration."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    REVOKED = "revoked"


class RevocationStatus(str, Enum):
    """Certificate revocation status."""

    GOOD = "good"
    BAD = "bad"
    UNKNOWN = "unknown"


class JobStatus(str, Enum):
    """Job execution status."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceType(str, Enum):
    """PKD source types."""

    ICAO_PKD = "icao_pkd"
    NATIONAL_PKI = "national_pki"
    MANUAL = "manual"


# Database Models
class TrustAnchor(BaseModel):
    """Trust anchor (CSCA) certificate model."""

    id: str
    country_code: str = Field(..., max_length=3)
    certificate_hash: str
    certificate_data: bytes
    subject_dn: str
    issuer_dn: str
    serial_number: str
    valid_from: datetime
    valid_to: datetime
    key_usage: list[str]
    signature_algorithm: str | None
    public_key_algorithm: str | None
    immutable_flag: bool = False
    trust_level: TrustLevel = TrustLevel.STANDARD
    status: CertificateStatus = CertificateStatus.ACTIVE
    created_at: datetime
    updated_at: datetime


class DSCCertificate(BaseModel):
    """Document Signer Certificate model."""

    id: str
    country_code: str = Field(..., max_length=3)
    certificate_hash: str
    certificate_data: bytes
    issuer_trust_anchor_id: str | None
    subject_dn: str
    issuer_dn: str
    serial_number: str
    valid_from: datetime
    valid_to: datetime
    key_usage: list[str]
    signature_algorithm: str | None
    public_key_algorithm: str | None

    # Revocation status
    revocation_status: RevocationStatus = RevocationStatus.UNKNOWN
    revocation_checked_at: datetime | None
    revocation_reason: int | None
    revocation_date: datetime | None
    crl_source: str | None
    ocsp_source: str | None
    ocsp_checked_at: datetime | None

    # Trust chain
    chain_valid: bool | None
    chain_validated_at: datetime | None
    trust_path: list[str] = Field(default_factory=list)

    immutable_flag: bool = False
    status: CertificateStatus = CertificateStatus.ACTIVE
    created_at: datetime
    updated_at: datetime


class IacaCertificate(BaseModel):
    """IACA (Issuing Authority CA) certificate model for mDL verification (ISO 18013-5)."""

    id: str
    jurisdiction: str = Field(..., max_length=10, description="AAMVA jurisdiction code (e.g., US-CA, CA-ON)")
    certificate_hash: str
    certificate_data: bytes
    subject_dn: str
    issuer_dn: str
    serial_number: str
    valid_from: datetime
    valid_to: datetime
    key_usage: list[str] = Field(default_factory=list)
    signature_algorithm: str | None = None
    public_key_algorithm: str | None = None

    # VICAL tracking
    vical_version: str | None = None
    vical_sequence: int | None = None

    # Trust metadata
    trust_level: TrustLevel = TrustLevel.STANDARD
    status: CertificateStatus = CertificateStatus.ACTIVE
    source: str | None = Field(None, description="Source: aamva_dts, manual, bundled")

    immutable_flag: bool = False
    created_at: datetime
    updated_at: datetime


class CRLCache(BaseModel):
    """Certificate Revocation List cache model."""

    id: str
    issuer_dn: str
    issuer_certificate_hash: str | None
    crl_url: str | None
    crl_number: int | None
    this_update: datetime
    next_update: datetime
    crl_data: bytes
    crl_hash: str
    signature_valid: bool = False
    revoked_count: int = 0
    fetched_at: datetime
    status: str = "active"
    created_at: datetime


class RevokedCertificate(BaseModel):
    """Revoked certificate from CRL."""

    id: str
    crl_id: str
    serial_number: str
    revocation_date: datetime
    reason_code: int | None
    certificate_hash: str | None
    dsc_id: str | None
    created_at: datetime


class TrustSnapshot(BaseModel):
    """Immutable trust snapshot model."""

    id: str
    snapshot_time: datetime
    snapshot_hash: str
    signature: str | None
    signature_algorithm: str = "RSA-SHA256"
    trust_anchor_count: int
    dsc_count: int
    revoked_count: int
    crl_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    immutable_flag: bool = True
    expires_at: datetime | None
    created_at: datetime


class JobExecution(BaseModel):
    """Job execution tracking model."""

    id: str
    job_name: str
    job_type: str
    status: JobStatus
    started_at: datetime
    completed_at: datetime | None
    duration_seconds: int | None
    records_processed: int = 0
    errors_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


# API Request/Response Models
class TrustStatusRequest(BaseModel):
    """Request for certificate trust status."""

    certificate_hash: str
    include_chain: bool = False
    validation_time: datetime | None = None


class TrustStatusResponse(BaseModel):
    """Response for certificate trust status."""

    certificate_hash: str
    found: bool
    trust_status: RevocationStatus | None
    trust_anchor: str | None
    chain_valid: bool | None
    revocation_checked_at: datetime | None
    expires_at: datetime | None
    trust_path: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrustAnchorListResponse(BaseModel):
    """Response for trust anchor listing."""

    country_code: str | None
    trust_anchors: list[TrustAnchor]
    total_count: int
    valid_count: int
    expired_count: int


class DSCListResponse(BaseModel):
    """Response for DSC listing."""

    country_code: str | None
    certificates: list[DSCCertificate]
    total_count: int
    status_counts: dict[str, int] = Field(default_factory=dict)


class IacaListResponse(BaseModel):
    """Response for IACA certificate listing."""

    jurisdiction: str | None
    certificates: list[IacaCertificate]
    total_count: int
    active_count: int
    vical_version: str | None = None
    status_counts: dict[str, int] = Field(default_factory=dict)


class SnapshotResponse(BaseModel):
    """Response for trust snapshot."""

    snapshot: TrustSnapshot
    signature_valid: bool
    age_seconds: int


class MasterListUploadRequest(BaseModel):
    """Request for master list upload."""

    country_code: str = Field(..., max_length=3)
    master_list_data: bytes
    source_type: str = "manual"
    source_url: str | None = None


class MasterListUploadResponse(BaseModel):
    """Response for master list upload."""

    success: bool
    message: str
    certificates_processed: int
    trust_anchors_added: int
    dscs_added: int
    errors: list[str] = Field(default_factory=list)


class CRLRefreshRequest(BaseModel):
    """Request for CRL refresh."""

    issuer_dn: str | None = None
    country_code: str | None = None
    force_refresh: bool = False


class CRLRefreshResponse(BaseModel):
    """Response for CRL refresh."""

    success: bool
    message: str
    crls_processed: int
    revoked_certificates_found: int
    errors: list[str] = Field(default_factory=list)


class ServiceStatusResponse(BaseModel):
    """Service health and status response."""

    status: str
    version: str
    uptime_seconds: int
    database_connected: bool
    kms_available: bool
    job_scheduler_running: bool
    last_snapshot_age_seconds: int | None
    certificate_counts: dict[str, int] = Field(default_factory=dict)
    recent_jobs: list[JobExecution] = Field(default_factory=list)


class MetricsResponse(BaseModel):
    """Prometheus metrics response."""

    metrics: dict[str, Any] = Field(default_factory=dict)
