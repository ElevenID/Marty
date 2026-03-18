"""
Custom Trust Profile Adapter

Flexible trust profile for custom trust sources and validation logic.
Allows configuration of arbitrary trust anchors and validation rules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

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


@dataclass
class CustomTrustProfile:
    """
    Custom Trust Profile implementation.

    Provides a flexible trust framework for custom trust sources.
    Supports manual trust anchor configuration, custom validation logic
    via callbacks, pluggable revocation checking, and custom refresh
    mechanisms.
    """

    name: str
    trust_anchors: dict[str, TrustAnchor] = field(default_factory=dict)
    validation_callback: Callable[[list[str], str | None], ChainValidationResult] | None = None
    revocation_callback: Callable[[str, str | None], RevocationCheckResult] | None = None
    refresh_callback: Callable[[], RefreshResult] | None = None

    # ------------------------------------------------------------------
    # TrustProfilePort interface
    # ------------------------------------------------------------------

    async def get_trust_anchors(
        self,
        jurisdiction: str | None = None,
        country_code: str | None = None,
    ) -> list[TrustAnchor]:
        """Get configured trust anchors, optionally filtered."""
        lookup = jurisdiction or country_code
        if lookup:
            return [
                anchor
                for anchor in self.trust_anchors.values()
                if lookup in (anchor.subject or "")
                or lookup in (anchor.issuer or "")
                or anchor.country_code == lookup
                or anchor.jurisdiction == lookup
            ]
        return list(self.trust_anchors.values())

    async def get_anchor_by_id(self, anchor_id: str) -> TrustAnchor | None:
        """Get a specific trust anchor by ID."""
        return self.trust_anchors.get(anchor_id)

    async def validate_chain(
        self,
        certificate_pem: str | None = None,
        certificate_der: bytes | None = None,
    ) -> ChainValidationResult:
        """Validate certificate chain using callback or Rust ChainValidator."""
        if self.validation_callback:
            try:
                chain = [certificate_pem] if certificate_pem else []
                return self.validation_callback(chain, None)
            except Exception as e:
                logger.exception("Custom validation callback failed")
                return ChainValidationResult(
                    status=ValidationStatus.INVALID,
                    errors=[f"Validation callback error: {e}"],
                )

        return await self._default_validate_chain(certificate_pem, certificate_der)

    async def _default_validate_chain(
        self,
        certificate_pem: str | None,
        certificate_der: bytes | None,
    ) -> ChainValidationResult:
        """Default chain validation using Rust ChainValidator."""
        if not certificate_pem and not certificate_der:
            return ChainValidationResult(
                status=ValidationStatus.INVALID,
                errors=["No certificate provided"],
            )

        if not self.trust_anchors:
            return ChainValidationResult(
                status=ValidationStatus.INVALID,
                errors=["No trust anchors configured"],
            )

        try:
            from marty_verification import ChainValidator, certificate_der_to_pem  # type: ignore

            if certificate_der and not certificate_pem:
                certificate_pem = certificate_der_to_pem(certificate_der)

            validator = ChainValidator()
            for anchor in self.trust_anchors.values():
                if anchor.certificate_pem:
                    validator.add_trust_anchor(anchor.certificate_pem)

            result = validator.validate_chain([certificate_pem])

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

        except ImportError:
            # Fallback to pure-Python issuer matching
            return self._python_fallback_validate(certificate_pem)

        except Exception as e:
            logger.exception("Default chain validation failed")
            return ChainValidationResult(
                status=ValidationStatus.INVALID,
                errors=[f"Validation error: {e}"],
            )

    def _python_fallback_validate(self, certificate_pem: str) -> ChainValidationResult:
        """Minimal pure-Python fallback: match leaf issuer to anchor subject."""
        try:
            leaf_cert = x509.load_pem_x509_certificate(certificate_pem.encode("utf-8"))
            leaf_issuer = leaf_cert.issuer.rfc4514_string()

            for anchor_id, anchor in self.trust_anchors.items():
                if not anchor.certificate_pem:
                    continue
                anchor_cert = x509.load_pem_x509_certificate(
                    anchor.certificate_pem.encode("utf-8")
                )
                if leaf_issuer == anchor_cert.subject.rfc4514_string():
                    # Verify signature using cryptography library
                    try:
                        from cryptography.hazmat.primitives.asymmetric import ec, padding
                        pubkey = anchor_cert.public_key()
                        sig_algo = leaf_cert.signature_algorithm_oid.dotted_string

                        if isinstance(pubkey, ec.EllipticCurvePublicKey):
                            pubkey.verify(
                                leaf_cert.signature,
                                leaf_cert.tbs_certificate_bytes,
                                ec.ECDSA(leaf_cert.signature_hash_algorithm),
                            )
                        else:
                            pubkey.verify(
                                leaf_cert.signature,
                                leaf_cert.tbs_certificate_bytes,
                                padding.PKCS1v15(),
                                leaf_cert.signature_hash_algorithm,
                            )

                        return ChainValidationResult(
                            status=ValidationStatus.VALID,
                            trust_anchor_id=anchor_id,
                            chain_length=1,
                            warnings=["Python fallback validation — Rust unavailable"],
                        )
                    except Exception as e:
                        return ChainValidationResult(
                            status=ValidationStatus.INVALID,
                            errors=[f"Signature verification failed: {e}"],
                        )

            return ChainValidationResult(
                status=ValidationStatus.INVALID,
                errors=[f"No trust anchor found for issuer: {leaf_issuer}"],
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
        """Check revocation status using callback or return UNKNOWN."""
        if self.revocation_callback:
            try:
                return self.revocation_callback(certificate_pem or "", None)
            except Exception as e:
                logger.exception("Custom revocation callback failed")
                return RevocationCheckResult(
                    status=RevocationStatus.UNKNOWN,
                    errors=[f"Revocation callback error: {e}"],
                )

        return RevocationCheckResult(
            status=RevocationStatus.UNKNOWN,
            errors=["No revocation checking configured"],
        )

    async def refresh(self) -> RefreshResult:
        """Refresh trust anchors using callback."""
        if self.refresh_callback:
            try:
                return self.refresh_callback()
            except Exception as e:
                logger.exception("Custom refresh callback failed")
                return RefreshResult(
                    success=False,
                    errors=[f"Refresh callback error: {e}"],
                )

        return RefreshResult(success=True)

    async def is_issuer_trusted(self, issuer_id: str) -> bool:
        """Check if an issuer is trusted."""
        for anchor in self.trust_anchors.values():
            if (
                issuer_id in (anchor.subject or "")
                or issuer_id in (anchor.issuer or "")
                or anchor.country_code == issuer_id
                or anchor.jurisdiction == issuer_id
            ):
                return True
        return False

    # ------------------------------------------------------------------
    # Anchor management helpers
    # ------------------------------------------------------------------

    def add_trust_anchor(
        self,
        identifier: str,
        certificate_pem: str,
        source: str = "manual",
    ) -> None:
        """Add a trust anchor from a PEM certificate."""
        cert = x509.load_pem_x509_certificate(certificate_pem.encode("utf-8"))
        not_before = (
            cert.not_valid_before_utc
            if hasattr(cert, "not_valid_before_utc")
            else cert.not_valid_before
        )
        not_after = (
            cert.not_valid_after_utc
            if hasattr(cert, "not_valid_after_utc")
            else cert.not_valid_after
        )
        fingerprint = cert.fingerprint(hashes.SHA256()).hex()

        anchor = TrustAnchor(
            id=fingerprint,
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            serial_number=format(cert.serial_number, "x"),
            valid_from=not_before,
            valid_until=not_after,
            certificate_pem=certificate_pem,
            certificate_der=cert.public_bytes(serialization.Encoding.DER),
            metadata={"source": source},
        )

        self.trust_anchors[identifier] = anchor
        logger.info("Added trust anchor: %s from %s", identifier, source)

    def remove_trust_anchor(self, identifier: str) -> bool:
        """Remove a trust anchor by identifier."""
        if identifier in self.trust_anchors:
            del self.trust_anchors[identifier]
            logger.info("Removed trust anchor: %s", identifier)
            return True
        return False
