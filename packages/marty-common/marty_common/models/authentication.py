"""
Authentication protocol models for e-passport access control.

Models for various authentication protocols used in e-passport access:
- BAC (Basic Access Control)
- PACE (Password Authenticated Connection Establishment)
- EAC (Extended Access Control) including Terminal Authentication and Chip Authentication
- Active Authentication

These protocols are specified in ICAO Doc 9303 and BSI TR-03110.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class AuthenticationProtocol(str, Enum):
    """Authentication protocols for ePassports."""

    BAC = "BAC"  # Basic Access Control
    PACE = "PACE"  # Password Authenticated Connection Establishment
    EAC_TA = "EAC_TA"  # Extended Access Control - Terminal Authentication
    EAC_CA = "EAC_CA"  # Extended Access Control - Chip Authentication
    ACTIVE_AUTH = "ACTIVE_AUTH"  # Active Authentication


class PACEMappingType(str, Enum):
    """PACE mapping types as defined in ICAO Doc 9303 and BSI TR-03110."""

    GM = "GM"  # Generic Mapping
    IM = "IM"  # Integrated Mapping
    CAM = "CAM"  # Chip Authentication Mapping
    DH = "DH"  # Diffie-Hellman
    ECDH = "ECDH"  # Elliptic Curve Diffie-Hellman


class ActiveAuthenticationAlgorithm(str, Enum):
    """Active Authentication signature algorithms."""

    RSA_SHA1 = "RSA_SHA1"
    RSA_SHA256 = "RSA_SHA256"
    ECDSA_SHA256 = "ECDSA_SHA256"


@dataclass
class AccessKey:
    """Base class for access keys used in passport authentication."""

    key_id: str
    key_type: str
    key_data: str  # Base64 encoded key material

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {"keyId": self.key_id, "keyType": self.key_type, "keyData": self.key_data}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AccessKey:
        """Create AccessKey from dictionary."""
        return cls(key_id=data["keyId"], key_type=data["keyType"], key_data=data["keyData"])


@dataclass
class BACKey(AccessKey):
    """Basic Access Control key derived from MRZ."""

    document_number: str
    date_of_birth: str  # Format: YYMMDD
    date_of_expiry: str  # Format: YYMMDD

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = super().to_dict()
        result.update(
            {
                "documentNumber": self.document_number,
                "dateOfBirth": self.date_of_birth,
                "dateOfExpiry": self.date_of_expiry,
            }
        )
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BACKey:
        """Create BACKey from dictionary."""
        return cls(
            key_id=data["keyId"],
            key_type=data["keyType"],
            key_data=data["keyData"],
            document_number=data["documentNumber"],
            date_of_birth=data["dateOfBirth"],
            date_of_expiry=data["dateOfExpiry"],
        )

    @classmethod
    def from_mrz_info(cls, document_number: str, date_of_birth: str, date_of_expiry: str) -> BACKey:
        """Create BAC key from MRZ information."""
        # In a real implementation, this would derive the actual BAC key
        # using the algorithm specified in ICAO Doc 9303
        key_id = f"BAC-{document_number}"
        key_type = "BAC"
        # Mock key derivation - a real implementation would use the key derivation algorithm
        mock_key_data = base64.b64encode(
            f"{document_number}{date_of_birth}{date_of_expiry}".encode()
        ).decode()

        return cls(
            key_id=key_id,
            key_type=key_type,
            key_data=mock_key_data,
            document_number=document_number,
            date_of_birth=date_of_birth,
            date_of_expiry=date_of_expiry,
        )


@dataclass
class PACEInfo:
    """PACE protocol parameters."""

    protocol_id: str  # OID for the protocol
    mapping_type: PACEMappingType
    key_agreement_algorithm: str
    key_length: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "protocolId": self.protocol_id,
            "mappingType": self.mapping_type.value,
            "keyAgreementAlgorithm": self.key_agreement_algorithm,
            "keyLength": self.key_length,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PACEInfo:
        """Create PACEInfo from dictionary."""
        return cls(
            protocol_id=data["protocolId"],
            mapping_type=PACEMappingType(data["mappingType"]),
            key_agreement_algorithm=data["keyAgreementAlgorithm"],
            key_length=data["keyLength"],
        )


@dataclass
class ChipAuthenticationInfo:
    """Chip Authentication parameters."""

    protocol_id: str  # OID for the protocol
    key_id: int | None = None
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {"protocolId": self.protocol_id, "version": self.version}

        if self.key_id is not None:
            result["keyId"] = self.key_id

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChipAuthenticationInfo:
        """Create ChipAuthenticationInfo from dictionary."""
        return cls(
            protocol_id=data["protocolId"], key_id=data.get("keyId"), version=data.get("version", 1)
        )


@dataclass
class TerminalAuthenticationInfo:
    """Terminal Authentication parameters."""

    protocol_id: str  # OID for the protocol
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {"protocolId": self.protocol_id, "version": self.version}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TerminalAuthenticationInfo:
        """Create TerminalAuthenticationInfo from dictionary."""
        return cls(protocol_id=data["protocolId"], version=data.get("version", 1))


@dataclass
class ActiveAuthenticationInfo:
    """Active Authentication parameters."""

    protocol_id: str  # OID for the protocol
    signature_algorithm: ActiveAuthenticationAlgorithm

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "protocolId": self.protocol_id,
            "signatureAlgorithm": self.signature_algorithm.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActiveAuthenticationInfo:
        """Create ActiveAuthenticationInfo from dictionary."""
        return cls(
            protocol_id=data["protocolId"],
            signature_algorithm=ActiveAuthenticationAlgorithm(data["signatureAlgorithm"]),
        )


@dataclass
class SecurityInfo:
    """Security information for ePassport authentication."""

    bac_info: bool | None = None
    pace_info: PACEInfo | None = None
    chip_auth_info: ChipAuthenticationInfo | None = None
    terminal_auth_info: TerminalAuthenticationInfo | None = None
    active_auth_info: ActiveAuthenticationInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {}

        if self.bac_info is not None:
            result["bacInfo"] = self.bac_info

        if self.pace_info:
            result["paceInfo"] = self.pace_info.to_dict()

        if self.chip_auth_info:
            result["chipAuthInfo"] = self.chip_auth_info.to_dict()

        if self.terminal_auth_info:
            result["terminalAuthInfo"] = self.terminal_auth_info.to_dict()

        if self.active_auth_info:
            result["activeAuthInfo"] = self.active_auth_info.to_dict()

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SecurityInfo:
        """Create SecurityInfo from dictionary."""
        security_info = cls(bac_info=data.get("bacInfo"))

        if "paceInfo" in data:
            security_info.pace_info = PACEInfo.from_dict(data["paceInfo"])

        if "chipAuthInfo" in data:
            security_info.chip_auth_info = ChipAuthenticationInfo.from_dict(data["chipAuthInfo"])

        if "terminalAuthInfo" in data:
            security_info.terminal_auth_info = TerminalAuthenticationInfo.from_dict(
                data["terminalAuthInfo"]
            )

        if "activeAuthInfo" in data:
            security_info.active_auth_info = ActiveAuthenticationInfo.from_dict(
                data["activeAuthInfo"]
            )

        return security_info


@dataclass
class AuthenticationResult:
    """Result of an authentication operation."""

    protocol: AuthenticationProtocol
    success: bool
    timestamp: datetime = field(default_factory=datetime.now)
    session_keys: dict[str, str] | None = None  # Base64 encoded session keys
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "protocol": self.protocol.value,
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
        }

        if self.session_keys:
            result["sessionKeys"] = self.session_keys

        if self.error_message:
            result["errorMessage"] = self.error_message

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthenticationResult:
        """Create AuthenticationResult from dictionary."""
        return cls(
            protocol=AuthenticationProtocol(data["protocol"]),
            success=data["success"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            session_keys=data.get("sessionKeys"),
            error_message=data.get("errorMessage"),
        )


@dataclass
class AuthenticationChallenge:
    """Challenge for authentication protocols."""

    protocol: AuthenticationProtocol
    challenge_id: str = field(default_factory=lambda: str(uuid4()))
    challenge_data: str | None = None  # Base64 encoded challenge
    timestamp: datetime = field(default_factory=datetime.now)
    expiry: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "protocol": self.protocol.value,
            "challengeId": self.challenge_id,
            "timestamp": self.timestamp.isoformat(),
        }

        if self.challenge_data:
            result["challengeData"] = self.challenge_data

        if self.expiry:
            result["expiry"] = self.expiry.isoformat()

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthenticationChallenge:
        """Create AuthenticationChallenge from dictionary."""
        challenge = cls(
            protocol=AuthenticationProtocol(data["protocol"]),
            challenge_id=data["challengeId"],
            challenge_data=data.get("challengeData"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )

        if "expiry" in data:
            challenge.expiry = datetime.fromisoformat(data["expiry"])

        return challenge

    def is_expired(self, current_time: datetime | None = None) -> bool:
        """Check if challenge is expired."""
        if not self.expiry:
            return False

        if current_time is None:
            current_time = datetime.now()

        return current_time > self.expiry


@dataclass
class AuthenticationResponse:
    """Response to an authentication challenge."""

    challenge_id: str
    response_data: str  # Base64 encoded response
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "challengeId": self.challenge_id,
            "responseData": self.response_data,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthenticationResponse:
        """Create AuthenticationResponse from dictionary."""
        return cls(
            challenge_id=data["challengeId"],
            response_data=data["responseData"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )
