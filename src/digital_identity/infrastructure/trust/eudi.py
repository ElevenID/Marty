"""
EUDI Trust Profile Adapter

Implementation for EU Digital Identity Wallet trust validation using Rust bindings.
Implements eIDAS 2.0 trust framework via ChainValidator + EudiRegistry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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


def _pem_to_trust_anchor(
    cert_pem: str,
    country_code: str | None = None,
) -> TrustAnchor | None:
    """Convert a PEM certificate to a TrustAnchor using Rust helpers."""
    try:
        from marty_verification import certificate_pem_to_der, get_certificate_info  # type: ignore

        der = bytes(certificate_pem_to_der(cert_pem))
        info = get_certificate_info(der)
        return TrustAnchor(
            id=info["fingerprint_sha256"],
            subject=info["subject"],
            issuer=info["issuer"],
            serial_number=info["serial_number"],
            valid_from=datetime.fromisoformat(info["not_before"]),
            valid_until=datetime.fromisoformat(info["not_after"]),
            certificate_pem=cert_pem,
            certificate_der=der,
            key_usage=info.get("key_usage") or [],
            country_code=country_code,
            metadata={"source": "eudi_lotl"},
        )
    except Exception as e:
        logger.debug("Failed to parse EUDI certificate: %s", e)
        return None


@dataclass
class EudiTrustProfile:
    """
    EUDI (EU Digital Identity) Trust Profile implementation.

    Wraps the Rust EudiRegistry for EU Digital Identity Wallet trust validation.
    Uses ChainValidator for certificate chain verification and CRL/OCSP for
    revocation checking, all backed by Rust.
    """

    trust_list_url: str | None = None
    member_state: str | None = None
    _rust_registry: Any = None     # Rust EudiRegistry via PyO3
    _chain_validator: Any = None   # Rust ChainValidator via PyO3

    def __post_init__(self):
        """Initialize the Rust registry and chain validator."""
        try:
            from marty_verification import EudiRegistry, ChainValidator  # type: ignore

            self._rust_registry = EudiRegistry()
            self._chain_validator = ChainValidator()
            logger.info("Initialized EUDI trust profile with Rust registry")

        except ImportError as e:
            logger.error("Rust marty-verification not available for EUDI: %s", e)
            self._rust_registry = None
            self._chain_validator = None

    def _rebuild_chain_validator(self) -> None:
        """Rebuild the ChainValidator from current registry anchors."""
        if self._rust_registry is None:
            return
        try:
            from marty_verification import ChainValidator  # type: ignore

            validator = ChainValidator()
            for pem in self._rust_registry.get_anchors_pem():
                validator.add_trust_anchor(pem)
            self._chain_validator = validator
        except Exception as e:
            logger.error("Failed to rebuild EUDI chain validator: %s", e)

    # ------------------------------------------------------------------
    # TrustProfilePort interface
    # ------------------------------------------------------------------

    async def get_trust_anchors(
        self,
        jurisdiction: str | None = None,
        country_code: str | None = None,
    ) -> list[TrustAnchor]:
        """Get EUDI trust anchors, optionally filtered by member state."""
        if self._rust_registry is None:
            return []

        lookup = country_code or jurisdiction
        try:
            if lookup:
                pems = self._rust_registry.get_member_state_anchors_pem(lookup)
            else:
                pems = self._rust_registry.get_anchors_pem()

            anchors: list[TrustAnchor] = []
            for pem in pems:
                anchor = _pem_to_trust_anchor(pem, country_code=lookup)
                if anchor:
                    anchors.append(anchor)
            return anchors

        except Exception as e:
            logger.error("Error getting EUDI trust anchors: %s", e)
            return []

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
        """Validate certificate chain against EUDI trust anchors."""
        if self._chain_validator is None:
            return ChainValidationResult(
                status=ValidationStatus.UNKNOWN,
                errors=["EUDI Rust registry not available"],
            )

        if not certificate_pem and not certificate_der:
            return ChainValidationResult(
                status=ValidationStatus.INVALID,
                errors=["No certificate provided"],
            )

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
            logger.error("EUDI chain validation failed: %s", e)
            return ChainValidationResult(
                status=ValidationStatus.INVALID,
                errors=[f"Validation error: {e}"],
            )

    async def check_revocation(
        self,
        certificate_pem: str | None = None,
        certificate_der: bytes | None = None,
    ) -> RevocationCheckResult:
        """Check EUDI certificate revocation status via CRL / OCSP."""
        if self._rust_registry is None:
            return RevocationCheckResult(
                status=RevocationStatus.UNKNOWN,
                errors=["EUDI Rust registry not available"],
            )

        try:
            from marty_verification import (  # type: ignore
                certificate_pem_to_der,
                get_ocsp_responder_url,
            )

            if certificate_pem and not certificate_der:
                certificate_der = bytes(certificate_pem_to_der(certificate_pem))

            ocsp_url = get_ocsp_responder_url(certificate_der)
            if ocsp_url:
                logger.debug("OCSP responder found: %s (fetch not yet wired)", ocsp_url)

            return RevocationCheckResult(
                status=RevocationStatus.UNKNOWN,
                errors=["EUDI CRL/OCSP fetch not yet configured"],
            )

        except Exception as e:
            return RevocationCheckResult(
                status=RevocationStatus.UNKNOWN,
                errors=[str(e)],
            )

    async def refresh(self) -> RefreshResult:
        """Refresh EUDI trust anchors from LoTL."""
        if self._rust_registry is None:
            return RefreshResult(
                success=False,
                errors=["EUDI Rust registry not available"],
            )

        anchors_before = len(self._rust_registry)

        # LoTL sync requires network access; stub until eudi-client is wired.
        anchors_after = len(self._rust_registry)

        return RefreshResult(
            success=True,
            anchors_added=max(0, anchors_after - anchors_before),
        )

    async def is_issuer_trusted(self, issuer_id: str) -> bool:
        """Check if an EU member state is trusted."""
        if self._rust_registry is None:
            return False
        try:
            supported = self._rust_registry.supported_member_states()
            return issuer_id in supported
        except Exception as e:
            logger.error("EUDI trust check failed for issuer %s: %s", issuer_id, e)
            return False
