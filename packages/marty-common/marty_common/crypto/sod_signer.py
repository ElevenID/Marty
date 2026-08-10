"""Fail-closed SOD compatibility APIs backed by native verification."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from marty_common.crypto.sod_parser import NativeSOD, parse_sod
from marty_common.native_backends import NativeOperationError, load_native_backend


def _native():
    return load_native_backend(
        "marty_verification",
        (
            "ChainValidator",
            "certificate_pem_to_der",
            "parse_sod",
            "verify_sod_signature",
        ),
    )


def _certificate_der(native: Any, certificate: Any) -> bytes:
    if isinstance(certificate, bytes):
        if certificate.lstrip().startswith(b"-----BEGIN"):
            return bytes(native.certificate_pem_to_der(certificate.decode("ascii")))
        return certificate
    if isinstance(certificate, str):
        return bytes(native.certificate_pem_to_der(certificate))
    value = getattr(certificate, "certificate_data", None)
    if value is not None:
        return _certificate_der(native, value)
    raise NativeOperationError("Native SOD trust validation requires DER or PEM trust anchors")


def build_lds_security_object(
    data_group_hashes: Mapping[int, bytes],
    hash_algorithm: Any,
) -> Any:
    """Reject the retired Python ASN.1 construction path."""

    del data_group_hashes, hash_algorithm
    raise NativeOperationError("SOD construction requires the native issuance service")


def create_sod(
    data_group_hashes: Mapping[int, bytes],
    private_key: Any,
    certificate: Any,
    hash_algorithm: Any | None = None,
) -> bytes:
    """Reject Python key handling and CMS signing."""

    del data_group_hashes, private_key, certificate, hash_algorithm
    raise NativeOperationError("SOD signing requires the native or remote document-signer service")


def verify_sod_signature(
    sod_bytes: bytes,
    trusted_certificates: Sequence[Any] | None = None,
) -> bool:
    """Verify the SOD signature and DSC chain using Rust."""

    if not trusted_certificates:
        return False
    native = _native()
    try:
        if not native.verify_sod_signature(sod_bytes):
            return False
        metadata = native.parse_sod(sod_bytes)
        signer_pem = metadata.get("document_signer_cert")
        if not signer_pem:
            return False
        validator = native.ChainValidator()
        for certificate in trusted_certificates:
            validator.add_trust_anchor_der(_certificate_der(native, certificate))
        return bool(validator.validate_certificate(signer_pem).valid)
    except NativeOperationError:
        raise
    except Exception:
        return False


def load_sod(sod_bytes: bytes) -> NativeSOD:
    """Parse an SOD with the native implementation."""

    return parse_sod(sod_bytes)


__all__ = [
    "build_lds_security_object",
    "create_sod",
    "load_sod",
    "verify_sod_signature",
]
