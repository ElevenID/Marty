"""
Certificate Revocation Service with Offline Grace Period Support.

Wraps revocation checking with Redis caching and grace period enforcement
according to RevocationPolicy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

from digital_identity.domain.value_objects import RevocationPolicy, RevocationCheckMode
from digital_identity.infrastructure.adapters.revocation_cache import RevocationCacheAdapter

logger = logging.getLogger(__name__)


@dataclass
class RevocationCheckResult:
    """Result of a revocation check with cache metadata."""
    
    is_revoked: bool
    source: str  # "online", "cached", "grace_period"
    check_timestamp: datetime
    revocation_timestamp: datetime | None = None
    reason: str | None = None
    cache_age: timedelta | None = None  # For cached/grace_period results


class CertificateRevocationService:
    """
    Service for checking certificate revocation with offline grace period support.
    
    Implements the following flow:
    1. Attempt online revocation check (OCSP/CRL)
    2. On success: cache result and return
    3. On failure: check cache for recent valid result
    4. If cached result within grace period: return cached result
    5. Otherwise: respect RevocationCheckMode (hard_fail/soft_fail)
    """
    
    def __init__(
        self,
        revocation_processor: Any,  # marty_plugin.trust_svc.revocation.RevocationProcessor
        cache_adapter: RevocationCacheAdapter,
    ):
        """
        Initialize revocation service.
        
        Args:
            revocation_processor: Underlying revocation processor (OCSP/CRL)
            cache_adapter: Redis cache adapter
        """
        self.revocation_processor = revocation_processor
        self.cache = cache_adapter
    
    async def check_revocation(
        self,
        certificate_der: bytes,
        organization_id: str,
        policy: RevocationPolicy,
    ) -> RevocationCheckResult:
        """
        Check certificate revocation status with grace period support.
        
        Args:
            certificate_der: DER-encoded certificate
            organization_id: Organization ID for cache scoping
            policy: Revocation policy with grace period settings
            
        Returns:
            RevocationCheckResult with status and metadata
            
        Raises:
            Exception: If mode is HARD_FAIL and check fails (no cache or expired)
        """
        # Try online check first
        try:
            online_result = await self._check_online(certificate_der, policy)
            
            # Cache the successful result
            await self.cache.set(
                organization_id=organization_id,
                certificate_der=certificate_der,
                is_revoked=online_result["is_revoked"],
                revocation_timestamp=online_result.get("revocation_timestamp"),
                reason=online_result.get("reason"),
                ttl_seconds=int(policy.cache_ttl.total_seconds()),
            )
            
            return RevocationCheckResult(
                is_revoked=online_result["is_revoked"],
                source="online",
                check_timestamp=datetime.now(timezone.utc),
                revocation_timestamp=online_result.get("revocation_timestamp"),
                reason=online_result.get("reason"),
            )
            
        except Exception as e:
            logger.warning(f"Online revocation check failed: {e}")
            
            # Check if we're in offline mode with skip policy
            if policy.mode == RevocationCheckMode.SKIP:
                logger.info("Revocation check skipped per policy")
                return RevocationCheckResult(
                    is_revoked=False,
                    source="skipped",
                    check_timestamp=datetime.now(timezone.utc),
                )
            
            # Try to use cached result with grace period
            within_grace, cached_entry = await self.cache.is_within_grace_period(
                organization_id=organization_id,
                certificate_der=certificate_der,
                grace_period=policy.offline_grace_period,
            )
            
            if within_grace and cached_entry:
                cache_age = datetime.now(timezone.utc) - cached_entry.check_timestamp
                
                logger.info(
                    f"Using cached revocation result (age: {cache_age.total_seconds()}s, "
                    f"grace: {policy.offline_grace_period.total_seconds()}s)"
                )
                
                return RevocationCheckResult(
                    is_revoked=cached_entry.is_revoked,
                    source="grace_period",
                    check_timestamp=datetime.now(timezone.utc),
                    revocation_timestamp=cached_entry.revocation_timestamp,
                    reason=cached_entry.reason,
                    cache_age=cache_age,
                )
            
            # No valid cache - respect mode
            if policy.mode == RevocationCheckMode.SOFT_FAIL:
                logger.warning(
                    "Revocation check failed and no valid cache - allowing per SOFT_FAIL policy"
                )
                return RevocationCheckResult(
                    is_revoked=False,
                    source="soft_fail",
                    check_timestamp=datetime.now(timezone.utc),
                )
            
            else:  # HARD_FAIL
                logger.error(
                    "Revocation check failed, no valid cache, and HARD_FAIL policy enforced"
                )
                raise Exception(
                    f"Certificate revocation check failed: {e}. "
                    f"No cached result within grace period ({policy.offline_grace_period}). "
                    f"HARD_FAIL policy enforced."
                )
    
    async def _check_online(
        self,
        certificate_der: bytes,
        policy: RevocationPolicy,
    ) -> dict[str, Any]:
        """
        Perform online revocation check.
        
        Args:
            certificate_der: DER-encoded certificate
            policy: Revocation policy with check flags
            
        Returns:
            Dictionary with is_revoked, revocation_timestamp, reason
            
        Raises:
            Exception: If check fails
        """
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        
        cert = x509.load_der_x509_certificate(certificate_der)
        
        # Try OCSP if enabled
        if policy.check_ocsp:
            ocsp_url = self.revocation_processor.get_ocsp_url_from_certificate(cert)
            if ocsp_url:
                # Get issuer certificate (would need to be passed or looked up)
                # For now, skip OCSP and try CRL
                logger.debug(f"OCSP URL found: {ocsp_url} (OCSP check not fully implemented)")
        
        # Try CRL if enabled
        if policy.check_crl:
            # Get CRL distribution points
            try:
                crl_urls = self._get_crl_urls_from_certificate(cert)
                if crl_urls:
                    # Download and check CRL (simplified - production needs caching)
                    for crl_url in crl_urls:
                        try:
                            # This would fetch CRL and check
                            # For now, raise to trigger cache fallback
                            logger.debug(f"CRL check would use: {crl_url}")
                        except Exception as crl_error:
                            logger.warning(f"CRL check failed for {crl_url}: {crl_error}")
                            continue
            except Exception as e:
                logger.warning(f"Failed to get CRL URLs: {e}")
        
        # If no checks succeeded, raise to trigger cache fallback
        raise Exception("No successful online revocation check")
    
    def _get_crl_urls_from_certificate(self, cert: Any) -> list[str]:
        """Extract CRL distribution point URLs from certificate."""
        from cryptography.x509.oid import ExtensionOID
        from cryptography import x509
        
        try:
            crl_ext = cert.extensions.get_extension_for_oid(
                ExtensionOID.CRL_DISTRIBUTION_POINTS
            )
            urls = []
            for dist_point in crl_ext.value:
                if dist_point.full_name:
                    for name in dist_point.full_name:
                        if isinstance(name, x509.UniformResourceIdentifier):
                            urls.append(name.value)
            return urls
        except x509.ExtensionNotFound:
            return []
