"""Native-backed eMRTD data-group hashing and SOD comparison."""

from __future__ import annotations

import json
from typing import Any

from marty_common.crypto.sod_parser import SODProcessor
from marty_common.native_backends import load_native_backend


class DataGroupHashingError(Exception):
    """Raised when a data group cannot be normalized or checked safely."""

    def __init__(self, message: str, details: str | None = None) -> None:
        super().__init__(f"{message}: {details}" if details else message)


def _native():
    return load_native_backend(
        "marty_verification",
        ("hash_data", "verify_sod_data_group_hash"),
    )


class DataGroupHashComputer:
    """Compatibility surface whose cryptographic operations execute in Rust."""

    def __init__(self) -> None:
        self.sod_processor = SODProcessor()

    def compute_data_group_hash(
        self,
        data_group_content: bytes,
        hash_algorithm: str,
    ) -> bytes:
        algorithm = hash_algorithm.lower().replace("-", "")
        if algorithm not in {"sha1", "sha256", "sha384", "sha512"}:
            raise DataGroupHashingError(f"Unsupported hash algorithm: {hash_algorithm}")
        try:
            return bytes(_native().hash_data(algorithm, bytes(data_group_content)))
        except Exception as exc:
            raise DataGroupHashingError("Native hash computation failed", str(exc)) from exc

    def compute_all_data_group_hashes(
        self,
        data_groups: dict[int, bytes],
        hash_algorithm: str,
    ) -> dict[int, bytes]:
        return {
            number: self.compute_data_group_hash(content, hash_algorithm) for number, content in data_groups.items()
        }

    def verify_data_group_integrity_with_sod(
        self,
        sod_data: str | bytes,
        data_groups: dict[int, bytes],
    ) -> tuple[bool, list[str], dict[str, Any]]:
        try:
            sod = self.sod_processor.parse_sod_data(sod_data)
            algorithm = self.sod_processor.extract_hash_algorithm(sod)
            expected = self.sod_processor.extract_data_group_hashes(sod)
            computed = self.compute_all_data_group_hashes(data_groups, algorithm)
            valid, errors = self.sod_processor.verify_data_group_integrity(
                sod,
                data_groups,
            )
        except Exception as exc:
            raise DataGroupHashingError("Native data-group verification failed", str(exc)) from exc
        return (
            valid,
            errors,
            {
                "hash_algorithm": algorithm,
                "expected_hashes": {number: value.hex() for number, value in expected.items()},
                "computed_hashes": {number: value.hex() for number, value in computed.items()},
                "data_groups_verified": len(computed),
                "data_groups_expected": len(expected),
            },
        )

    def extract_data_group_content(
        self,
        data_group_raw: bytes | str | dict[str, Any] | object,
    ) -> bytes:
        if isinstance(data_group_raw, bytes):
            return data_group_raw
        if isinstance(data_group_raw, str):
            try:
                return bytes.fromhex(data_group_raw.replace(" ", "").replace("\n", ""))
            except ValueError:
                return data_group_raw.encode("utf-8")
        if isinstance(data_group_raw, dict) and "content" in data_group_raw:
            return self.extract_data_group_content(data_group_raw["content"])
        content = getattr(data_group_raw, "content", None)
        if content is not None:
            return self.extract_data_group_content(content)
        model_dump = getattr(data_group_raw, "model_dump", None)
        if callable(model_dump):
            return json.dumps(model_dump(), sort_keys=True).encode("utf-8")
        raise DataGroupHashingError(f"Unsupported data-group content type: {type(data_group_raw).__name__}")

    def prepare_data_groups_for_verification(
        self,
        data_groups_dict: dict[str, Any],
    ) -> dict[int, bytes]:
        prepared: dict[int, bytes] = {}
        for key, value in data_groups_dict.items():
            normalized = str(key).upper()
            number_text = normalized[2:] if normalized.startswith("DG") else normalized
            try:
                number = int(number_text)
            except ValueError as exc:
                raise DataGroupHashingError(f"Invalid data group key: {key}") from exc
            prepared[number] = self.extract_data_group_content(value)
        return prepared


def verify_passport_data_groups(
    sod_data: str | bytes,
    data_groups: dict[str, Any],
) -> tuple[bool, list[str], dict[str, Any]]:
    """Verify passport data groups and normalize failures to an invalid result."""

    try:
        computer = DataGroupHashComputer()
        prepared = computer.prepare_data_groups_for_verification(data_groups)
        return computer.verify_data_group_integrity_with_sod(sod_data, prepared)
    except DataGroupHashingError as exc:
        return False, [str(exc)], {}


def compute_data_group_hash_simple(content: bytes, algorithm: str = "sha256") -> str:
    """Return a native-computed digest as lowercase hexadecimal."""

    return DataGroupHashComputer().compute_data_group_hash(content, algorithm).hex()


__all__ = [
    "DataGroupHashComputer",
    "DataGroupHashingError",
    "compute_data_group_hash_simple",
    "verify_passport_data_groups",
]
