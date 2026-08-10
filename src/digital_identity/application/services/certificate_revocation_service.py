"""
Certificate Revocation Service with Offline Grace Period Support.

Wraps revocation checking with Redis caching and grace period enforcement
according to RevocationPolicy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from digital_identity.domain.value_objects import RevocationCheckMode, RevocationPolicy
from digital_identity.infrastructure.adapters.revocation_cache import (
    RevocationCacheAdapter,
)
from marty_plugin.native_backends import (
    NativeBackendUnavailable,
    NativeOperationError,
)

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
        issuer_certificate_der: bytes | None = None,
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
            online_result = await self._check_online(
                certificate_der, policy, issuer_certificate_der
            )

            # Cache the successful result
            await self.cache.set(
                organization_id=organization_id,
                certificate_der=certificate_der,
                is_revoked=online_result["is_revoked"],
                revocation_timestamp=online_result.get("revocation_timestamp"),
                reason=online_result.get("reason"),
                ttl_seconds=policy.cache_ttl_seconds,
            )

            return RevocationCheckResult(
                is_revoked=online_result["is_revoked"],
                source="online",
                check_timestamp=datetime.now(timezone.utc),
                revocation_timestamp=online_result.get("revocation_timestamp"),
                reason=online_result.get("reason"),
            )

        except NativeBackendUnavailable:
            raise
        except Exception as e:
            logger.warning(f"Online revocation check failed: {e}")

            # Check if we're in offline mode with skip policy
            if policy.check_mode == RevocationCheckMode.SKIP:
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
                grace_period_seconds=policy.cache_ttl_seconds,
            )

            if within_grace and cached_entry:
                cache_age = datetime.now(timezone.utc) - cached_entry.check_timestamp

                logger.info(
                    f"Using cached revocation result (age: {cache_age.total_seconds()}s, "
                    f"grace: {policy.cache_ttl_seconds}s)"
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
            if policy.check_mode == RevocationCheckMode.SOFT_FAIL:
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
                raise RuntimeError(
                    f"Certificate revocation check failed: {e}. "
                    f"No cached result within grace period ({policy.cache_ttl_seconds}s). "
                    f"HARD_FAIL policy enforced."
                )

    async def _check_online(
        self,
        certificate_der: bytes,
        policy: RevocationPolicy,
        issuer_certificate_der: bytes | None = None,
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
        del policy  # Network-source selection is currently certificate driven.
        native = self.revocation_processor.native
        certificate_info = native.get_certificate_info(certificate_der)
        issuer_dn = certificate_info["issuer"]
        failures: list[str] = []

        # Try OCSP first when advertised by the certificate.
        ocsp_url = self.revocation_processor.get_ocsp_url_from_certificate(
            certificate_der
        )
        if ocsp_url:
            if issuer_certificate_der is None:
                failures.append("OCSP requires the issuer certificate")
            else:
                result = await self.revocation_processor.check_ocsp_status(
                    certificate_der, issuer_certificate_der, ocsp_url
                )
                if result.get("success"):
                    status = str(result.get("status", "unknown")).lower()
                    if status == "good":
                        return {"is_revoked": False}
                    if status in {"bad", "revoked"}:
                        return {
                            "is_revoked": True,
                            "revocation_timestamp": result.get("revocation_date"),
                            "reason": result.get("reason_code"),
                        }
                    failures.append("OCSP responder returned unknown status")
                else:
                    failures.append(str(result.get("error", "OCSP check failed")))

        # Fall through to each advertised CRL distribution point.
        for crl_url in self._get_crl_urls_from_certificate(certificate_der):
            fetched = await self.revocation_processor._fetch_crl_from_url(crl_url)
            if not fetched.get("success"):
                failures.append(str(fetched.get("error", "CRL fetch failed")))
                continue
            if issuer_certificate_der is None:
                failures.append(
                    "CRL signature verification requires the issuer certificate"
                )
                continue

            crl_der = self.revocation_processor._crl_der(fetched["data"])
            if not native.verify_crl_signature(crl_der, issuer_certificate_der):
                failures.append(f"CRL signature verification failed for {crl_url}")
                continue

            is_revoked, reason = self.revocation_processor.check_revocation_against_crl(
                certificate_der, issuer_dn, crl_der
            )
            return {"is_revoked": bool(is_revoked), "reason": reason}

        detail = "; ".join(failures) or "certificate advertises no OCSP or CRL source"
        raise NativeOperationError(f"No verified revocation source succeeded: {detail}")

    def _get_crl_urls_from_certificate(self, certificate_der: bytes) -> list[str]:
        """Extract CRL distribution point URLs using native X.509 parsing."""
        return self.revocation_processor.get_crl_urls_from_certificate(certificate_der)
