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
)

logger = logging.getLogger(__name__)


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
                self._rust_registry = IacaRegistry.from_directory(str(self.iaca_directory))
                logger.info(f"Initialized AAMVA trust profile with {len(self._rust_registry.get_anchors())} IACA anchors")
            else:
                self._rust_registry = IacaRegistry.new()
                logger.info("Initialized empty AAMVA trust profile")
        
        except ImportError:
            logger.error("Rust marty-verification not available - AAMVA trust profile unavailable")
            self._rust_registry = None
    
    async def get_trust_anchors(self, issuer: str | None = None) -> list[TrustAnchor]:
        """
        Get trust anchors for a jurisdiction.
        
        Args:
            issuer: Jurisdiction code (e.g., "US-CA", "CA-ON")
        
        Returns:
            List of IACA trust anchors
        """
        if not self._rust_registry:
            return []
        
        try:
            if issuer:
                # Get jurisdiction-specific IACAs
                rust_anchors = self._rust_registry.get_jurisdiction_iacas(issuer)
            else:
                # Get all IACAs
                rust_anchors = self._rust_registry.get_anchors()
            
            anchors = []
            for rust_anchor in rust_anchors:
                anchors.append(TrustAnchor(
                    identifier=rust_anchor.identifier,
                    subject=rust_anchor.subject,
                    issuer=rust_anchor.issuer,
                    not_before=rust_anchor.not_before,
                    not_after=rust_anchor.not_after,
                    pem=rust_anchor.pem,
                    source="aamva_dts",
                ))
            
            return anchors
        
        except Exception as e:
            logger.exception(f"Failed to get AAMVA trust anchors for {issuer}")
            return []
    
    async def validate_chain(
        self,
        certificate_chain: list[str],  # PEM-encoded certificates
        issuer: str | None = None,
    ) -> ChainValidationResult:
        """
        Validate an mDL certificate chain against IACA trust anchors.
        
        Args:
            certificate_chain: List of PEM-encoded certificates (leaf first)
            issuer: Expected jurisdiction code (optional)
        
        Returns:
            Chain validation result
        """
        if not self._rust_registry:
            return ChainValidationResult(
                is_valid=False,
                trust_anchor_used=None,
                validation_time=datetime.now(),
                errors=["AAMVA trust registry not available"],
            )
        
        if not certificate_chain:
            return ChainValidationResult(
                is_valid=False,
                trust_anchor_used=None,
                validation_time=datetime.now(),
                errors=["Empty certificate chain"],
            )
        
        try:
            # Validate using Rust IacaRegistry
            result = self._rust_registry.validate_mdl_chain(
                certificate_chain,
                jurisdiction=issuer,
            )
            
            return ChainValidationResult(
                is_valid=result.is_valid,
                trust_anchor_used=result.trust_anchor_jurisdiction if result.is_valid else None,
                validation_time=datetime.now(),
                errors=result.errors if not result.is_valid else None,
                warnings=result.warnings,
            )
        
        except Exception as e:
            logger.exception("mDL chain validation failed")
            return ChainValidationResult(
                is_valid=False,
                trust_anchor_used=None,
                validation_time=datetime.now(),
                errors=[f"Validation error: {str(e)}"],
            )
    
    async def check_revocation(
        self,
        certificate: str,  # PEM-encoded certificate
        issuer: str | None = None,
    ) -> RevocationCheckResult:
        """
        Check mDL certificate revocation status.
        
        For mDL, this typically checks:
        - CRL from the issuing jurisdiction
        - OCSP if available
        - AAMVA-specific revocation mechanisms
        """
        try:
            if not self._rust_registry:
                return RevocationCheckResult(
                    is_revoked=False,
                    status="error",
                    checked_at=datetime.now(),
                    source=None,
                    error="AAMVA trust registry not available",
                )
            
            # TODO: Implement mDL-specific revocation checking
            # This would integrate with AAMVA revocation services
            
            return RevocationCheckResult(
                is_revoked=False,
                status="unknown",
                checked_at=datetime.now(),
                source=None,
                error="mDL revocation checking not yet implemented",
            )
        
        except Exception as e:
            return RevocationCheckResult(
                is_revoked=False,
                status="error",
                checked_at=datetime.now(),
                source=None,
                error=str(e),
            )
    
    async def refresh(self) -> RefreshResult:
        """
        Refresh IACA trust anchors from AAMVA DTS.
        
        This would fetch updated IACA certificates from:
        - AAMVA DTS (Driver Trust Service)
        - VICAL (Verifier IACA Certificate Authority List)
        """
        try:
            if not self._rust_registry:
                return RefreshResult(
                    success=False,
                    anchors_updated=0,
                    error="AAMVA trust registry not available",
                )
            
            anchors_before = len(self._rust_registry.get_anchors())
            
            # TODO: Implement VICAL/DTS fetching
            # This would:
            # 1. Fetch VICAL from vical_url
            # 2. Parse and validate the VICAL
            # 3. Add new IACA certificates
            # 4. Remove expired/revoked certificates
            
            anchors_after = len(self._rust_registry.get_anchors())
            
            logger.info(f"AAMVA trust refresh: {anchors_before} -> {anchors_after} anchors")
            
            return RefreshResult(
                success=True,
                anchors_updated=anchors_after - anchors_before,
                error=None,
            )
        
        except Exception as e:
            logger.exception("Failed to refresh AAMVA trust anchors")
            return RefreshResult(
                success=False,
                anchors_updated=0,
                error=str(e),
            )
    
    async def is_issuer_trusted(self, issuer: str) -> bool:
        """
        Check if a jurisdiction is trusted.
        
        Args:
            issuer: Jurisdiction code (e.g., "US-CA", "CA-ON")
        
        Returns:
            True if we have IACA trust anchors for this jurisdiction
        """
        if not self._rust_registry:
            return False
        
        try:
            anchors = self._rust_registry.get_jurisdiction_iacas(issuer)
            return len(anchors) > 0
        except Exception:
            return False
