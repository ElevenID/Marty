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
from cryptography.hazmat.primitives import serialization

from digital_identity.application.ports.trust_profile import (
    TrustProfilePort,
    TrustAnchor,
    ChainValidationResult,
    RevocationCheckResult,
    RefreshResult,
)

logger = logging.getLogger(__name__)


@dataclass
class IcaoTrustProfile:
    """
    ICAO Trust Profile implementation.
    
    Wraps the existing CSCATrustStore for ICAO 9303 eMRTD trust validation.
    Uses Rust marty-verification CscaRegistry for high-performance certificate validation.
    """
    
    trust_store_path: Path
    master_list_sources: list[str]
    pkd_urls: list[str]
    _trust_store: Any = None  # CSCATrustStore instance
    _rust_registry: Any = None  # Rust CscaRegistry via PyO3
    
    def __post_init__(self):
        """Initialize the trust store."""
        from marty_plugin.common.crypto.csca_trust_store import CSCATrustStore
        
        self._trust_store = CSCATrustStore(trust_store_path=self.trust_store_path)
        
        # Initialize Rust registry
        try:
            from marty_verification import CscaRegistry  # type: ignore
            self._rust_registry = CscaRegistry.from_directory(str(self.trust_store_path))
            logger.info(f"Initialized ICAO trust profile with {len(self._rust_registry.get_anchors())} anchors")
        except ImportError:
            logger.warning("Rust marty-verification not available, using Python-only validation")
            self._rust_registry = None
    
    async def get_trust_anchors(self, issuer: str | None = None) -> list[TrustAnchor]:
        """
        Get trust anchors for an issuer (country code).
        
        Args:
            issuer: ISO 3166-1 alpha-2 or alpha-3 country code (e.g., "US", "DEU")
        
        Returns:
            List of trust anchors for the specified country
        """
        if issuer:
            # Get country-specific CSCAs
            certificates = self._trust_store.get_csca_certificates_for_country(issuer)
        else:
            # Get all trusted CSCAs
            certificates = self._trust_store.get_all_trusted_certificates()
        
        anchors = []
        for cert in certificates:
            # Convert to x509.Certificate if it's a CertificateBridge
            if hasattr(cert, 'to_cryptography'):
                cert = cert.to_cryptography()
            
            pem = cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
            subject = cert.subject.rfc4514_string()
            
            anchors.append(TrustAnchor(
                identifier=self._get_cert_id(cert),
                subject=subject,
                issuer=cert.issuer.rfc4514_string(),
                not_before=cert.not_valid_before_utc if hasattr(cert, 'not_valid_before_utc') else cert.not_valid_before,
                not_after=cert.not_valid_after_utc if hasattr(cert, 'not_valid_after_utc') else cert.not_valid_after,
                pem=pem,
                source="icao_pkd",
            ))
        
        return anchors
    
    async def validate_chain(
        self,
        certificate_chain: list[str],  # PEM-encoded certificates
        issuer: str | None = None,
    ) -> ChainValidationResult:
        """
        Validate a certificate chain against ICAO trust anchors.
        
        Args:
            certificate_chain: List of PEM-encoded certificates (leaf first)
            issuer: Expected country code (optional)
        
        Returns:
            Chain validation result
        """
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
            
            # Use Rust validator if available for better performance
            if self._rust_registry:
                return await self._validate_with_rust(certificate_chain, issuer)
            
            # Fallback to Python validation
            return await self._validate_with_python(leaf_cert, issuer)
        
        except Exception as e:
            logger.exception("Certificate chain validation failed")
            return ChainValidationResult(
                is_valid=False,
                trust_anchor_used=None,
                validation_time=datetime.now(),
                errors=[f"Validation error: {str(e)}"],
            )
    
    async def _validate_with_rust(
        self,
        certificate_chain: list[str],
        issuer: str | None,
    ) -> ChainValidationResult:
        """Validate using Rust marty-verification library."""
        try:
            # Rust validation implementation
            # This would call into the Rust CscaRegistry
            result = self._rust_registry.validate_chain(certificate_chain)
            
            return ChainValidationResult(
                is_valid=result.is_valid,
                trust_anchor_used=result.trust_anchor_subject if result.is_valid else None,
                validation_time=datetime.now(),
                errors=result.errors if not result.is_valid else None,
                warnings=result.warnings,
            )
        except Exception as e:
            logger.error(f"Rust validation failed: {e}")
            # Fallback to Python
            leaf_pem = certificate_chain[0]
            leaf_cert = x509.load_pem_x509_certificate(leaf_pem.encode('utf-8'))
            return await self._validate_with_python(leaf_cert, issuer)
    
    async def _validate_with_python(
        self,
        leaf_cert: x509.Certificate,
        issuer: str | None,
    ) -> ChainValidationResult:
        """Validate using Python CSCATrustStore."""
        is_valid, messages = self._trust_store.verify_csca_certificate(leaf_cert, issuer)
        
        if is_valid:
            # Find which trust anchor was used
            cert_id = self._get_cert_id(leaf_cert)
            metadata = self._trust_store._metadata.get(cert_id)
            trust_anchor = metadata.country_code if metadata else None
            
            return ChainValidationResult(
                is_valid=True,
                trust_anchor_used=trust_anchor,
                validation_time=datetime.now(),
                errors=None,
                warnings=messages if messages else None,
            )
        else:
            return ChainValidationResult(
                is_valid=False,
                trust_anchor_used=None,
                validation_time=datetime.now(),
                errors=messages,
            )
    
    async def check_revocation(
        self,
        certificate: str,  # PEM-encoded certificate
        issuer: str | None = None,
    ) -> RevocationCheckResult:
        """
        Check revocation status via CRL/OCSP.
        
        This delegates to the existing revocation checking infrastructure.
        """
        try:
            cert = x509.load_pem_x509_certificate(certificate.encode('utf-8'))
            
            # TODO: Integrate with existing revocation checking
            # from marty_plugin.common.crypto.certificate_validator import CertificateChainValidator
            
            # For now, return unknown
            return RevocationCheckResult(
                is_revoked=False,
                status="unknown",
                checked_at=datetime.now(),
                source=None,
                error="Revocation checking not yet integrated",
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
        Refresh trust anchors from ICAO PKD Master Lists.
        
        This would fetch updated CSCA certificates from configured sources.
        """
        try:
            anchors_before = len(self._trust_store._certificates)
            
            # TODO: Implement Master List fetching and parsing
            # This would:
            # 1. Fetch Master Lists from pkd_urls
            # 2. Parse and validate the Master List
            # 3. Add new CSCA certificates to the trust store
            # 4. Remove expired/revoked certificates
            
            anchors_after = len(self._trust_store._certificates)
            
            logger.info(f"ICAO trust refresh: {anchors_before} -> {anchors_after} anchors")
            
            return RefreshResult(
                success=True,
                anchors_updated=anchors_after - anchors_before,
                error=None,
            )
        
        except Exception as e:
            logger.exception("Failed to refresh ICAO trust anchors")
            return RefreshResult(
                success=False,
                anchors_updated=0,
                error=str(e),
            )
    
    async def is_issuer_trusted(self, issuer: str) -> bool:
        """
        Check if an issuer (country code) is trusted.
        
        Args:
            issuer: ISO 3166-1 alpha-2 or alpha-3 country code
        
        Returns:
            True if we have trust anchors for this country
        """
        certificates = self._trust_store.get_csca_certificates_for_country(issuer)
        return len(certificates) > 0
    
    def _get_cert_id(self, cert: x509.Certificate) -> str:
        """Generate certificate identifier (SHA-256 fingerprint)."""
        fingerprint = cert.fingerprint(hashes.SHA256())  # type: ignore
        return fingerprint.hex()


# Import hashes for certificate fingerprinting
from cryptography.hazmat.primitives import hashes  # noqa: E402
