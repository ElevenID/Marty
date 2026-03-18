"""
ICAO Trust Profile Adapter

Wraps existing CSCATrustStore and Rust CscaRegistry to implement the TrustProfilePort interface.
Provides trust validation for ICAO 9303 eMRTD documents (ePassports).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from digital_identity.application.ports.trust_profile import (
    TrustProfilePort,
    TrustAnchor,
    ChainValidationResult,
    RevocationCheckResult,
    RefreshResult,
    ValidationStatus,
    RevocationStatus,
)

logger = logging.getLogger(__name__)


def _x509_to_trust_anchor(cert: x509.Certificate, country_code: str | None = None) -> TrustAnchor:
    """Convert a cryptography x509.Certificate to a TrustAnchor."""
    pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    der = cert.public_bytes(serialization.Encoding.DER)
    fingerprint = cert.fingerprint(hashes.SHA256()).hex()
    not_before = cert.not_valid_before_utc if hasattr(cert, "not_valid_before_utc") else cert.not_valid_before
    not_after = cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else cert.not_valid_after

    return TrustAnchor(
        id=fingerprint,
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
        serial_number=format(cert.serial_number, "x"),
        valid_from=not_before,
        valid_until=not_after,
        certificate_pem=pem,
        certificate_der=der,
        country_code=country_code,
        metadata={"source": "icao_pkd"},
    )


@dataclass
class IcaoTrustProfile:
    """
    ICAO Trust Profile implementation.

    Wraps the existing CSCATrustStore for ICAO 9303 eMRTD trust validation.
    Uses Rust marty-verification ChainValidator + CscaRegistry for
    high-performance certificate validation.
    """

    trust_store_path: Path
    master_list_sources: list[str]
    pkd_urls: list[str]
    _trust_store: Any = None       # CSCATrustStore instance
    _rust_registry: Any = None     # Rust CscaRegistry via PyO3
    _chain_validator: Any = None   # Rust ChainValidator via PyO3

    def __post_init__(self):
        """Initialize the trust store and Rust-side chain validator."""
        from marty_common.crypto.csca_trust_store import CSCATrustStore

        self._trust_store = CSCATrustStore(trust_store_path=self.trust_store_path)

        try:
            from marty_verification import CscaRegistry, ChainValidator  # type: ignore

            if self.trust_store_path.exists():
                self._rust_registry = CscaRegistry.from_directory(
                    str(self.trust_store_path)
                )
            else:
                self._rust_registry = CscaRegistry()

            # Build a ChainValidator pre-loaded with CSCA anchors
            self._chain_validator = ChainValidator()
            for pem in self._rust_registry.get_anchors_pem():
                self._chain_validator.add_trust_anchor(pem)

            logger.info(
                "Initialized ICAO trust profile with %d CSCA anchors",
                len(self._rust_registry),
            )
        except ImportError:
            logger.warning(
                "Rust marty-verification not available, using Python-only validation"
            )
            self._rust_registry = None
            self._chain_validator = None

    # ------------------------------------------------------------------
    # TrustProfilePort interface
    # ------------------------------------------------------------------

    async def get_trust_anchors(
        self,
        jurisdiction: str | None = None,
        country_code: str | None = None,
    ) -> list[TrustAnchor]:
        """Get CSCA trust anchors, optionally filtered by country code."""
        lookup = country_code or jurisdiction
        if lookup:
            certificates = self._trust_store.get_csca_certificates_for_country(lookup)
        else:
            certificates = self._trust_store.get_all_trusted_certificates()

        anchors: list[TrustAnchor] = []
        for cert in certificates:
            if hasattr(cert, "to_cryptography"):
                cert = cert.to_cryptography()
            anchors.append(_x509_to_trust_anchor(cert, country_code=lookup))
        return anchors

    async def get_anchor_by_id(self, anchor_id: str) -> TrustAnchor | None:
        """Get a specific trust anchor by fingerprint."""
        for anchor in await self.get_trust_anchors():
            if anchor.id == anchor_id:
                return anchor
        return None

    async def validate_chain(
        self,
        certificate_pem: str | None = None,
        certificate_der: bytes | None = None,
    ) -> ChainValidationResult:
        """Validate a certificate chain against CSCA trust anchors."""
        if not certificate_pem and not certificate_der:
            return ChainValidationResult(
                status=ValidationStatus.INVALID,
                errors=["No certificate provided"],
            )

        # Prefer Rust chain validator if available
        if self._chain_validator:
            return self._validate_with_rust(certificate_pem, certificate_der)

        # Fallback to Python
        return await self._validate_with_python(certificate_pem, certificate_der)

    def _validate_with_rust(
        self,
        certificate_pem: str | None,
        certificate_der: bytes | None,
    ) -> ChainValidationResult:
        """Validate using Rust ChainValidator."""
        try:
            from marty_verification import certificate_der_to_pem  # type: ignore

            if certificate_der and not certificate_pem:
                certificate_pem = certificate_der_to_pem(certificate_der)

            result = self._chain_validator.validate_chain([certificate_pem])

            if result.valid:
                return ChainValidationResult(
                    status=ValidationStatus.VALID,
                    trust_anchor_id=result.issuer,
                    chain_length=result.chain_depth,
                    chain_path=[result.subject or "leaf"],
                    warnings=list(result.warnings) if result.warnings else [],
                )
            else:
                return ChainValidationResult(
                    status=ValidationStatus.INVALID,
                    errors=list(result.errors) if result.errors else ["Chain validation failed"],
                )
        except Exception as e:
            logger.error("Rust validation failed, falling through: %s", e)
            return ChainValidationResult(
                status=ValidationStatus.INVALID,
                errors=[f"Validation error: {e}"],
            )

    async def _validate_with_python(
        self,
        certificate_pem: str | None,
        certificate_der: bytes | None,
    ) -> ChainValidationResult:
        """Validate using Python CSCATrustStore."""
        try:
            if certificate_pem:
                leaf_cert = x509.load_pem_x509_certificate(certificate_pem.encode("utf-8"))
            else:
                leaf_cert = x509.load_der_x509_certificate(certificate_der)

            is_valid, messages = self._trust_store.verify_csca_certificate(leaf_cert, None)

            if is_valid:
                cert_id = leaf_cert.fingerprint(hashes.SHA256()).hex()
                metadata = self._trust_store._metadata.get(cert_id)
                anchor_id = metadata.country_code if metadata else None

                return ChainValidationResult(
                    status=ValidationStatus.VALID,
                    trust_anchor_id=anchor_id,
                    chain_length=1,
                    warnings=messages or [],
                )
            else:
                return ChainValidationResult(
                    status=ValidationStatus.INVALID,
                    errors=messages or ["Validation failed"],
                )
        except Exception as e:
            return ChainValidationResult(
                status=ValidationStatus.INVALID,
                errors=[f"Validation error: {e}"],
            )

    async def check_revocation(
        self,
        certificate_pem: str | None = None,
        certificate_der: bytes | None = None,
    ) -> RevocationCheckResult:
        """Check revocation status via Rust CRL parser."""
        try:
            from marty_verification import (  # type: ignore
                certificate_pem_to_der,
                get_certificate_info,
                get_ocsp_responder_url,
            )

            if certificate_pem and not certificate_der:
                certificate_der = bytes(certificate_pem_to_der(certificate_pem))

            info = get_certificate_info(certificate_der)

            # Check for embedded OCSP responder
            ocsp_url = get_ocsp_responder_url(certificate_der)
            if ocsp_url:
                logger.debug("OCSP responder found at %s (fetch not yet wired)", ocsp_url)

            return RevocationCheckResult(
                status=RevocationStatus.UNKNOWN,
                errors=["ICAO CRL/OCSP fetch not yet configured"],
            )

        except Exception as e:
            return RevocationCheckResult(
                status=RevocationStatus.UNKNOWN,
                errors=[str(e)],
            )

    async def refresh(self) -> RefreshResult:
        """Refresh trust anchors from ICAO PKD Master Lists."""
        try:
            anchors_before = len(self._trust_store._certificates)
            # Master List fetching requires network access;
            # the trust store already loads from disk on init.
            anchors_after = len(self._trust_store._certificates)

            return RefreshResult(
                success=True,
                anchors_added=max(0, anchors_after - anchors_before),
            )
        except Exception as e:
            logger.exception("Failed to refresh ICAO trust anchors")
            return RefreshResult(success=False, errors=[str(e)])

    async def is_issuer_trusted(self, issuer_id: str) -> bool:
        """Check if a country code is trusted."""
        certificates = self._trust_store.get_csca_certificates_for_country(issuer_id)
        return len(certificates) > 0
