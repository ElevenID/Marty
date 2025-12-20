"""
Data models for the PKD service
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, validator


class CertificateStatus(str, Enum):
    """Certificate status enum"""

    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class Certificate(BaseModel):
    """Certificate model"""

    id: UUID = Field(default_factory=uuid4)
    subject: str
    issuer: str
    valid_from: datetime
    valid_to: datetime
    serial_number: str
    certificate_data: bytes
    status: CertificateStatus = CertificateStatus.ACTIVE
    country_code: str

    @validator("certificate_data")
    @classmethod
    def validate_cert_data(cls, v: bytes) -> bytes:
        """Validate certificate data is properly formatted"""
        # In a real implementation, validate this is proper ASN.1 X.509 data
        if not v:
            msg = "Certificate data cannot be empty"
            raise ValueError(msg)
        return v


class SyncStatus(str, Enum):
    """Synchronization status enum"""

    NOT_STARTED = "NOT_STARTED"
    INITIATED = "INITIATED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ComponentSyncStatus(str, Enum):
    """Component synchronization status enum"""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class UploadStatus(str, Enum):
    """Upload status enum"""

    PROCESSED = "PROCESSED"
    PENDING = "PENDING"
    ERROR = "ERROR"


class DeviationType(str, Enum):
    """Deviation type enum"""

    CSCA_MISSING = "CSCA_MISSING"
    DSC_MISSING = "DSC_MISSING"
    CRL_MISSING = "CRL_MISSING"
    CRL_EXPIRED = "CRL_EXPIRED"
    CERTIFICATE_INVALID = "CERTIFICATE_INVALID"


class DeviationStatus(str, Enum):
    """Deviation status enum"""

    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"
    INVESTIGATING = "INVESTIGATING"


class DeviationEntry(BaseModel):
    """Deviation entry model"""

    id: UUID = Field(default_factory=uuid4)
    country_code: str
    description: str
    status: DeviationStatus = DeviationStatus.ACTIVE
    created: datetime = Field(default_factory=lambda: datetime.now())
    updated: datetime = Field(default_factory=lambda: datetime.now())
    details: dict[str, Any] = Field(default_factory=dict)


# Request Models
class PkdSyncRequest(BaseModel):
    """Request model for PKD synchronization"""

    sync_source: str
    components: list[str]
    force_sync: bool = False


class DeviationListRequest(BaseModel):
    """Request model for deviation list upload"""

    deviations: list[dict[str, Any]]


class VerificationRequest(BaseModel):
    """Request model for certificate verification."""

    certificate_data: bytes
    check_revocation: bool = True


# Response Models
class MasterListResponse(BaseModel):
    """Response model for CSCA master list"""

    id: UUID = Field(default_factory=uuid4)
    version: int
    created: datetime = Field(default_factory=datetime.now)
    countries: list[str]
    certificates: list[Certificate]


class DscListResponse(BaseModel):
    """Response model for DSC list"""

    id: UUID = Field(default_factory=uuid4)
    version: int
    created: datetime = Field(default_factory=datetime.now)
    countries: list[str]
    certificates: list[Certificate]


# Alias for backwards compatibility
DSCListResponse = DscListResponse


class RevokedCertificate(BaseModel):
    """Model for a revoked certificate"""

    serial_number: str
    revocation_date: datetime
    reason_code: int | None = None


class CrlResponse(BaseModel):
    """Response model for CRL"""

    id: UUID = Field(default_factory=uuid4)
    version: int
    created: datetime = Field(default_factory=datetime.now)
    issuer: str
    this_update: datetime
    next_update: datetime
    revoked_certificates: list[RevokedCertificate]


class Deviation(BaseModel):
    """Model for a PKD deviation"""

    country: str
    type: DeviationType
    certificate_id: str | None = None
    description: str | None = None


class DeviationListResponse(BaseModel):
    """Response model for deviation list"""

    id: UUID = Field(default_factory=uuid4)
    version: int
    created: datetime = Field(default_factory=datetime.now)
    deviations: list[Deviation]


class MasterListUploadResponse(BaseModel):
    """Response model for master list upload"""

    id: UUID = Field(default_factory=uuid4)
    version: int
    created: datetime = Field(default_factory=datetime.now)
    status: UploadStatus
    certificate_count: int


class DscListUploadResponse(BaseModel):
    """Response model for DSC list upload"""

    id: UUID = Field(default_factory=uuid4)
    version: int
    created: datetime = Field(default_factory=datetime.now)
    status: UploadStatus
    certificate_count: int


# Alias for backwards compatibility
DSCListUploadResponse = DscListUploadResponse


class CrlUploadResponse(BaseModel):
    """Response model for CRL upload"""

    id: UUID = Field(default_factory=uuid4)
    version: int
    created: datetime = Field(default_factory=datetime.now)
    status: UploadStatus
    revoked_count: int


class DeviationListUploadResponse(BaseModel):
    """Response model for deviation list upload"""

    id: UUID = Field(default_factory=uuid4)
    version: int
    created: datetime = Field(default_factory=datetime.now)
    status: UploadStatus
    deviation_count: int


class PkdSyncResponse(BaseModel):
    """Response model for PKD synchronization"""

    id: UUID = Field(default_factory=uuid4)
    status: SyncStatus
    start_time: datetime = Field(default_factory=datetime.now)


class PkdSyncStatusResponse(BaseModel):
    """Response model for PKD synchronization status"""

    id: UUID
    status: SyncStatus
    start_time: datetime | None = None
    end_time: datetime | None = None
    components: dict[str, ComponentSyncStatus] = {}
    error_message: str | None = None


class VerificationResult(BaseModel):
    """Result of certificate verification against the trust store."""

    is_valid: bool
    status: str  # VALID, EXPIRED, REVOKED, UNTRUSTED, etc.
    details: str
