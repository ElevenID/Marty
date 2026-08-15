"""Thin fail-closed adapters for the canonical Rust eMRTD data kernel."""

from __future__ import annotations

import json
from typing import Any

from marty_common.native_backends import NativeOperationError, load_native_backend

_CAPABILITIES = (
    "emrtd_inspect_rsa_public_key_json",
    "emrtd_parse_biometric_template_json",
    "emrtd_parse_dg15_json",
    "emrtd_parse_ef_com_json",
    "emrtd_parse_ef_dg1_json",
    "emrtd_parse_ef_dg2_json",
    "emrtd_parse_elementary_file_json",
    "emrtd_parse_tlv_json",
    "emrtd_rsa_public_key_spki",
    "emrtd_validate_biometric_quality_json",
)


def _backend():
    return load_native_backend("marty_verification", _CAPABILITIES)


def _decode_result(operation: str, result: str) -> dict[str, Any]:
    try:
        decoded = json.loads(result)
    except (TypeError, ValueError) as exc:
        raise NativeOperationError(f"Native eMRTD operation {operation!r} returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise NativeOperationError(f"Native eMRTD operation {operation!r} returned a non-object result")
    return decoded


def parse_tlv(data: bytes, offset: int = 0) -> dict[str, Any]:
    return _decode_result(
        "emrtd_parse_tlv_json",
        _backend().emrtd_parse_tlv_json(bytes(data), offset),
    )


def parse_ef_com(data: bytes) -> dict[str, Any]:
    return _decode_result("emrtd_parse_ef_com_json", _backend().emrtd_parse_ef_com_json(bytes(data)))


def parse_ef_dg1(data: bytes) -> dict[str, Any]:
    return _decode_result("emrtd_parse_ef_dg1_json", _backend().emrtd_parse_ef_dg1_json(bytes(data)))


def parse_ef_dg2(data: bytes) -> dict[str, Any]:
    return _decode_result("emrtd_parse_ef_dg2_json", _backend().emrtd_parse_ef_dg2_json(bytes(data)))


def parse_elementary_file(file_id: str, data: bytes) -> dict[str, Any]:
    return _decode_result(
        "emrtd_parse_elementary_file_json",
        _backend().emrtd_parse_elementary_file_json(file_id, bytes(data)),
    )


def parse_biometric_template(data: bytes, biometric_type: str) -> dict[str, Any]:
    return _decode_result(
        "emrtd_parse_biometric_template_json",
        _backend().emrtd_parse_biometric_template_json(bytes(data), biometric_type),
    )


def validate_biometric_quality(template: dict[str, Any]) -> dict[str, Any]:
    return _decode_result(
        "emrtd_validate_biometric_quality_json",
        _backend().emrtd_validate_biometric_quality_json(json.dumps(template, separators=(",", ":"))),
    )


def parse_dg15(data: bytes) -> dict[str, Any]:
    return _decode_result("emrtd_parse_dg15_json", _backend().emrtd_parse_dg15_json(bytes(data)))


def rsa_public_key_spki(modulus: int, public_exponent: int) -> bytes:
    return bytes(_backend().emrtd_rsa_public_key_spki(str(modulus), public_exponent))


def inspect_rsa_public_key(spki_der: bytes) -> dict[str, Any]:
    return _decode_result(
        "emrtd_inspect_rsa_public_key_json",
        _backend().emrtd_inspect_rsa_public_key_json(bytes(spki_der)),
    )


__all__ = [
    "parse_biometric_template",
    "inspect_rsa_public_key",
    "parse_dg15",
    "parse_ef_com",
    "parse_ef_dg1",
    "parse_ef_dg2",
    "parse_elementary_file",
    "parse_tlv",
    "rsa_public_key_spki",
    "validate_biometric_quality",
]
