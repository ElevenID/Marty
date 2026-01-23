"""
Certificate models for X.509 PKI infrastructure.

Models complying with RFC 5280 for X.509 certificates used in the
ICAO PKI for ePassports, including CSCA and Document Signer certificates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class KeyAlgorithm(str, Enum):
    """Supported key algorithms for certificates."""

    RSA = "RSA"
    EC = "EC"
    DSA = "DSA"


class SignatureAlgorithm(str, Enum):
    """Supported signature algorithms for certificates."""

    SHA1_WITH_RSA = "SHA1withRSA"
    SHA256_WITH_RSA = "SHA256withRSA"
    SHA384_WITH_RSA = "SHA384withRSA"
    SHA512_WITH_RSA = "SHA512withRSA"
    SHA256_WITH_ECDSA = "SHA256withECDSA"
    SHA384_WITH_ECDSA = "SHA384withECDSA"
    SHA512_WITH_ECDSA = "SHA512withECDSA"


class KeyUsage(str, Enum):
    """Key usage extensions for certificates."""

    DIGITAL_SIGNATURE = "digitalSignature"
    NON_REPUDIATION = "nonRepudiation"
    KEY_ENCIPHERMENT = "keyEncipherment"
    DATA_ENCIPHERMENT = "dataEncipherment"
    KEY_AGREEMENT = "keyAgreement"
    KEY_CERT_SIGN = "keyCertSign"
    CRL_SIGN = "cRLSign"
    ENCIPHER_ONLY = "encipherOnly"
    DECIPHER_ONLY = "decipherOnly"


class CertificateType(str, Enum):
    """Types of certificates used in the ICAO PKI."""

    CSCA = "CSCA"  # Country Signing Certificate Authority
    DOCUMENT_SIGNER = "DS"  # Document Signer Certificate
    MASTER_LIST_SIGNER = "MLS"  # Master List Signer
    CRL_SIGNER = "CRL"  # Certificate Revocation List Signer
    TERMINAL = "TERMINAL"  # Inspection System Terminal Certificate


@dataclass
class X509Name:
    """X.509 Distinguished Name components."""

    country: str
    organization: str
    organizational_unit: str | None = None
    common_name: str | None = None
    state_or_province: str | None = None
    locality: str | None = None
    email: str | None = None

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary."""
        result = {"C": self.country, "O": self.organization}

        if self.organizational_unit:
            result["OU"] = self.organizational_unit

        if self.common_name:
            result["CN"] = self.common_name

        if self.state_or_province:
            result["ST"] = self.state_or_province

        if self.locality:
            result["L"] = self.locality

        if self.email:
            result["E"] = self.email

        return result

    def to_string(self) -> str:
        """Convert to string format used in certificates."""
        parts = []

        if self.country:
            parts.append(f"C={self.country}")

        if self.organization:
            parts.append(f"O={self.organization}")

        if self.organizational_unit:
            parts.append(f"OU={self.organizational_unit}")

        if self.common_name:
            parts.append(f"CN={self.common_name}")

        if self.state_or_province:
            parts.append(f"ST={self.state_or_province}")

        if self.locality:
            parts.append(f"L={self.locality}")

        if self.email:
            parts.append(f"E={self.email}")

        return ", ".join(parts)

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> X509Name:
        """Create X509Name from dictionary."""
        return cls(
            country=data.get("C", ""),
            organization=data.get("O", ""),
            organizational_unit=data.get("OU"),
            common_name=data.get("CN"),
            state_or_province=data.get("ST"),
            locality=data.get("L"),
            email=data.get("E"),
        )

    @classmethod
    def from_string(cls, name_string: str) -> X509Name:
        """Parse X509Name from string."""
        components = {}
        for part in name_string.split(","):
            if "=" in part:
                key, value = part.strip().split("=", 1)
                components[key.strip()] = value.strip()

        return cls.from_dict(components)


@dataclass
class X509Extension:
    """X.509 certificate extension."""

    oid: str
    critical: bool = False
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {"oid": self.oid, "critical": self.critical}

        if self.value is not None:
            result["value"] = self.value

        return result


@dataclass
class CertificateRequest:
    """Certificate Signing Request (CSR) data."""

    subject: X509Name
    key_algorithm: KeyAlgorithm
    key_size: int
    validity_days: int
    key_usage: list[KeyUsage] = field(default_factory=list)
    extensions: list[X509Extension] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "subject": self.subject.to_dict(),
            "keyAlgorithm": self.key_algorithm.value,
            "keySize": self.key_size,
            "validityDays": self.validity_days,
            "keyUsage": [usage.value for usage in self.key_usage],
            "extensions": [ext.to_dict() for ext in self.extensions],
        }


@dataclass
class Certificate:
    """X.509 Certificate model."""

    serial_number: str
    subject: X509Name
    issuer: X509Name
    not_before: datetime
    not_after: datetime
    public_key: str  # Base64 encoded public key
    signature_algorithm: SignatureAlgorithm
    signature: str  # Base64 encoded signature
    certificate_type: CertificateType
    key_usage: list[KeyUsage] = field(default_factory=list)
    extensions: list[X509Extension] = field(default_factory=list)
    raw_data: str | None = None  # Base64 encoded certificate data (DER/PEM)
    id: UUID = field(default_factory=uuid4)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "serialNumber": self.serial_number,
            "subject": self.subject.to_dict(),
            "issuer": self.issuer.to_dict(),
            "notBefore": self.not_before.isoformat(),
            "notAfter": self.not_after.isoformat(),
            "publicKey": self.public_key,
            "signatureAlgorithm": self.signature_algorithm.value,
            "signature": self.signature,
            "certificateType": self.certificate_type.value,
            "keyUsage": [usage.value for usage in self.key_usage],
            "extensions": [ext.to_dict() for ext in self.extensions],
            "rawData": self.raw_data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Certificate:
        """Create Certificate from dictionary."""
        cert = cls(
            id=UUID(data["id"]) if "id" in data else uuid4(),
            serial_number=data["serialNumber"],
            subject=X509Name.from_dict(data["subject"]),
            issuer=X509Name.from_dict(data["issuer"]),
            not_before=datetime.fromisoformat(data["notBefore"]),
            not_after=datetime.fromisoformat(data["notAfter"]),
            public_key=data["publicKey"],
            signature_algorithm=SignatureAlgorithm(data["signatureAlgorithm"]),
            signature=data["signature"],
            certificate_type=CertificateType(data["certificateType"]),
            raw_data=data.get("rawData"),
        )

        # Add key usage if present
        if "keyUsage" in data:
            cert.key_usage = [KeyUsage(usage) for usage in data["keyUsage"]]

        # Add extensions if present
        if "extensions" in data:
            cert.extensions = [
                X509Extension(
                    oid=ext["oid"], critical=ext.get("critical", False), value=ext.get("value")
                )
                for ext in data["extensions"]
            ]

        return cert

    def is_valid(self, current_time: datetime | None = None) -> bool:
        """Check if certificate is currently valid."""
        if current_time is None:
            current_time = datetime.now()

        return self.not_before <= current_time <= self.not_after

    def is_self_signed(self) -> bool:
        """Check if this is a self-signed certificate."""
        subject_dict = {k.lower(): v for k, v in self.subject.to_dict().items()}
        issuer_dict = {k.lower(): v for k, v in self.issuer.to_dict().items()}

        # Check minimally required fields
        if subject_dict.get("c") != issuer_dict.get("c"):
            return False

        if subject_dict.get("o") != issuer_dict.get("o"):
            return False

        # If CN is present in both, it should match
        if "cn" in subject_dict and "cn" in issuer_dict:
            return subject_dict["cn"] == issuer_dict["cn"]

        return True


@dataclass
class CertificateRevocationList:
    """Certificate Revocation List (CRL) model."""

    issuer: X509Name
    this_update: datetime
    next_update: datetime
    revoked_certificates: list[dict[str, Any]] = field(default_factory=list)
    signature_algorithm: SignatureAlgorithm | None = None
    signature: str | None = None  # Base64 encoded signature
    raw_data: str | None = None  # Base64 encoded CRL data
    id: UUID = field(default_factory=uuid4)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "id": str(self.id),
            "issuer": self.issuer.to_dict(),
            "thisUpdate": self.this_update.isoformat(),
            "nextUpdate": self.next_update.isoformat(),
            "revokedCertificates": self.revoked_certificates,
        }

        if self.signature_algorithm:
            result["signatureAlgorithm"] = self.signature_algorithm.value

        if self.signature:
            result["signature"] = self.signature

        if self.raw_data:
            result["rawData"] = self.raw_data

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CertificateRevocationList:
        """Create CertificateRevocationList from dictionary."""
        crl = cls(
            id=UUID(data["id"]) if "id" in data else uuid4(),
            issuer=X509Name.from_dict(data["issuer"]),
            this_update=datetime.fromisoformat(data["thisUpdate"]),
            next_update=datetime.fromisoformat(data["nextUpdate"]),
            revoked_certificates=data.get("revokedCertificates", []),
            raw_data=data.get("rawData"),
        )

        if "signatureAlgorithm" in data:
            crl.signature_algorithm = SignatureAlgorithm(data["signatureAlgorithm"])

        if "signature" in data:
            crl.signature = data["signature"]

        return crl

    def is_certificate_revoked(self, serial_number: str) -> bool:
        """Check if a certificate with the given serial number is revoked."""
        return any(cert.get("serialNumber") == serial_number for cert in self.revoked_certificates)

    def is_valid(self, current_time: datetime | None = None) -> bool:
        """Check if CRL is currently valid."""
        if current_time is None:
            current_time = datetime.now()

        return self.this_update <= current_time <= self.next_update


@dataclass
class CSCAMasterListEntry:
    """Entry in a CSCA Master List."""

    country: str
    certificate: Certificate

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {"country": self.country, "certificate": self.certificate.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CSCAMasterListEntry:
        """Create CSCAMasterListEntry from dictionary."""
        return cls(country=data["country"], certificate=Certificate.from_dict(data["certificate"]))


@dataclass
class CSCAMasterList:
    """CSCA Master List containing trusted CSCA certificates."""

    version: str
    issuer: X509Name
    issued_date: datetime
    next_update: datetime
    entries: list[CSCAMasterListEntry] = field(default_factory=list)
    signature: str | None = None
    id: UUID = field(default_factory=uuid4)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "id": str(self.id),
            "version": self.version,
            "issuer": self.issuer.to_dict(),
            "issuedDate": self.issued_date.isoformat(),
            "nextUpdate": self.next_update.isoformat(),
            "entries": [entry.to_dict() for entry in self.entries],
        }

        if self.signature:
            result["signature"] = self.signature

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CSCAMasterList:
        """Create CSCAMasterList from dictionary."""
        master_list = cls(
            id=UUID(data["id"]) if "id" in data else uuid4(),
            version=data["version"],
            issuer=X509Name.from_dict(data["issuer"]),
            issued_date=datetime.fromisoformat(data["issuedDate"]),
            next_update=datetime.fromisoformat(data["nextUpdate"]),
            signature=data.get("signature"),
        )

        if "entries" in data:
            master_list.entries = [
                CSCAMasterListEntry.from_dict(entry) for entry in data["entries"]
            ]

        return master_list

    def get_certificates_for_country(self, country_code: str) -> list[Certificate]:
        """Get all CSCA certificates for a specific country."""
        return [
            entry.certificate
            for entry in self.entries
            if entry.country.upper() == country_code.upper()
        ]

    def is_valid(self, current_time: datetime | None = None) -> bool:
        """Check if master list is currently valid."""
        if current_time is None:
            current_time = datetime.now()

        return self.issued_date <= current_time <= self.next_update
