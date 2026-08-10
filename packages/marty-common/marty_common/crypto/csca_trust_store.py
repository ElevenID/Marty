"""Native ICAO CSCA trust-registry compatibility adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from marty_common.crypto.certificate_validator import CertificateChainValidator
from marty_common.crypto_bridge import Certificate
from marty_common.native_backends import NativeOperationError, load_native_backend


class CSCAStatus(Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUSPENDED = "suspended"
    PENDING = "pending"
    UNKNOWN = "unknown"


class TrustLevel(Enum):
    FULL_TRUST = "full_trust"
    CONDITIONAL_TRUST = "conditional_trust"
    UNTRUSTED = "untrusted"
    BLACKLISTED = "blacklisted"


@dataclass
class CountryInfo:
    country_code: str
    country_name: str
    region: str
    passport_type: str
    issuing_authority: str
    security_features: list[str]
    supported_data_groups: list[int]
    eac_supported: bool
    bac_supported: bool

    @property
    def alpha_2_code(self) -> str | None:
        return None


@dataclass
class CertificateProcessingResult:
    success: bool
    cert_id: str | None = None
    error: Exception | None = None


@dataclass
class CSCACertificateMetadata:
    subject_key_identifier: str
    fingerprint_sha256: str
    serial_number: str
    subject_name: str
    issuer_name: str
    country_code: str
    country_name: str
    valid_from: datetime
    valid_until: datetime
    is_expired: bool
    days_until_expiry: int
    signature_algorithm: str
    public_key_algorithm: str
    key_size: int | None
    trust_level: TrustLevel
    status: CSCAStatus
    last_verified: datetime | None
    source: str
    added_date: datetime
    pkd_country_list: list[str]

    @property
    def is_self_signed(self) -> bool:
        return self.subject_name == self.issuer_name

    @property
    def needs_renewal_warning(self) -> bool:
        return 0 < self.days_until_expiry <= 90

    @property
    def is_valid(self) -> bool:
        return not self.is_expired and self.status == CSCAStatus.ACTIVE and self.trust_level == TrustLevel.FULL_TRUST


def _native():
    return load_native_backend(
        "marty_verification",
        (
            "CscaRegistry",
            "certificate_der_to_pem",
            "certificate_pem_to_der",
            "get_certificate_info",
            "load_certificate_der",
        ),
    )


def _as_der(native: Any, certificate: Any) -> bytes:
    if isinstance(certificate, Certificate):
        return certificate.to_der()
    if isinstance(certificate, bytes):
        if certificate.lstrip().startswith(b"-----BEGIN"):
            return bytes(native.certificate_pem_to_der(certificate.decode("ascii")))
        return bytes(native.load_certificate_der(certificate))
    if isinstance(certificate, str):
        return bytes(native.certificate_pem_to_der(certificate))
    raise NativeOperationError("CSCA certificates must be native DER or PEM values")


class CSCATrustStore:
    """Use the Rust CSCA registry as the authoritative in-memory trust store."""

    def __init__(self, trust_store_path: Path | None = None) -> None:
        native = _native()
        self.trust_store_path = trust_store_path
        self._registry = (
            native.CscaRegistry.from_directory(str(trust_store_path))
            if trust_store_path is not None and trust_store_path.exists()
            else native.CscaRegistry()
        )
        self._metadata: dict[str, CSCACertificateMetadata] = {}

    def add_csca_certificate(
        self,
        certificate: Any,
        country_code: str | None = None,
        trust_level: TrustLevel = TrustLevel.FULL_TRUST,
        source: str = "manual",
    ) -> str:
        if trust_level != TrustLevel.FULL_TRUST:
            raise NativeOperationError("Only explicitly fully trusted CSCAs may enter the registry")
        if not country_code:
            raise NativeOperationError("An explicit ISO country code is required for a CSCA")
        native = _native()
        der = _as_der(native, certificate)
        info = dict(native.get_certificate_info(der))
        if not info.get("is_ca"):
            raise NativeOperationError("A CSCA trust anchor must be a CA certificate")
        pem = native.certificate_der_to_pem(der)
        self._registry.add_country_csca(country_code.upper(), pem)
        fingerprint = str(info["fingerprint_sha256"])
        self._metadata[fingerprint] = self._metadata_from_info(
            info,
            country_code.upper(),
            source,
        )
        return fingerprint

    def load_csca_certificates_from_directory(self, directory: Path) -> list[str]:
        native = _native()
        loaded = native.CscaRegistry.from_directory(str(directory))
        identifiers: list[str] = []
        for country in loaded.supported_countries():
            for pem in loaded.get_country_cscas_pem(country):
                identifiers.append(self.add_csca_certificate(pem, country, source=str(directory)))
        return identifiers

    def get_csca_certificates_for_country(self, country_code: str) -> list[Certificate]:
        return [Certificate.from_pem(pem) for pem in self._registry.get_country_cscas_pem(country_code.upper())]

    def get_all_trusted_certificates(self) -> list[Certificate]:
        return [Certificate.from_pem(pem) for pem in self._registry.get_anchors_pem()]

    def verify_csca_certificate(self, certificate: Any) -> bool:
        validator = CertificateChainValidator(self.get_all_trusted_certificates())
        return validator.validate_certificate_chain(certificate).is_valid

    def update_certificate_trust_level(self, cert_id: str, trust_level: TrustLevel) -> bool:
        del cert_id, trust_level
        raise NativeOperationError("Native CSCA trust changes require rebuilding the governed registry")

    def get_certificate_metadata(self, cert_id: str) -> CSCACertificateMetadata | None:
        return self._metadata.get(cert_id)

    def get_certificates_by_trust_level(
        self,
        trust_level: TrustLevel,
    ) -> list[CSCACertificateMetadata]:
        return [item for item in self._metadata.values() if item.trust_level == trust_level]

    def get_expiring_certificates(self, days_ahead: int = 90) -> list[CSCACertificateMetadata]:
        cutoff = datetime.now(UTC) + timedelta(days=days_ahead)
        return [item for item in self._metadata.values() if item.valid_until <= cutoff]

    def get_trust_store_statistics(self) -> dict[str, Any]:
        return {
            "total_certificates": len(self._registry),
            "countries": list(self._registry.supported_countries()),
            "native_backend": "marty_verification.CscaRegistry",
        }

    @staticmethod
    def _metadata_from_info(
        info: dict[str, Any],
        country: str,
        source: str,
    ) -> CSCACertificateMetadata:
        parse = lambda value: datetime.fromisoformat(str(value).replace("Z", "+00:00"))  # noqa: E731
        valid_from = parse(info["not_before"])
        valid_until = parse(info["not_after"])
        now = datetime.now(UTC)
        return CSCACertificateMetadata(
            subject_key_identifier="",
            fingerprint_sha256=str(info["fingerprint_sha256"]),
            serial_number=str(info["serial_number"]),
            subject_name=str(info["subject"]),
            issuer_name=str(info["issuer"]),
            country_code=country,
            country_name=country,
            valid_from=valid_from,
            valid_until=valid_until,
            is_expired=valid_until < now,
            days_until_expiry=max(0, (valid_until - now).days),
            signature_algorithm=str(info.get("signature_algorithm", "")),
            public_key_algorithm=str(info.get("public_key_algorithm", "")),
            key_size=info.get("key_size"),
            trust_level=TrustLevel.FULL_TRUST,
            status=CSCAStatus.EXPIRED if valid_until < now else CSCAStatus.ACTIVE,
            last_verified=now,
            source=source,
            added_date=now,
            pkd_country_list=[country],
        )


def create_default_csca_trust_store(trust_store_path: Path | None = None) -> CSCATrustStore:
    return CSCATrustStore(trust_store_path)


def load_csca_from_pkd_master_list(
    master_list_path: Path,
    trust_store: CSCATrustStore,
) -> list[str]:
    del master_list_path, trust_store
    raise NativeOperationError(
        "Master-list ingestion requires a pinned signer certificate and the native PKD sync service"
    )


__all__ = [
    "CSCACertificateMetadata",
    "CSCAStatus",
    "CSCATrustStore",
    "CertificateProcessingResult",
    "CountryInfo",
    "TrustLevel",
    "create_default_csca_trust_store",
    "load_csca_from_pkd_master_list",
]
