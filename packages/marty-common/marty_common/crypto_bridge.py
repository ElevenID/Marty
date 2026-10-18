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
from marty_common.native_policy import (
    OPTIONAL_VERIFICATION_OPERATIONS,
    REQUIRED_NATIVE_BACKENDS,
    RETIRED_PRIVATE_OPERATIONS,
)
from marty_common.native_public_exports import PUBLIC_NATIVE_EXPORTS

_MARTY_RS_CAPABILITIES = REQUIRED_NATIVE_BACKENDS["_marty_rs"]
_MARTY_VERIFICATION_CAPABILITIES = REQUIRED_NATIVE_BACKENDS["marty_verification"]

_marty_rs = load_native_backend("_marty_rs", _MARTY_RS_CAPABILITIES)
_marty_verification = load_native_backend(
    "marty_verification",
    _MARTY_VERIFICATION_CAPABILITIES,
)

# These flags remain for source compatibility.  Import failure raises before a
# missing required public core can be observed. Optional session/password APIs
# are separately checked when called and are not implied by these flags.
_marty_rs_available = True
_marty_verification_available = True

_PROTECTED_EXPORTS = {
    "NativeBackendError",
    "NativeBackendUnavailable",
    "NativeOperationError",
    "load_native_backend",
}


def _export_public(module: Any, names: tuple[str, ...]) -> set[str]:
    exported: set[str] = set()
    for name in names:
        if name in _PROTECTED_EXPORTS or not hasattr(module, name):
            continue
        globals()[name] = getattr(module, name)
        exported.add(name)
    return exported


_VERIFICATION_EXPORTS = _export_public(
    _marty_verification,
    PUBLIC_NATIVE_EXPORTS["marty_verification"] + OPTIONAL_VERIFICATION_OPERATIONS,
)
_MARTY_RS_EXPORTS = _export_public(_marty_rs, PUBLIC_NATIVE_EXPORTS["_marty_rs"])


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
        if name in RETIRED_PRIVATE_OPERATIONS:
            raise NativeOperationError(
                f"{name} is retired from Python compatibility; "
                "use the Rust managed-KMS workflow for long-term keys and signing"
            )
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
for _name in RETIRED_PRIVATE_OPERATIONS:
    globals()[_name] = _unsupported(_name)


def _optional_native_operation(module_name: str, name: str):
    def operation(*args: Any, **kwargs: Any) -> Any:
        native = load_native_backend(module_name, (name,))
        return getattr(native, name)(*args, **kwargs)

    operation.__name__ = name
    return operation


for _module_name, _names in PUBLIC_NATIVE_EXPORTS.items():
    for _name in _names:
        globals().setdefault(_name, _optional_native_operation(_module_name, _name))
for _name in OPTIONAL_VERIFICATION_OPERATIONS:
    globals().setdefault(_name, _optional_native_operation("marty_verification", _name))


def verify_open_badge_ob2(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(_marty_verification.open_badge_ob2_verify(json.dumps(payload)))


def verify_open_badge_ob3(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(_marty_verification.open_badge_ob3_verify(json.dumps(payload)))


def issue_open_badge_ob2(request: dict[str, Any]) -> dict[str, Any]:
    raise NativeOperationError("Open Badge issuance requires the Rust managed-KMS issuer")


def issue_open_badge_ob3(request: dict[str, Any]) -> dict[str, Any]:
    raise NativeOperationError("Open Badge issuance requires the Rust managed-KMS issuer")


def get_available_functions() -> dict[str, list[str]]:
    """Return actual allowed native capabilities, excluding compatibility stubs."""

    return {
        "marty_rs": sorted(_MARTY_RS_EXPORTS),
        "marty_verification": sorted(_VERIFICATION_EXPORTS),
    }


def get_module_status() -> dict[str, bool]:
    """Return required public-core availability, not optional operation support."""

    return {"marty_rs": True, "marty_verification": True}


__all__ = sorted(
    _MARTY_RS_EXPORTS
    | _VERIFICATION_EXPORTS
    | set(_RETIRED_OPERATIONS)
    | set(RETIRED_PRIVATE_OPERATIONS)
    | set(OPTIONAL_VERIFICATION_OPERATIONS)
    | set().union(*PUBLIC_NATIVE_EXPORTS.values())
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
        "build_self_signed_certificate_with_key",
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
