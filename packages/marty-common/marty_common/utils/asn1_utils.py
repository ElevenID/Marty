"""Native-backed certificate and ASN.1 compatibility utilities.

Generic ASN.1 object decoding and CMS traversal are intentionally retired.
Callers must select a format-specific Rust parser so untrusted data cannot be
accepted through a permissive Python decoder.
"""

from __future__ import annotations

from typing import Any, NoReturn

from marty_common.native_backends import NativeOperationError, load_native_backend


def _native():
    return load_native_backend(
        "marty_verification",
        (
            "certificate_der_to_pem",
            "certificate_pem_to_der",
            "get_certificate_info",
            "load_certificate_der",
        ),
    )


def decode_der(data: bytes) -> NoReturn:
    del data
    raise NativeOperationError(
        "Generic ASN.1 decoding is retired; use the native certificate, SOD, master-list, or CRL parser"
    )


def encode_der(asn1_obj: Any) -> NoReturn:
    del asn1_obj
    raise NativeOperationError("Generic Python ASN.1 encoding is retired; use a format-specific native encoder")


def is_pem(data: bytes) -> bool:
    """Return whether bytes have an ASCII PEM envelope."""

    return bytes(data).lstrip().startswith(b"-----BEGIN ")


def pem_to_der(pem_data: bytes) -> bytes:
    """Convert an X.509 certificate PEM through the Rust parser."""

    try:
        text = bytes(pem_data).decode("ascii")
    except UnicodeDecodeError as exc:
        raise NativeOperationError("PEM input must be ASCII") from exc
    if "-----BEGIN CERTIFICATE-----" not in text:
        raise NativeOperationError("Generic PEM conversion is retired; use the native format-specific parser")
    return bytes(_native().certificate_pem_to_der(text))


def der_to_pem(der_data: bytes, pem_type: str = "CERTIFICATE") -> bytes:
    """Convert an X.509 certificate DER through the Rust parser."""

    if pem_type != "CERTIFICATE":
        raise NativeOperationError("Generic DER conversion is retired; use the native format-specific encoder")
    native = _native()
    native.load_certificate_der(bytes(der_data))
    return native.certificate_der_to_pem(bytes(der_data)).encode("ascii")


def extract_signed_data(cms_data: bytes) -> NoReturn:
    del cms_data
    raise NativeOperationError("Generic CMS traversal is retired; use native SOD or master-list parsing")


def extract_certificate_info(cert_data: bytes) -> dict[str, Any]:
    """Return normalized native X.509 metadata."""

    native = _native()
    der_data = pem_to_der(cert_data) if is_pem(cert_data) else bytes(cert_data)
    native.load_certificate_der(der_data)
    result = dict(native.get_certificate_info(der_data))
    result["pem"] = native.certificate_der_to_pem(der_data)
    return result


def verify_cms_signature(cms_data: bytes, cert_data: bytes | None = None) -> NoReturn:
    del cms_data, cert_data
    raise NativeOperationError(
        "Generic CMS verification is not exposed by the canonical native API; "
        "use native SOD, master-list, CRL, or format-specific verification"
    )


__all__ = [
    "decode_der",
    "der_to_pem",
    "encode_der",
    "extract_certificate_info",
    "extract_signed_data",
    "is_pem",
    "pem_to_der",
    "verify_cms_signature",
]
