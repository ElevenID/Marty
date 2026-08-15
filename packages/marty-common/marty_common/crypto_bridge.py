"""Fail-closed compatibility surface for Marty Rust cryptographic bindings.

This module intentionally contains no cryptographic implementation.  Existing
Python callers may continue importing their established names, but every
security-sensitive operation is delegated to one of the canonical native
extensions.  Retired APIs raise :class:`NativeOperationError` instead of
falling back to Python.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, NoReturn

from marty_common.native_backends import (
    NativeBackendError,  # noqa: F401
    NativeBackendUnavailable,  # noqa: F401
    NativeOperationError,
    load_native_backend,
)

_MARTY_RS_CAPABILITIES = (
    "BitstringStatusList",
    "TokenStatusList",
    "create_bitstring_credential_subject",
    "create_status_list_claim",
    "generate_did_key",
    "generate_p256_key",
    "oid4vci_sign_credential",
    "verify_mdoc_cbor",
    "verify_sd_jwt",
    "verify_vcdm_jwt",
)

_MARTY_VERIFICATION_CAPABILITIES = (
    "active_authentication_build_apdu",
    "active_authentication_generate_challenge",
    "active_authentication_parse_response",
    "active_authentication_verify",
    "ChainValidator",
    "NativeBacSession",
    "NativeEacChipAuthentication",
    "NativeEacSecureMessaging",
    "NativePaceSession",
    "ValidationConfig",
    "build_self_signed_certificate_with_key",
    "certificate_der_to_pem",
    "certificate_pem_to_der",
    "compute_check_digit",
    "compare_passport_hashes_json",
    "dtc_assemble_signature",
    "dtc_create",
    "dtc_prepare_signing",
    "dtc_sign",
    "dtc_verify",
    "eac_calculate_mac",
    "eac_certificate_fingerprint",
    "eac_serialize_certificate",
    "eac_sign_terminal_challenge",
    "eac_verify_certificate_signature",
    "ecdsa_p256_generate",
    "ecdsa_p384_generate",
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
    "generate_random_bytes",
    "get_certificate_info",
    "get_certificate_public_key",
    "hash_data",
    "iso9796_recover",
    "iso9796_scheme1_sign",
    "iso9796_verify",
    "load_certificate_der",
    "load_certificate_pem",
    "load_private_key_pem",
    "load_public_key_pem",
    "parse_master_list",
    "parse_mrz",
    "parse_sod",
    "pbkdf2_sha256",
    "raw_private_key_to_pkcs8",
    "raw_public_key_to_spki",
    "save_private_key_pem",
    "save_public_key_pem",
    "validate_check_digit",
    "verify_sod_data_group_hash",
    "verify_sod_signature",
)

_marty_rs = load_native_backend("_marty_rs", _MARTY_RS_CAPABILITIES)
_marty_verification = load_native_backend(
    "marty_verification",
    _MARTY_VERIFICATION_CAPABILITIES,
)

# These flags remain for source compatibility.  Import failure raises before a
# partially functional module can be observed, so an imported bridge is always
# fully native-backed.
_marty_rs_available = True
_marty_verification_available = True

_PROTECTED_EXPORTS = {
    "NativeBackendError",
    "NativeBackendUnavailable",
    "NativeOperationError",
    "load_native_backend",
}


def _export_public(module: Any) -> set[str]:
    exported: set[str] = set()
    for name in dir(module):
        if name.startswith("_") or name in _PROTECTED_EXPORTS:
            continue
        globals()[name] = getattr(module, name)
        exported.add(name)
    return exported


_VERIFICATION_EXPORTS = _export_public(_marty_verification)
_MARTY_RS_EXPORTS = _export_public(_marty_rs)


def sha256(data: bytes) -> bytes:
    """Hash bytes with SHA-256 in Rust."""

    return _marty_verification.hash_data("sha256", data)


def sha384(data: bytes) -> bytes:
    """Hash bytes with SHA-384 in Rust."""

    return _marty_verification.hash_data("sha384", data)


def sha512(data: bytes) -> bytes:
    """Hash bytes with SHA-512 in Rust."""

    return _marty_verification.hash_data("sha512", data)


class Encoding(StrEnum):
    """Serialization selector retained for compatibility adapters."""

    DER = "DER"
    PEM = "PEM"


class PublicFormat(StrEnum):
    """Only SPKI is supported by the native key conversion surface."""

    SubjectPublicKeyInfo = "SubjectPublicKeyInfo"


class ExtensionNotFound(LookupError):  # noqa: N818
    """Compatibility error for retired Python extension traversal."""


class SubjectAlternativeName:
    """Marker retained for import compatibility only."""


class DNSName:
    """Marker retained for import compatibility only."""


class UniformResourceIdentifier:
    """Marker retained for import compatibility only."""


class Certificate:
    """Minimal native-backed certificate compatibility adapter."""

    def __init__(self, der_data: bytes) -> None:
        self._der = bytes(der_data)
        _marty_verification.load_certificate_der(self._der)
        self._info = _marty_verification.get_certificate_info(self._der)

    @classmethod
    def from_der(cls, der_data: bytes) -> Certificate:
        return cls(der_data)

    @classmethod
    def from_pem(cls, pem_data: str | bytes) -> Certificate:
        if isinstance(pem_data, bytes):
            pem_data = pem_data.decode("ascii")
        return cls(_marty_verification.load_certificate_pem(pem_data))

    @property
    def subject(self) -> str:
        return str(self._info.get("subject", ""))

    @property
    def issuer(self) -> str:
        return str(self._info.get("issuer", ""))

    @property
    def serial_number(self) -> str:
        return str(self._info.get("serial_number", ""))

    @property
    def extensions(self) -> NoReturn:
        raise NativeOperationError(
            "Python certificate-extension traversal is retired; use native "
            "certificate metadata or a native verification operation"
        )

    def to_der(self) -> bytes:
        return self._der

    def public_bytes(self, encoding: Encoding) -> bytes:
        if encoding == Encoding.DER or str(encoding).upper().endswith("DER"):
            return self._der
        if encoding == Encoding.PEM or str(encoding).upper().endswith("PEM"):
            return _marty_verification.certificate_der_to_pem(self._der).encode("ascii")
        raise ValueError(f"Unsupported certificate encoding: {encoding}")

    def to_cryptography(self) -> NoReturn:
        raise NativeOperationError(
            "Conversion to a Python cryptography certificate is disabled; "
            "route the operation through marty-verification"
        )


def load_pem_x509_certificate(pem_data: str | bytes) -> Certificate:
    """Load a certificate through the native parser."""

    return Certificate.from_pem(pem_data)


class RSAPublicKeyBridge:
    """Serialization-compatible view of a Rust-validated RSA public key."""

    def __init__(self, modulus: int, public_exponent: int) -> None:
        from marty_common.emrtd_native import inspect_rsa_public_key, rsa_public_key_spki

        self._der = rsa_public_key_spki(modulus, public_exponent)
        info = inspect_rsa_public_key(self._der)
        self.key_size = int(info["key_size"])
        self._fingerprint_sha256 = str(info["fingerprint_sha256"])
        self._valid_for_active_authentication = bool(info["valid_for_active_authentication"])

    @classmethod
    def from_native_dg15(
        cls,
        *,
        spki_der: bytes,
        key_size: int,
        fingerprint_sha256: str,
        valid_for_active_authentication: bool,
    ) -> RSAPublicKeyBridge:
        """Build a view from metadata already validated by the Rust DG15 parser."""

        value = cls.__new__(cls)
        value._der = bytes(spki_der)
        value.key_size = key_size
        value._fingerprint_sha256 = fingerprint_sha256
        value._valid_for_active_authentication = valid_for_active_authentication
        return value

    def public_bytes(self, encoding: Any, format: Any = None) -> bytes:  # noqa: A002
        """Return the native canonical SubjectPublicKeyInfo encoding."""

        del format
        encoding_name = str(getattr(encoding, "name", encoding)).upper()
        if encoding_name.endswith("DER"):
            return self._der
        if encoding_name.endswith("PEM"):
            return _marty_verification.save_public_key_pem(self._der).encode("ascii")
        raise ValueError(f"Unsupported public-key encoding: {encoding}")

    @property
    def fingerprint_sha256(self) -> str | None:
        return self._fingerprint_sha256

    @property
    def valid_for_active_authentication(self) -> bool:
        return self._valid_for_active_authentication


CertificateChainValidator = _marty_verification.ChainValidator


def _unsupported(name: str):
    def operation(*_args: Any, **_kwargs: Any) -> NoReturn:
        raise NativeOperationError(
            f"{name} is not exposed by the canonical Marty Rust bindings; "
            "the former Python/provider fallback is disabled"
        )

    operation.__name__ = name
    operation.__qualname__ = name
    return operation


# Historical credential helpers and BBS operations are deliberately not
# emulated.  Canonical OID4VCI/verification entry points above replace them.
_RETIRED_OPERATIONS = (
    "bbs_create_proof",
    "bbs_sign",
    "bbs_verify",
    "bbs_verify_proof",
    "check_isomdl",
    "create_credential_offer",
    "create_presentation",
    "generate_bls12381_key",
    "generate_did_key",
    "generate_issuer_metadata",
    "generate_offer_uri",
    "generate_rsa_key",
    "get_ssi_version",
    "sum_as_string",
    "verify_certificate_chain",
    "verify_emrtd",
    "verify_jwt",
    "verify_mdl",
    "verify_mdoc",
)
for _name in _RETIRED_OPERATIONS:
    globals().setdefault(_name, _unsupported(_name))


def verify_open_badge_ob2(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(_marty_verification.open_badge_ob2_verify(json.dumps(payload)))


def verify_open_badge_ob3(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(_marty_verification.open_badge_ob3_verify(json.dumps(payload)))


def issue_open_badge_ob2(request: dict[str, Any]) -> dict[str, Any]:
    return json.loads(_marty_verification.open_badge_ob2_issue(json.dumps(request)))


def issue_open_badge_ob3(request: dict[str, Any]) -> dict[str, Any]:
    return json.loads(_marty_verification.open_badge_ob3_issue(json.dumps(request)))


def get_available_functions() -> dict[str, list[str]]:
    """Return the loaded native public surfaces for diagnostics."""

    return {
        "marty_rs": sorted(_MARTY_RS_EXPORTS),
        "marty_verification": sorted(_VERIFICATION_EXPORTS),
    }


def get_module_status() -> dict[str, bool]:
    """Return availability after strict import and capability validation."""

    return {"marty_rs": True, "marty_verification": True}


__all__ = sorted(
    _MARTY_RS_EXPORTS
    | _VERIFICATION_EXPORTS
    | set(_RETIRED_OPERATIONS)
    | {
        "Certificate",
        "CertificateChainValidator",
        "DNSName",
        "Encoding",
        "ExtensionNotFound",
        "NativeBackendError",
        "NativeBackendUnavailable",
        "NativeOperationError",
        "PublicFormat",
        "RSAPublicKeyBridge",
        "SubjectAlternativeName",
        "UniformResourceIdentifier",
        "get_available_functions",
        "get_module_status",
        "issue_open_badge_ob2",
        "issue_open_badge_ob3",
        "load_pem_x509_certificate",
        "sha256",
        "sha384",
        "sha512",
        "verify_open_badge_ob2",
        "verify_open_badge_ob3",
    }
)
