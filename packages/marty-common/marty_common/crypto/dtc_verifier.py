"""Native Digital Travel Credential compatibility helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from marty_common.crypto.certificate_validator import (
    CertificateChainValidator,
    ChainValidationResult,
)
from marty_common.native_backends import NativeOperationError, load_native_backend


@dataclass(slots=True)
class DTCIntegrityResult:
    is_valid: bool
    mismatches: list[str]
    expected: Mapping[str, str]
    computed: Mapping[str, str]


@dataclass(slots=True)
class DTCSignatureResult:
    is_valid: bool
    certificate_subject: str
    chain_result: ChainValidationResult | None
    error: str | None = None


class DTCVerifier:
    """Compatibility adapter for native DTC hashing and trust validation."""

    def __init__(self, trust_anchors: Iterable[Any] | None = None) -> None:
        self._chain_validator = CertificateChainValidator()
        if trust_anchors:
            self._chain_validator.load_csca_certificates(list(trust_anchors))

    @staticmethod
    def compute_data_group_hashes(
        data_groups: Sequence[Mapping[str, Any]],
        algorithm: str = "sha256",
    ) -> dict[str, str]:
        canonical = algorithm.lower().replace("-", "")
        if canonical not in {"sha1", "sha256", "sha384", "sha512"}:
            raise NativeOperationError(f"Unsupported native DTC hash algorithm: {algorithm}")
        native = load_native_backend("marty_verification", ("hash_data",))
        results: dict[str, str] = {}
        for item in data_groups:
            number = item.get("dg_number") or item.get("number") or item.get("id")
            if number is None:
                raise NativeOperationError("DTC data group is missing its number")
            raw = item.get("data") if "data" in item else item.get("content")
            if raw is None:
                raise NativeOperationError(f"DTC data group {number} is missing content")
            if isinstance(raw, str):
                try:
                    payload = bytes.fromhex(raw)
                except ValueError:
                    payload = raw.encode("utf-8")
            else:
                payload = bytes(raw)
            results[str(number)] = bytes(native.hash_data(canonical, payload)).hex()
        return results

    def verify_data_group_hashes(
        self,
        credential_payload: Mapping[str, Any],
        data_groups: Sequence[Mapping[str, Any]],
        algorithm: str = "sha256",
    ) -> DTCIntegrityResult:
        expected = credential_payload.get("dataGroupHashes")
        if not isinstance(expected, Mapping) or not expected:
            return DTCIntegrityResult(False, ["Missing signed data-group hashes"], {}, {})
        computed = self.compute_data_group_hashes(data_groups, algorithm)
        expected_strings = {str(key): str(value) for key, value in expected.items()}
        mismatches = [
            f"Hash mismatch or missing DG{number}"
            for number, digest in expected_strings.items()
            if computed.get(number, "").lower() != digest.lower()
        ]
        mismatches.extend(
            f"Unexpected DG{number} in supplied data groups" for number in computed if number not in expected_strings
        )
        return DTCIntegrityResult(
            not mismatches,
            mismatches,
            expected_strings,
            computed,
        )

    def verify_signature(
        self,
        payload: Mapping[str, Any],
        signature: bytes,
        signer_certificate: Any,
        signature_algorithm: Any | None = None,
    ) -> DTCSignatureResult:
        del payload, signature, signer_certificate, signature_algorithm
        raise NativeOperationError(
            "Detached Python DTC signature verification is retired; submit the complete "
            "signed DTC to marty-verification.dtc_verify"
        )

    def validate_certificate_chain(
        self,
        signer_certificate: Any,
        intermediates: Sequence[Any] | None = None,
    ) -> ChainValidationResult:
        return self._chain_validator.validate_certificate_chain(
            signer_certificate,
            list(intermediates or ()),
        )


__all__ = ["DTCIntegrityResult", "DTCSignatureResult", "DTCVerifier"]
