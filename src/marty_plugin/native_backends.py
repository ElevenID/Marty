"""Fail-closed loading and diagnostics for native Marty backends."""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from types import ModuleType
from typing import Any

REQUIRED_NATIVE_BACKENDS: dict[str, tuple[str, ...]] = {
    "marty_iso18013": (
        "BleTransport",
        "DeviceEngagement",
        "EngagementMethod",
        "MdlRequest",
        "MdlResponse",
        "NfcTransport",
        "ResponseStatus",
        "SelectiveDisclosure",
        "Session",
        "SessionConfig",
        "SessionState",
        "HttpsTransport",
        "TransportMethod",
    ),
    "marty_verification": (
        "ChainValidator",
        "CscaRegistry",
        "EudiRegistry",
        "IacaRegistry",
        "build_ocsp_request",
        "certificate_der_to_pem",
        "certificate_pem_to_der",
        "check_certificate_revocation",
        "crl_pem_to_der",
        "detect_public_key_type",
        "get_certificate_info",
        "get_certificate_public_key",
        "get_crl_distribution_points",
        "get_ocsp_responder_url",
        "hash_data",
        "load_certificate_der",
        "parse_crl",
        "parse_master_list",
        "parse_mrz",
        "parse_ocsp_response",
        "parse_sod",
        "verify_crl_signature",
        "verify_master_list_signature",
        "verify_sod_data_group_hash",
        "verify_sod_signature",
    ),
    "_marty_rs": (
        "BitstringStatusList",
        "TokenStatusList",
        "create_verifiable_credential",
        "generate_p256_key",
    ),
}

NATIVE_DISTRIBUTIONS = {
    "marty_iso18013": "marty-iso18013",
    "marty_verification": "marty-verification-py",
    "_marty_rs": "marty-rs",
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
                "version": _backend_version(name, module),
            }
    return result


def _backend_version(module_name: str, module: ModuleType) -> str:
    native_version = getattr(module, "__version__", None)
    if native_version:
        return str(native_version)
    version_function = getattr(module, "version", None)
    if callable(version_function):
        return str(version_function())
    try:
        return distribution_version(NATIVE_DISTRIBUTIONS[module_name])
    except PackageNotFoundError:
        return "unknown"
