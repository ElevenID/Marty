"""Native compatibility adapter for ICAO EF.SOD parsing and hash checks."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar

from marty_common.native_backends import load_native_backend


class SODParsingError(Exception):
    """Raised when native SOD parsing fails."""

    def __init__(self, message: str, details: str | None = None) -> None:
        super().__init__(f"{message}: {details}" if details else message)


class HashAlgorithmError(Exception):
    """Raised when an SOD names an unsupported digest algorithm."""

    def __init__(self, algorithm: str) -> None:
        super().__init__(f"Unsupported hash algorithm: {algorithm}")


class HashAlgorithm(Enum):
    """Compatibility identifiers accepted by native hashing APIs."""

    SHA1 = "sha1"
    SHA256 = "sha256"
    SHA384 = "sha384"
    SHA512 = "sha512"


@dataclass(frozen=True, slots=True)
class NativeSOD:
    """Opaque native-parsed SOD plus normalized metadata."""

    der: bytes
    metadata: dict[str, Any]


def _native():
    return load_native_backend(
        "marty_verification",
        (
            "parse_sod",
            "verify_sod_data_group_hash",
            "verify_sod_signature",
        ),
    )


def _sod_der(value: str | bytes | NativeSOD) -> bytes:
    if isinstance(value, NativeSOD):
        return value.der
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        try:
            return bytes.fromhex(value.replace(" ", "").replace("\n", ""))
        except ValueError:
            try:
                return base64.b64decode(value, validate=True)
            except (ValueError, TypeError) as exc:
                raise SODParsingError("Invalid hex/base64 SOD data", str(exc)) from exc
    raise SODParsingError(f"Unsupported SOD data type: {type(value).__name__}")


class SODProcessor:
    """Preserve the former Python API while executing every kernel in Rust."""

    SUPPORTED_HASH_ALGORITHMS: ClassVar[set[str]] = {
        "sha1",
        "sha256",
        "sha384",
        "sha512",
    }

    def parse_sod_data(self, sod_data: str | bytes) -> NativeSOD:
        der = _sod_der(sod_data)
        try:
            metadata = dict(_native().parse_sod(der))
        except Exception as exc:
            raise SODParsingError("Native SOD parsing failed", str(exc)) from exc
        return NativeSOD(der=der, metadata=metadata)

    def extract_hash_algorithm(self, sod: NativeSOD) -> str:
        raw_algorithm = str(sod.metadata.get("hash_algorithm", "")).lower()
        algorithm = {
            "1.3.14.3.2.26": "sha1",
            "2.16.840.1.101.3.4.2.1": "sha256",
            "2.16.840.1.101.3.4.2.2": "sha384",
            "2.16.840.1.101.3.4.2.3": "sha512",
        }.get(raw_algorithm, raw_algorithm.replace("-", ""))
        if algorithm not in self.SUPPORTED_HASH_ALGORITHMS:
            raise HashAlgorithmError(algorithm or "unknown")
        return algorithm

    def extract_data_group_hashes(self, sod: NativeSOD) -> dict[int, bytes]:
        try:
            return {
                int(item["data_group_number"]): (
                    bytes.fromhex(item["hash_value"])
                    if isinstance(item["hash_value"], str)
                    else bytes(item["hash_value"])
                )
                for item in sod.metadata.get("data_group_hashes", [])
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise SODParsingError("Invalid native SOD hash metadata", str(exc)) from exc

    def verify_data_group_integrity(
        self,
        sod: NativeSOD,
        data_groups: dict[int, bytes],
    ) -> tuple[bool, list[str]]:
        expected = self.extract_data_group_hashes(sod)
        errors: list[str] = []
        native = _native()
        for number, content in data_groups.items():
            if number not in expected:
                errors.append(f"Data group {number} not found in SOD")
                continue
            try:
                valid = bool(native.verify_sod_data_group_hash(sod.der, number, bytes(content)))
            except Exception as exc:
                errors.append(f"Data group {number} verification failed: {exc}")
                continue
            if not valid:
                errors.append(f"Data group {number} hash mismatch")
        errors.extend(f"Missing data group {number}" for number in expected if number not in data_groups)
        return not errors, errors

    def extract_sod_info(self, sod: NativeSOD) -> dict[str, Any]:
        hashes = self.extract_data_group_hashes(sod)
        signer = sod.metadata.get("document_signer_cert") or ""
        return {
            "version": sod.metadata.get("lds_version"),
            "hash_algorithm": self.extract_hash_algorithm(sod),
            "data_groups": hashes,
            "signer_info": {},
            "certificates": [signer] if signer else [],
            "has_certificate": bool(signer),
            "signature_valid": bool(_native().verify_sod_signature(sod.der)),
        }


def parse_sod(sod_data: str | bytes) -> NativeSOD:
    """Parse SOD data with the canonical native implementation."""

    return SODProcessor().parse_sod_data(sod_data)


def extract_sod_hashes(sod_data: str | bytes) -> dict[int, bytes]:
    """Extract native-parsed data-group hashes."""

    processor = SODProcessor()
    return processor.extract_data_group_hashes(processor.parse_sod_data(sod_data))


def verify_data_group_integrity_from_sod(
    sod_data: str | bytes,
    data_groups: dict[int, bytes],
) -> tuple[bool, list[str]]:
    """Verify all supplied data groups using native SOD checks."""

    try:
        processor = SODProcessor()
        sod = processor.parse_sod_data(sod_data)
        return processor.verify_data_group_integrity(sod, data_groups)
    except (SODParsingError, HashAlgorithmError) as exc:
        return False, [str(exc)]


__all__ = [
    "HashAlgorithmError",
    "HashAlgorithm",
    "NativeSOD",
    "SODParsingError",
    "SODProcessor",
    "extract_sod_hashes",
    "parse_sod",
    "verify_data_group_integrity_from_sod",
]
