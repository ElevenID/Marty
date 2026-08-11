"""Thin fail-closed adapter for the canonical Rust VDS-NC profile."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from marty_common.native_backends import NativeOperationError

from marty_plugin.native_backends import require_backend


def _call(operation: str, *args: object) -> Any:
    backend = require_backend("_marty_rs")
    native_operation = getattr(backend, operation)
    try:
        return native_operation(*args)
    except Exception as exc:
        if isinstance(exc, NativeOperationError):
            raise
        raise NativeOperationError(f"Native VDS-NC {operation} failed: {exc}") from exc


def _json_object(value: str, operation: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise NativeOperationError(
            f"Native VDS-NC {operation} returned invalid JSON"
        ) from exc
    if not isinstance(decoded, dict):
        raise NativeOperationError(
            f"Native VDS-NC {operation} returned a non-object result"
        )
    return decoded


def inspect_profile(barcode_data: str) -> dict[str, Any]:
    """Inspect one Rust-validated canonical envelope."""

    return _json_object(_call("vds_nc_inspect", barcode_data), "inspection")


def sign_profile(
    *,
    private_key_pem: str,
    signer_id: str,
    certificate_reference: str,
    document_type: str,
    issuing_country: str,
    document_data: dict[str, Any],
    algorithm: str,
) -> dict[str, Any]:
    """Canonicalize and sign one profile entirely in Rust."""

    result = _call(
        "vds_nc_sign_profile",
        private_key_pem,
        signer_id,
        certificate_reference,
        document_type,
        issuing_country,
        json.dumps(document_data, ensure_ascii=False, separators=(",", ":")),
        algorithm,
    )
    return _json_object(result, "signing")


def verify_profile(
    barcode_data: str,
    public_key_pem: str,
    printed_values: dict[str, Any] | None = None,
    evaluation_date: date | None = None,
) -> dict[str, Any]:
    """Run canonical, signature, field, and temporal checks in Rust."""

    printed_json = (
        json.dumps(printed_values, ensure_ascii=False, separators=(",", ":"))
        if printed_values is not None
        else None
    )
    result = _call(
        "vds_nc_verify_profile",
        barcode_data,
        public_key_pem,
        (evaluation_date or date.today()).isoformat(),
        printed_json,
    )
    return _json_object(result, "verification")


def validate_profile(
    barcode_data: str,
    printed_values: dict[str, Any] | None = None,
    evaluation_date: date | None = None,
) -> dict[str, Any]:
    """Run non-authenticity profile checks in Rust."""

    printed_json = (
        json.dumps(printed_values, ensure_ascii=False, separators=(",", ":"))
        if printed_values is not None
        else None
    )
    result = _call(
        "vds_nc_validate_profile",
        barcode_data,
        (evaluation_date or date.today()).isoformat(),
        printed_json,
    )
    return _json_object(result, "profile validation")


def canonicalize_profile(document_type: str, document_data: dict[str, Any]) -> str:
    """Return the sole canonical JSON representation from Rust."""

    return str(
        _call(
            "vds_nc_canonicalize",
            document_type,
            json.dumps(document_data, ensure_ascii=False, separators=(",", ":")),
        )
    )


def barcode_policy(
    document_type: str,
    encoded_size: int,
    preferred_format: str | None = None,
) -> tuple[str, str]:
    """Return Rust's barcode-format and error-correction decision."""

    result = _call(
        "vds_nc_barcode_policy",
        document_type,
        encoded_size,
        preferred_format,
    )
    if not isinstance(result, tuple) or len(result) != 2:
        raise NativeOperationError(
            "Native VDS-NC barcode policy returned an invalid result"
        )
    return str(result[0]), str(result[1])


def select_barcode_format(
    encoded_size: int,
    error_correction: str,
    preferred_format: str | None = None,
) -> str:
    """Select a format in Rust with an explicit correction level."""

    return str(
        _call(
            "vds_nc_select_barcode_format",
            encoded_size,
            error_correction,
            preferred_format,
        )
    )
