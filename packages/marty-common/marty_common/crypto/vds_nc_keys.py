"""Retained VDS-NC public metadata and stable database enum values.

The former native key-management and distribution implementation is retired.
"""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any





class KeyStatus(Enum):
    """VDS-NC key lifecycle status."""

    PENDING = "pending"  # Generated but not activated
    ACTIVE = "active"  # Currently active for signing
    ROTATING = "rotating"  # In rotation overlap period
    DEPRECATED = "deprecated"  # No longer used for signing, kept for verification
    REVOKED = "revoked"  # Revoked/compromised
    EXPIRED = "expired"  # Past validity period


class KeyRole(Enum):
    """VDS-NC signer role/purpose."""

    CMC = "CMC"  # Crew Member Certificate
    VISA = "VISA"  # Visa sticker
    EMERGENCY_TRAVEL = "ETD"  # Emergency Travel Document
    PROOF_OF_TESTING = "POT"  # Proof of Testing (health certificates)
    VACCINATION = "VCN"  # Vaccination certificates
    GENERAL = "GENERAL"  # General purpose


@dataclass
class VDSNCKeyMetadata:
    """Metadata for VDS-NC signer keys."""

    kid: str  # Key identifier
    issuer_country: str  # ISO 3166-1 alpha-3 country code
    role: KeyRole
    algorithm: str = "ES256"  # ECDSA with P-256 and SHA-256
    key_size: int = 256
    status: KeyStatus = KeyStatus.PENDING
    rotation_generation: int = 1
    not_before: datetime = field(default_factory=lambda: datetime.now(UTC))
    not_after: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(days=730))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    activated_at: datetime | None = None
    deprecated_at: datetime | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None
    hsm_key_id: str | None = None  # HSM reference if using HSM
    parent_kid: str | None = None  # Previous key in rotation chain
    tags: dict[str, str] = field(default_factory=dict)

    def is_valid_now(self) -> bool:
        """Check if key is currently valid."""
        now = datetime.now(UTC)
        return self.status in [KeyStatus.ACTIVE, KeyStatus.ROTATING] and self.not_before <= now <= self.not_after

    def needs_rotation(self, warning_days: int = 60) -> bool:
        """Check if key approaching expiration."""
        warning_threshold = datetime.now(UTC) + timedelta(days=warning_days)
        return self.not_after <= warning_threshold

    def to_jwk(self, public_key: bytes) -> dict[str, Any]:
        """Convert to JWK format for distribution."""
        raw = bytes(public_key)
        if len(raw) != 65 or raw[0] != 4:
            raise ValueError("Native P-256 public key must be uncompressed SEC1 data")

        x_b64 = base64.urlsafe_b64encode(raw[1:33]).decode("ascii").rstrip("=")
        y_b64 = base64.urlsafe_b64encode(raw[33:65]).decode("ascii").rstrip("=")

        return {
            "kid": self.kid,
            "kty": "EC",
            "crv": "P-256",
            "x": x_b64,
            "y": y_b64,
            "use": "sig",
            "alg": "ES256",
            "issuer": self.issuer_country,
            "role": self.role.value,
            "not_before": self.not_before.isoformat(),
            "not_after": self.not_after.isoformat(),
            "status": self.status.value,
            "rotation_generation": self.rotation_generation,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        # Convert enums to strings
        data["status"] = self.status.value
        data["role"] = self.role.value
        # Convert datetimes to ISO format
        for key in [
            "not_before",
            "not_after",
            "created_at",
            "activated_at",
            "deprecated_at",
            "revoked_at",
        ]:
            if data[key]:
                data[key] = data[key].isoformat() if isinstance(data[key], datetime) else data[key]
        return data
