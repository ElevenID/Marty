"""Retired legacy VDS-NC cryptography compatibility surface.

Canonical VDS-NC models use :mod:`marty_common.crypto_bridge` for native
signature verification.  This older API accepted live ``cryptography`` key
objects and generated development keys at runtime, so it cannot be preserved
without reintroducing a Python cryptographic fallback.
"""

from __future__ import annotations

from typing import Any, NoReturn

from marty_common.models.passport import CMCCertificate, VDSNCBarcode
from marty_common.native_backends import NativeOperationError


def _retired(operation: str) -> NoReturn:
    raise NativeOperationError(
        f"Legacy VDS-NC {operation} is disabled; use the canonical VDS-NC "
        "processor with native Marty key and signature bindings"
    )


class VDSNCGenerator:
    """Compatibility type that rejects Python key-object signing."""

    def __init__(self, signing_key: Any, certificate_reference: str) -> None:
        del signing_key, certificate_reference
        _retired("generation")

    def generate_vds_nc_barcode(
        self,
        cmc_certificate: CMCCertificate,
        signature_algorithm: str = "ES256",
    ) -> VDSNCBarcode:
        del cmc_certificate, signature_algorithm
        _retired("generation")


class VDSNCVerifier:
    """Compatibility type that never accepts a structure-only barcode."""

    def __init__(self, public_keys: dict[str, Any]) -> None:
        del public_keys
        _retired("verification")

    def verify_vds_nc_barcode(
        self,
        barcode_data: str,
    ) -> tuple[bool, CMCCertificate | None, list[str]]:
        del barcode_data
        return False, None, ["Legacy VDS-NC verification is disabled"]


def generate_test_key_pair() -> NoReturn:
    """Reject runtime development-key generation in production code."""

    _retired("test-key generation")


def export_public_key_pem(public_key: Any) -> NoReturn:
    del public_key
    _retired("Python public-key export")


def load_public_key_pem(pem_data: str) -> NoReturn:
    del pem_data
    _retired("Python public-key loading")


__all__ = [
    "VDSNCGenerator",
    "VDSNCVerifier",
    "export_public_key_pem",
    "generate_test_key_pair",
    "load_public_key_pem",
]
