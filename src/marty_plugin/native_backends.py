"""Fail-closed loading and diagnostics for native Marty backends."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any

REQUIRED_NATIVE_BACKENDS: dict[str, tuple[str, ...]] = {
    "marty_iso18013": (
        "BleTransport",
        "DeviceEngagement",
        "MdlRequest",
        "MdlResponse",
        "NfcTransport",
        "SelectiveDisclosure",
        "Session",
        "HttpsTransport",
    ),
    "marty_verification": (
        "ChainValidator",
        "parse_sod",
        "verify_sod_data_group_hash",
        "parse_master_list",
        "verify_master_list_signature",
        "parse_crl",
        "verify_crl_signature",
        "build_ocsp_request",
        "parse_ocsp_response",
    ),
    "_marty_rs": (
        "BitstringStatusList",
        "TokenStatusList",
        "create_verifiable_credential",
        "generate_p256_key",
    ),
}


class NativeBackendError(RuntimeError):
    """Base error for unavailable or unusable native Marty backends."""


class NativeBackendUnavailable(NativeBackendError):
    """Raised when a required Rust extension cannot be imported."""


class NativeOperationError(NativeBackendError):
    """Raised when a native operation fails."""


def require_backend(module_name: str) -> ModuleType:
    """Load a required native module without falling back to Python code."""

    try:
        module = import_module(module_name)
    except (ImportError, ModuleNotFoundError) as exc:
        raise NativeBackendUnavailable(
            f"Required native backend {module_name!r} is unavailable. "
            "Install the corresponding Rust extension before starting this service."
        ) from exc
    missing = [
        capability
        for capability in REQUIRED_NATIVE_BACKENDS.get(module_name, ())
        if not hasattr(module, capability)
    ]
    if missing:
        raise NativeBackendUnavailable(
            f"Required native backend {module_name!r} is incompatible; missing: "
            f"{', '.join(missing)}. Install matching Marty native wheels."
        )
    return module


def require_native_backends() -> dict[str, ModuleType]:
    """Load every production-required native backend or raise a typed error."""
    loaded: dict[str, ModuleType] = {}
    errors: list[str] = []
    for name in REQUIRED_NATIVE_BACKENDS:
        try:
            loaded[name] = require_backend(name)
        except NativeBackendUnavailable as exc:
            errors.append(str(exc))
    if errors:
        raise NativeBackendUnavailable("; ".join(errors))
    return loaded


def backend_diagnostics() -> dict[str, Any]:
    """Return native backend availability for health checks and diagnostics."""

    result: dict[str, Any] = {}
    for name in REQUIRED_NATIVE_BACKENDS:
        try:
            module = require_backend(name)
        except NativeBackendUnavailable as exc:
            result[name] = {"available": False, "error": str(exc)}
        else:
            result[name] = {
                "available": True,
                "version": getattr(module, "__version__", "unknown"),
            }
    return result
