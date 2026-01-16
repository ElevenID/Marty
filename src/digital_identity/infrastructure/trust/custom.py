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
)

logger = logging.getLogger(__name__)


@dataclass
class CustomTrustProfile:
    """
    Custom Trust Profile implementation.
    
    Provides a flexible trust framework for custom trust sources.
    Supports:
    - Manual trust anchor configuration
    - Custom validation logic via callbacks
    - Pluggable revocation checking
    - Custom refresh mechanisms
    """
    
    name: str
    trust_anchors: dict[str, TrustAnchor] = field(default_factory=dict)
    validation_callback: Callable[[list[str], str | None], ChainValidationResult] | None = None
    revocation_callback: Callable[[str, str | None], RevocationCheckResult] | None = None
    refresh_callback: Callable[[], RefreshResult] | None = None
    
    async def get_trust_anchors(self, issuer: str | None = None) -> list[TrustAnchor]:
        """
        Get configured trust anchors.
        
        Args:
            issuer: Optional issuer filter
        
        Returns:
            List of trust anchors, optionally filtered by issuer
        """
        if issuer:
            return [
                anchor for anchor in self.trust_anchors.values()
                if anchor.subject.find(issuer) != -1 or anchor.issuer.find(issuer) != -1
            ]
        return list(self.trust_anchors.values())
    
    async def validate_chain(
        self,
        certificate_chain: list[str],
        issuer: str | None = None,
    ) -> ChainValidationResult:
        """
        Validate certificate chain.
        
        Uses custom validation callback if provided, otherwise performs basic validation.
        """
        if self.validation_callback:
            try:
                return self.validation_callback(certificate_chain, issuer)
            except Exception as e:
                logger.exception("Custom validation callback failed")
                return ChainValidationResult(
                    is_valid=False,
                    trust_anchor_used=None,
                    validation_time=datetime.now(),
                    errors=[f"Validation callback error: {str(e)}"],
                )
        
        # Default validation: check if leaf certificate is issued by a known trust anchor
        return await self._default_validate_chain(certificate_chain, issuer)
    
    async def _default_validate_chain(
        self,
        certificate_chain: list[str],
        issuer: str | None,
    ) -> ChainValidationResult:
        """Default chain validation logic."""
        if not certificate_chain:
            return ChainValidationResult(
                is_valid=False,
                trust_anchor_used=None,
                validation_time=datetime.now(),
                errors=["Empty certificate chain"],
            )
        
        try:
            # Parse leaf certificate
            leaf_pem = certificate_chain[0]
            leaf_cert = x509.load_pem_x509_certificate(leaf_pem.encode('utf-8'))
            leaf_issuer = leaf_cert.issuer.rfc4514_string()
            
            # Find matching trust anchor
            for anchor_id, anchor in self.trust_anchors.items():
                anchor_cert = x509.load_pem_x509_certificate(anchor.pem.encode('utf-8'))
                anchor_subject = anchor_cert.subject.rfc4514_string()
                
                if leaf_issuer == anchor_subject:
                    # Found matching trust anchor
                    # Verify signature (basic check)
                    try:
                        anchor_cert.public_key().verify(
                            leaf_cert.signature,
                            leaf_cert.tbs_certificate_bytes,
                            # padding and hash algorithm depend on signature algorithm
                        )
                        
                        return ChainValidationResult(
                            is_valid=True,
                            trust_anchor_used=anchor.subject,
                            validation_time=datetime.now(),
                            errors=None,
                            warnings=["Basic validation only - full chain validation not performed"],
                        )
                    except Exception as e:
                        return ChainValidationResult(
                            is_valid=False,
                            trust_anchor_used=None,
                            validation_time=datetime.now(),
                            errors=[f"Signature verification failed: {str(e)}"],
                        )
            
            return ChainValidationResult(
                is_valid=False,
                trust_anchor_used=None,
                validation_time=datetime.now(),
                errors=[f"No trust anchor found for issuer: {leaf_issuer}"],
            )
        
        except Exception as e:
            logger.exception("Default chain validation failed")
            return ChainValidationResult(
                is_valid=False,
                trust_anchor_used=None,
                validation_time=datetime.now(),
                errors=[f"Validation error: {str(e)}"],
            )
    
    async def check_revocation(
        self,
        certificate: str,
        issuer: str | None = None,
    ) -> RevocationCheckResult:
        """
        Check revocation status.
        
        Uses custom revocation callback if provided.
        """
        if self.revocation_callback:
            try:
                return self.revocation_callback(certificate, issuer)
            except Exception as e:
                logger.exception("Custom revocation callback failed")
                return RevocationCheckResult(
                    is_revoked=False,
                    status="error",
                    checked_at=datetime.now(),
                    source=None,
                    error=f"Revocation callback error: {str(e)}",
                )
        
        # No revocation checking configured
        return RevocationCheckResult(
            is_revoked=False,
            status="unknown",
            checked_at=datetime.now(),
            source=None,
            error="No revocation checking configured",
        )
    
    async def refresh(self) -> RefreshResult:
        """
        Refresh trust anchors.
        
        Uses custom refresh callback if provided.
        """
        if self.refresh_callback:
            try:
                return self.refresh_callback()
            except Exception as e:
                logger.exception("Custom refresh callback failed")
                return RefreshResult(
                    success=False,
                    anchors_updated=0,
                    error=f"Refresh callback error: {str(e)}",
                )
        
        # No refresh mechanism configured
        return RefreshResult(
            success=True,
            anchors_updated=0,
            error=None,
        )
    
    async def is_issuer_trusted(self, issuer: str) -> bool:
        """Check if an issuer is trusted."""
        for anchor in self.trust_anchors.values():
            if issuer in anchor.subject or issuer in anchor.issuer:
                return True
        return False
    
    def add_trust_anchor(
        self,
        identifier: str,
        certificate_pem: str,
        source: str = "manual",
    ) -> None:
        """
        Add a trust anchor.
        
        Args:
            identifier: Unique identifier for this anchor
            certificate_pem: PEM-encoded certificate
            source: Source of this anchor (for audit trail)
        """
        try:
            cert = x509.load_pem_x509_certificate(certificate_pem.encode('utf-8'))
            
            anchor = TrustAnchor(
                identifier=identifier,
                subject=cert.subject.rfc4514_string(),
                issuer=cert.issuer.rfc4514_string(),
                not_before=cert.not_valid_before_utc if hasattr(cert, 'not_valid_before_utc') else cert.not_valid_before,
                not_after=cert.not_valid_after_utc if hasattr(cert, 'not_valid_after_utc') else cert.not_valid_after,
                pem=certificate_pem,
                source=source,
            )
            
            self.trust_anchors[identifier] = anchor
            logger.info(f"Added trust anchor: {identifier} from {source}")
        
        except Exception as e:
            logger.exception(f"Failed to add trust anchor: {identifier}")
            raise ValueError(f"Invalid certificate: {str(e)}")
    
    def remove_trust_anchor(self, identifier: str) -> bool:
        """
        Remove a trust anchor.
        
        Args:
            identifier: Identifier of anchor to remove
        
        Returns:
            True if anchor was removed
        """
        if identifier in self.trust_anchors:
            del self.trust_anchors[identifier]
            logger.info(f"Removed trust anchor: {identifier}")
            return True
        return False
