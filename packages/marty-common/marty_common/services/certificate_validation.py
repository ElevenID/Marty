"""Native fail-closed certificate and SOD trust validation service."""

from __future__ import annotations

import logging
from pathlib import Path

from marty_common.crypto.certificate_validator import CertificateChainValidator
from marty_common.crypto.sod_parser import parse_sod
from marty_common.crypto.sod_signer import verify_sod_signature

logger = logging.getLogger(__name__)


class CertificateValidationError(Exception):
    """Raised when certificate validation cannot be configured safely."""


class CertificateValidationService:
    """Validate certificate chains and eMRTD SODs using Rust."""

    def __init__(self, certificate_directory: Path | None = None) -> None:
        self.certificate_directory = certificate_directory or Path("data/csca")

    def validate_certificate_chain(
        self,
        certificate_data: bytes,
        trust_roots: list[bytes] | None = None,
    ) -> bool:
        roots = trust_roots if trust_roots is not None else self.load_trust_roots()
        if not roots:
            logger.warning("Certificate validation has no CSCA trust anchors")
            return False
        try:
            validator = CertificateChainValidator(roots)
            return validator.validate_certificate_chain(certificate_data).is_valid
        except Exception:
            logger.exception("Native certificate-chain validation failed closed")
            return False

    def validate_sod_certificate(self, sod_data: str | bytes) -> bool:
        roots = self.load_trust_roots()
        if not roots:
            logger.warning("SOD validation has no CSCA trust anchors")
            return False
        try:
            sod = parse_sod(sod_data)
            return verify_sod_signature(sod.der, roots)
        except Exception:
            logger.exception("Native SOD trust validation failed closed")
            return False

    def load_trust_roots(self, directory: Path | None = None) -> list[bytes]:
        cert_dir = directory or self.certificate_directory
        if not cert_dir.is_dir():
            return []
        roots: list[bytes] = []
        for pattern in ("*.crt", "*.cer", "*.pem"):
            for certificate in cert_dir.glob(pattern):
                try:
                    roots.append(certificate.read_bytes())
                except OSError as exc:
                    logger.warning("Failed to read trust anchor %s: %s", certificate, exc)
        return roots


MacOSCompatibleCertValidator = CertificateValidationService

_global_validator: CertificateValidationService | None = None


def get_certificate_validator() -> CertificateValidationService:
    global _global_validator
    if _global_validator is None:
        _global_validator = CertificateValidationService()
    return _global_validator


def validate_certificate(
    certificate_data: bytes,
    trust_roots: list[bytes] | None = None,
) -> bool:
    return get_certificate_validator().validate_certificate_chain(
        certificate_data,
        trust_roots,
    )


def validate_sod_certificate(sod_data: str | bytes) -> bool:
    return get_certificate_validator().validate_sod_certificate(sod_data)


__all__ = [
    "CertificateValidationError",
    "CertificateValidationService",
    "MacOSCompatibleCertValidator",
    "get_certificate_validator",
    "validate_certificate",
    "validate_sod_certificate",
]
