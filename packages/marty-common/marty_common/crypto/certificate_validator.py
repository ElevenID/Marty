"""Native CSCA/DSC certificate-chain compatibility adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from marty_common.native_backends import NativeOperationError, load_native_backend


class ValidationResult(Enum):
    """Normalized certificate validation outcomes."""

    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"
    NOT_YET_VALID = "not_yet_valid"
    REVOKED = "revoked"
    UNTRUSTED = "untrusted"
    INVALID_SIGNATURE = "invalid_signature"
    INVALID_KEY_USAGE = "invalid_key_usage"
    CHAIN_BROKEN = "chain_broken"
    UNKNOWN_ERROR = "unknown_error"


class CertificateType(Enum):
    """ICAO certificate roles."""

    CSCA = "csca"
    DOCUMENT_SIGNER = "ds"
    INTERMEDIATE = "intermediate"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class ValidationError:
    certificate_subject: str
    error_type: ValidationResult
    error_message: str
    severity: str

    @property
    def is_critical(self) -> bool:
        return self.severity == "critical"


@dataclass(slots=True)
class CertificateInfo:
    certificate: bytes
    cert_type: CertificateType
    subject: str
    issuer: str
    serial_number: str
    valid_from: datetime
    valid_until: datetime
    signature_algorithm: str
    key_size: int | None
    key_usage: list[str]
    extended_key_usage: list[str]
    is_ca: bool
    path_length: int | None
    _fingerprint_sha256: str

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.valid_until

    @property
    def is_not_yet_valid(self) -> bool:
        return datetime.now(UTC) < self.valid_from

    @property
    def days_until_expiry(self) -> int:
        return max(0, (self.valid_until - datetime.now(UTC)).days)

    @property
    def fingerprint_sha256(self) -> str:
        return self._fingerprint_sha256.upper()


@dataclass(slots=True)
class ChainValidationResult:
    is_valid: bool
    trust_anchor: bytes | None
    validation_path: list[CertificateInfo]
    errors: list[ValidationError]
    warnings: list[ValidationError]
    validation_time: datetime
    signature_verified: bool

    @property
    def has_critical_errors(self) -> bool:
        return any(error.is_critical for error in self.errors)

    @property
    def error_summary(self) -> str:
        if not self.errors:
            return "No errors"
        critical = sum(error.is_critical for error in self.errors)
        return f"{critical} critical errors, {len(self.errors) - critical} warnings"

    def get_certificate_by_type(
        self,
        cert_type: CertificateType,
    ) -> CertificateInfo | None:
        return next(
            (item for item in self.validation_path if item.cert_type == cert_type),
            None,
        )


def _native():
    return load_native_backend(
        "marty_verification",
        (
            "ChainValidator",
            "certificate_der_to_pem",
            "certificate_pem_to_der",
            "crl_pem_to_der",
            "get_certificate_info",
            "get_certificate_public_key",
            "get_key_size",
            "load_certificate_der",
            "parse_crl",
        ),
    )


def _certificate_der(native: Any, value: Any) -> bytes:
    if isinstance(value, bytes):
        if value.lstrip().startswith(b"-----BEGIN"):
            return bytes(native.certificate_pem_to_der(value.decode("ascii")))
        return bytes(native.load_certificate_der(value))
    if isinstance(value, str):
        return bytes(native.certificate_pem_to_der(value))
    certificate_data = getattr(value, "certificate_data", None)
    if certificate_data is not None:
        return _certificate_der(native, certificate_data)
    for method_name in ("to_der", "as_der"):
        method = getattr(value, method_name, None)
        if callable(method):
            return _certificate_der(native, method())
    raise NativeOperationError("Native certificate validation requires DER or PEM certificate inputs")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class CertificateChainValidator:
    """Python-facing orchestration around the Rust chain validator."""

    ICAO_MRTD_SECURITY_OBJECT_OID = "2.23.136.1.1.1"
    DOCUMENT_SIGNER_KEY_USAGE = ["digitalSignature"]
    CSCA_KEY_USAGE = ["keyCertSign", "cRLSign"]

    def __init__(self, trust_store: Any | None = None) -> None:
        self._trust_anchors: dict[str, bytes] = {}
        self._crls: list[bytes] = []
        if trust_store is not None:
            try:
                self.load_csca_certificates(list(trust_store))
            except TypeError as exc:
                raise NativeOperationError("Trust store must be an iterable of DER/PEM certificates") from exc

    def add_trust_anchor(self, csca_cert: Any) -> None:
        native = _native()
        der = _certificate_der(native, csca_cert)
        info = native.get_certificate_info(der)
        if not info.get("is_ca"):
            raise NativeOperationError("A CSCA trust anchor must be a CA certificate")
        self._trust_anchors[str(info["fingerprint_sha256"])] = der

    def load_csca_certificates(self, csca_certs: list[Any]) -> None:
        for certificate in csca_certs:
            self.add_trust_anchor(certificate)

    def add_crl(self, crl: Any) -> None:
        native = _native()
        if isinstance(crl, str):
            der = bytes(native.crl_pem_to_der(crl))
        elif isinstance(crl, bytes):
            der = bytes(native.crl_pem_to_der(crl.decode("ascii"))) if crl.lstrip().startswith(b"-----BEGIN") else crl
        else:
            raise NativeOperationError("Native revocation checking requires DER or PEM CRLs")
        native.parse_crl(der)
        self._crls.append(der)

    def add_ocsp_response(self, response: Any) -> None:
        del response
        raise NativeOperationError("OCSP responses must be verified by the native revocation service")

    def validate_certificate_chain(
        self,
        end_entity_cert: Any,
        intermediate_certs: list[Any] | None = None,
        validation_time: datetime | None = None,
    ) -> ChainValidationResult:
        if (
            validation_time is not None
            and abs((datetime.now(UTC) - validation_time.astimezone(UTC)).total_seconds()) > 5
        ):
            raise NativeOperationError("Historical certificate validation time is not supported by this native adapter")
        return self._validate(end_entity_cert, intermediate_certs or [], None)

    def validate_chain_with_rust(
        self,
        end_entity_cert: Any,
        intermediate_certs: list[Any] | None = None,
        validation_config: Any | None = None,
    ) -> ChainValidationResult:
        return self._validate(
            end_entity_cert,
            intermediate_certs or [],
            validation_config,
        )

    def _validate(
        self,
        end_entity_cert: Any,
        intermediate_certs: list[Any],
        validation_config: Any | None,
    ) -> ChainValidationResult:
        native = _native()
        now = datetime.now(UTC)
        try:
            leaf = _certificate_der(native, end_entity_cert)
            intermediates = [_certificate_der(native, certificate) for certificate in intermediate_certs]
        except Exception as exc:
            return self._failure("Unknown", str(exc), now)
        if not self._trust_anchors:
            subject = str(native.get_certificate_info(leaf).get("subject", "Unknown"))
            return self._failure(subject, "No CSCA trust anchors configured", now)

        validator = native.ChainValidator()
        for anchor in self._trust_anchors.values():
            validator.add_trust_anchor_der(anchor)
        for intermediate in intermediates:
            validator.add_intermediate_der(intermediate)
        for crl in self._crls:
            validator.add_crl(crl)

        chain = [native.certificate_der_to_pem(certificate) for certificate in [leaf, *intermediates]]
        try:
            result = (
                validator.validate_with_config(chain, validation_config)
                if validation_config is not None
                else validator.validate_chain(chain)
            )
        except Exception as exc:
            return self._failure("Unknown", f"Native chain validation failed: {exc}", now)

        path = [
            self._certificate_info(native, certificate, index)
            for index, certificate in enumerate([leaf, *intermediates])
        ]
        subject = str(result.subject or path[0].subject)
        errors = [ValidationError(subject, ValidationResult.INVALID, value, "critical") for value in result.errors]
        warnings = [ValidationError(subject, ValidationResult.VALID, value, "warning") for value in result.warnings]
        trust_anchor = self._matching_anchor(native, path[-1].issuer)
        if result.valid and trust_anchor is None:
            errors.append(
                ValidationError(
                    subject,
                    ValidationResult.UNTRUSTED,
                    "Native validation did not resolve a configured trust anchor",
                    "critical",
                )
            )
        valid = bool(result.valid and trust_anchor is not None and not errors)
        return ChainValidationResult(
            is_valid=valid,
            trust_anchor=trust_anchor,
            validation_path=path,
            errors=errors,
            warnings=warnings,
            validation_time=now,
            signature_verified=valid,
        )

    def _certificate_info(
        self,
        native: Any,
        certificate: bytes,
        index: int,
    ) -> CertificateInfo:
        info = native.get_certificate_info(certificate)
        public_key = native.get_certificate_public_key(certificate)
        return CertificateInfo(
            certificate=certificate,
            cert_type=(CertificateType.DOCUMENT_SIGNER if index == 0 else CertificateType.INTERMEDIATE),
            subject=str(info["subject"]),
            issuer=str(info["issuer"]),
            serial_number=str(info["serial_number"]),
            valid_from=_parse_time(str(info["not_before"])),
            valid_until=_parse_time(str(info["not_after"])),
            signature_algorithm="native",
            key_size=int(native.get_key_size(public_key)),
            key_usage=list(info.get("key_usage", [])),
            extended_key_usage=[],
            is_ca=bool(info.get("is_ca")),
            path_length=None,
            _fingerprint_sha256=str(info["fingerprint_sha256"]),
        )

    def _matching_anchor(self, native: Any, issuer: str) -> bytes | None:
        normalized = issuer.upper().replace(" ", "")
        for certificate in self._trust_anchors.values():
            subject = str(native.get_certificate_info(certificate)["subject"])
            if subject.upper().replace(" ", "") == normalized:
                return certificate
        return None

    @staticmethod
    def _failure(
        subject: str,
        message: str,
        validation_time: datetime,
    ) -> ChainValidationResult:
        return ChainValidationResult(
            is_valid=False,
            trust_anchor=None,
            validation_path=[],
            errors=[
                ValidationError(
                    subject,
                    ValidationResult.UNTRUSTED,
                    message,
                    "critical",
                )
            ],
            warnings=[],
            validation_time=validation_time,
            signature_verified=False,
        )

    def clear_cache(self) -> None:
        """Retained for API compatibility; native validation is not cached here."""

    def get_trust_anchors(self) -> list[bytes]:
        return list(self._trust_anchors.values())


def validate_passport_certificate_chain(
    document_signer_cert: Any,
    intermediate_certs: list[Any] | None = None,
    csca_certs: list[Any] | None = None,
) -> ChainValidationResult:
    validator = CertificateChainValidator()
    validator.load_csca_certificates(csca_certs or [])
    return validator.validate_certificate_chain(
        document_signer_cert,
        intermediate_certs or [],
    )


def create_passport_validator_with_trust_store(
    csca_certificates: list[Any],
) -> CertificateChainValidator:
    validator = CertificateChainValidator()
    validator.load_csca_certificates(csca_certificates)
    return validator


__all__ = [
    "CertificateChainValidator",
    "CertificateInfo",
    "CertificateType",
    "ChainValidationResult",
    "ValidationError",
    "ValidationResult",
    "create_passport_validator_with_trust_store",
    "validate_passport_certificate_chain",
]
