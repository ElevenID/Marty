"""Native-backed high-level ICAO eMRTD verification adapter."""

from __future__ import annotations

import base64
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from marty_common.crypto.certificate_validator import (
    CertificateChainValidator,
    ChainValidationResult,
    ValidationError,
    ValidationResult,
)
from marty_common.crypto.data_group_hasher import DataGroupHashComputer
from marty_common.crypto.sod_parser import NativeSOD, SODProcessor
from marty_common.crypto.sod_signer import verify_sod_signature
from marty_common.native_backends import NativeOperationError, load_native_backend


@dataclass
class MRZValidationResult:
    is_valid: bool
    mrz_string: str
    parsed: Any | None
    errors: list[str]


@dataclass
class SODValidationResult:
    is_valid: bool
    hash_algorithm: str | None
    expected_hashes: dict[int, str]
    computed_hashes: dict[int, str]
    errors: list[str]


@dataclass
class CertificateValidationSummary:
    result: ChainValidationResult
    sod_certificate_subject: str | None


@dataclass
class ActiveAuthenticationResult:
    is_valid: bool
    challenge: Any
    chip_info: Any | None
    recovered_message: bytes | None
    error: str | None = None


class PassportCryptoValidationError(Exception):
    """Raised when native passport verification cannot be completed."""


class PassportCryptoValidator:
    """Compose native MRZ, SOD, data-group, and certificate validation."""

    def __init__(self, trust_anchors: Iterable[Any] | None = None) -> None:
        self._sod_processor = SODProcessor()
        self._hash_computer = DataGroupHashComputer()
        self._cert_validator = CertificateChainValidator()
        self._trust_anchors: list[Any] = []
        if trust_anchors:
            self.load_trust_anchors(trust_anchors)

    def load_trust_anchors(self, certificates: Iterable[Any]) -> None:
        for certificate in certificates:
            self._cert_validator.add_trust_anchor(certificate)
            self._trust_anchors.append(certificate)

    def validate_mrz(self, mrz_lines: Sequence[str] | str) -> MRZValidationResult:
        payload = mrz_lines.strip() if isinstance(mrz_lines, str) else "\n".join(line.strip() for line in mrz_lines)
        native = load_native_backend("marty_verification", ("parse_mrz",))
        try:
            parsed = native.parse_mrz(payload.splitlines())
        except (RuntimeError, TypeError, ValueError) as exc:
            return MRZValidationResult(False, payload, None, [str(exc)])
        if not parsed.check_digits_valid:
            return MRZValidationResult(False, payload, parsed, ["MRZ check digits are invalid"])
        return MRZValidationResult(True, payload, parsed, [])

    def verify_sod(
        self,
        sod_blob: bytes | str,
        data_groups: dict[str, Any],
    ) -> SODValidationResult:
        try:
            prepared = self._hash_computer.prepare_data_groups_for_verification(data_groups)
            valid, errors, details = self._hash_computer.verify_data_group_integrity_with_sod(
                sod_blob,
                prepared,
            )
        except Exception as exc:
            raise PassportCryptoValidationError(str(exc)) from exc
        return SODValidationResult(
            is_valid=valid,
            hash_algorithm=details.get("hash_algorithm"),
            expected_hashes={int(key): value for key, value in details.get("expected_hashes", {}).items()},
            computed_hashes={int(key): value for key, value in details.get("computed_hashes", {}).items()},
            errors=errors,
        )

    def parse_sod(self, sod_blob: bytes | str) -> NativeSOD:
        try:
            return self._sod_processor.parse_sod_data(sod_blob)
        except Exception as exc:
            raise PassportCryptoValidationError(str(exc)) from exc

    def validate_sod_certificate(
        self,
        sod_blob: bytes | str,
        extra_trust_anchors: Sequence[Any] | None = None,
    ) -> CertificateValidationSummary:
        if extra_trust_anchors:
            self.load_trust_anchors(extra_trust_anchors)
        sod = self.parse_sod(sod_blob)
        signer = sod.metadata.get("document_signer_cert")
        if not signer:
            raise PassportCryptoValidationError("SOD does not contain a Document Signer certificate")
        result = self._cert_validator.validate_certificate_chain(signer)
        if not verify_sod_signature(sod.der, self._trust_anchors):
            result.is_valid = False
            result.signature_verified = False
            result.errors.append(
                ValidationError(
                    certificate_subject=str(signer)[:80],
                    error_type=ValidationResult.INVALID_SIGNATURE,
                    error_message="Native SOD signature or DSC chain validation failed",
                    severity="critical",
                )
            )
        subject = result.validation_path[0].subject if result.validation_path else None
        return CertificateValidationSummary(result=result, sod_certificate_subject=subject)

    def generate_active_authentication_challenge(
        self,
        key_size_bits: int = 128,
        hash_algorithm: Any | None = None,
    ) -> Any:
        del key_size_bits, hash_algorithm
        raise NativeOperationError(
            "Active Authentication challenge generation requires the native chip-session service"
        )

    def verify_active_authentication(
        self,
        dg15_data: bytes,
        challenge: Any,
        signature: bytes,
    ) -> ActiveAuthenticationResult:
        del dg15_data, challenge, signature
        raise NativeOperationError(
            "Detached Python Active Authentication is retired; use the native chip-session service"
        )

    def perform_chip_active_authentication(self, transport: Any, **kwargs: Any) -> Any:
        del transport, kwargs
        raise NativeOperationError(
            "Python BAC/PACE and Active Authentication are retired; use the native chip-session service"
        )

    @staticmethod
    def decode_maybe_base64(data: bytes | str) -> bytes:
        if isinstance(data, bytes):
            return data
        try:
            return base64.b64decode(data, validate=True)
        except ValueError:
            try:
                return bytes.fromhex(data)
            except ValueError as exc:
                raise PassportCryptoValidationError(
                    "Passport binary input must be bytes, base64, or hexadecimal"
                ) from exc


__all__ = [
    "ActiveAuthenticationResult",
    "CertificateValidationSummary",
    "MRZValidationResult",
    "PassportCryptoValidationError",
    "PassportCryptoValidator",
    "SODValidationResult",
]
