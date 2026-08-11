"""Fail-closed loading and diagnostics for native Marty backends."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from types import ModuleType
from typing import Any

from marty_common.native_backends import (
    NativeBackendError,
    NativeBackendUnavailable,
    NativeOperationError,
    load_native_backend,
)

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
        "build_self_signed_certificate_with_key",
        "certificate_der_to_pem",
        "certificate_pem_to_der",
        "crl_pem_to_der",
        "detect_public_key_type",
        "dtc_create",
        "dtc_sign",
        "dtc_verify",
        "ecdsa_p256_generate",
        "ecdsa_p384_generate",
        "generate_random_bytes",
        "get_certificate_info",
        "get_certificate_public_key",
        "get_crl_distribution_points",
        "get_ocsp_responder_url",
        "hash_data",
        "load_certificate_der",
        "load_private_key_pem",
        "load_public_key_pem",
        "parse_crl",
        "parse_master_list",
        "parse_mrz",
        "validate_ocsp_response",
        "parse_sod",
        "raw_private_key_to_pkcs8",
        "raw_public_key_to_spki",
        "save_private_key_pem",
        "save_public_key_pem",
        "validate_crl",
        "validate_crl_for_certificate",
        "verify_emrtd",
        "verify_master_list_signature",
        "verify_sod_data_group_hash",
        "verify_sod_signature",
    ),
    "_marty_rs": (
        "BitstringStatusList",
        "TokenStatusList",
        "create_bitstring_credential_subject",
        "create_status_list_claim",
        "create_verifiable_credential",
        "generate_did_key",
        "generate_p256_key",
        "oid4vci_sign_credential",
        "sha256",
        "verify_mdoc_cbor",
        "verify_sd_jwt",
        "verify_vcdm_jwt",
        "vds_nc_barcode_policy",
        "vds_nc_canonicalize",
        "vds_nc_inspect",
        "vds_nc_select_barcode_format",
        "vds_nc_sign_profile",
        "vds_nc_validate_profile",
        "vds_nc_verify_profile",
    ),
}

NATIVE_DISTRIBUTIONS = {
    "marty_iso18013": "marty-iso18013",
    "marty_verification": "marty-verification-py",
    "_marty_rs": "marty-rs",
}


def require_backend(module_name: str) -> ModuleType:
    """Load a required native module without falling back to Python code."""

    return load_native_backend(
        module_name,
        REQUIRED_NATIVE_BACKENDS.get(module_name, ()),
    )


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
