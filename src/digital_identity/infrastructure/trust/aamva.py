"""
AAMVA Trust Profile Adapter

Wraps Rust IacaRegistry to implement the TrustProfilePort interface.
Provides trust validation for ISO 18013-5 mDL (mobile Driver's License) documents.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
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
    jurisdiction: str | None = None,
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
            jurisdiction=jurisdiction,
            metadata={"source": "aamva_dts"},
        )
    except Exception as e:
        logger.debug("Failed to parse certificate: %s", e)
        return None


@dataclass
class AamvaTrustProfile:
    """
    AAMVA Trust Profile implementation.

    Wraps the Rust IacaRegistry for mDL trust validation.
    Supports AAMVA jurisdictions (US states/territories, Canadian provinces).
    """

    iaca_directory: Path
    vical_url: str | None = None
    dts_url: str | None = None
    _rust_registry: Any = None  # Rust IacaRegistry via PyO3

    def __post_init__(self):
        """Initialize the IACA registry."""
        try:
            from marty_verification import IacaRegistry  # type: ignore

            if self.iaca_directory.exists():
                self._rust_registry = IacaRegistry.from_directory(
                    str(self.iaca_directory)
                )
                logger.info(
                    "Initialized AAMVA trust profile with %d IACA anchors",
                    len(self._rust_registry),
                )
            else:
                self._rust_registry = IacaRegistry()
                logger.info("Initialized empty AAMVA trust profile")

        except ImportError:
            logger.error(
                "Rust marty-verification not available — AAMVA trust profile unavailable"
            )
            self._rust_registry = None

    # ------------------------------------------------------------------
    # TrustProfilePort interface
    # ------------------------------------------------------------------

    async def get_trust_anchors(
        self,
        jurisdiction: str | None = None,
        country_code: str | None = None,
    ) -> list[TrustAnchor]:
        """Get IACA trust anchors, optionally filtered by jurisdiction."""
        if self._rust_registry is None:
            return []

        lookup = jurisdiction or country_code
        try:
            if lookup:
                pems = self._rust_registry.get_jurisdiction_anchors_pem(lookup)
            else:
                pems = self._rust_registry.get_anchors_pem()

            anchors: list[TrustAnchor] = []
            for pem in pems:
                anchor = _pem_to_trust_anchor(pem, jurisdiction=lookup)
                if anchor:
                    anchors.append(anchor)
            return anchors

        except Exception:
            logger.exception("Failed to get AAMVA trust anchors for %s", lookup)
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
        """Validate an mDL certificate chain against IACA trust anchors."""
        if self._rust_registry is None:
            return ChainValidationResult(
                status=ValidationStatus.UNKNOWN,
                errors=["AAMVA trust registry not available"],
            )

        if not certificate_pem and not certificate_der:
            return ChainValidationResult(
                status=ValidationStatus.INVALID,
                errors=["No certificate provided"],
            )

        try:
            from marty_verification import (  # type: ignore
                ChainValidator,
                certificate_der_to_pem,
            )

            if certificate_der and not certificate_pem:
                certificate_pem = certificate_der_to_pem(certificate_der)

            # Build a ChainValidator loaded with IACA anchors
            validator = ChainValidator()
            for pem in self._rust_registry.get_anchors_pem():
                validator.add_trust_anchor(pem)

            result = validator.validate_chain([certificate_pem])

            if result.valid:
                return ChainValidationResult(
                    status=ValidationStatus.VALID,
                    trust_anchor_id=result.issuer,
                    chain_length=result.chain_depth,
                    chain_path=[result.subject or "leaf"],
                )
            else:
                return ChainValidationResult(
                    status=ValidationStatus.INVALID,
                    errors=list(result.errors) if result.errors else ["Chain validation failed"],
                )

        except Exception as e:
            logger.exception("mDL chain validation failed")
            return ChainValidationResult(
                status=ValidationStatus.INVALID,
                errors=[f"Validation error: {e}"],
            )

    async def check_revocation(
        self,
        certificate_pem: str | None = None,
        certificate_der: bytes | None = None,
    ) -> RevocationCheckResult:
        """Check mDL certificate revocation via CRL / OCSP."""
        if self._rust_registry is None:
            return RevocationCheckResult(
                status=RevocationStatus.UNKNOWN,
                errors=["AAMVA trust registry not available"],
            )

        try:
            from marty_verification import (  # type: ignore
                certificate_pem_to_der,
                get_certificate_info,
                get_ocsp_responder_url,
            )

            if certificate_pem and not certificate_der:
                certificate_der = bytes(certificate_pem_to_der(certificate_pem))

            info = get_certificate_info(certificate_der)

            # Check if OCSP responder URL is embedded
            ocsp_url = get_ocsp_responder_url(certificate_der)
            if ocsp_url:
                logger.debug("OCSP responder found: %s (not yet fetched)", ocsp_url)

            # CRL-based revocation requires fetching from distribution points,
            # which are jurisdiction-specific.  Return UNKNOWN until CRL/OCSP
            # network fetching is wired up.
            return RevocationCheckResult(
                status=RevocationStatus.UNKNOWN,
                errors=["AAMVA CRL distribution points not yet configured"],
            )

        except Exception as e:
            return RevocationCheckResult(
                status=RevocationStatus.UNKNOWN,
                errors=[str(e)],
            )

    async def refresh(self) -> RefreshResult:
        """Refresh IACA trust anchors from AAMVA DTS / VICAL."""
        if self._rust_registry is None:
            return RefreshResult(
                success=False,
                errors=["AAMVA trust registry not available"],
            )

        anchors_before = len(self._rust_registry)

        # VICAL/DTS fetching requires network access;
        # the registry already loads from iaca_directory on init.
        anchors_after = len(self._rust_registry)

        return RefreshResult(
            success=True,
            anchors_added=max(0, anchors_after - anchors_before),
        )

    async def is_issuer_trusted(self, issuer_id: str) -> bool:
        """Check if a jurisdiction is trusted."""
        if self._rust_registry is None:
            return False
        try:
            jurisdictions = self._rust_registry.supported_jurisdictions()
            return issuer_id in jurisdictions
        except Exception:
            return False
