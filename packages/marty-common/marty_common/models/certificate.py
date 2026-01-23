"""
Certificate data models for Marty services.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class CertificateStatus(str, Enum):
    """Certificate status enum."""

    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class KeyAlgorithm(str, Enum):
    """Public key algorithm enum."""

    RSA = "RSA"
    EC = "EC"


@dataclass
class Certificate:
    """X.509 certificate model."""

    id: UUID
    subject: str
    issuer: str
    valid_from: datetime
    valid_to: datetime
    certificate_data: bytes
    status: CertificateStatus
    public_key: str | None = None

    def to_dict(self) -> dict:
        """Convert certificate to dictionary."""
        result = {
            "id": str(self.id),
            "subject": self.subject,
            "issuer": self.issuer,
            "validFrom": self.valid_from.isoformat(),
            "validTo": self.valid_to.isoformat(),
            "certificateData": self.certificate_data.hex(),
            "status": self.status.value,
        }

        if self.public_key:
            result["publicKey"] = self.public_key

        return result

    @classmethod
    def from_dict(cls, data: dict) -> Certificate:
        """Create Certificate from dictionary."""
        return cls(
            id=UUID(data["id"]),
            subject=data["subject"],
            issuer=data["issuer"],
            valid_from=datetime.fromisoformat(data["validFrom"]),
            valid_to=datetime.fromisoformat(data["validTo"]),
            certificate_data=bytes.fromhex(data["certificateData"]),
            status=CertificateStatus(data["status"]),
            public_key=data.get("publicKey"),
        )

    def is_valid_at(self, timestamp: datetime | None = None) -> bool:
        """
        Check if certificate is valid at given timestamp.
        If no timestamp is provided, checks for current time.
        """
        if timestamp is None:
            timestamp = datetime.now()

        return (
            self.valid_from <= timestamp <= self.valid_to
            and self.status == CertificateStatus.ACTIVE
        )


@dataclass
class CertificateRequest:
    """Request for certificate generation."""

    subject: str
    validity_days: int
    key_algorithm: KeyAlgorithm
    key_size: int = 2048

    def to_dict(self) -> dict:
        """Convert certificate request to dictionary."""
        return {
            "subject": self.subject,
            "validityDays": self.validity_days,
            "keyAlgorithm": self.key_algorithm.value,
            "keySize": self.key_size,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CertificateRequest:
        """Create CertificateRequest from dictionary."""
        return cls(
            subject=data["subject"],
            validity_days=data["validityDays"],
            key_algorithm=KeyAlgorithm(data["keyAlgorithm"]),
            key_size=data.get("keySize", 2048),
        )
