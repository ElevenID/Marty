"""Verifier Trust List Management.

This module provides trust list management for verifiers, including:
- Periodic fetching from PKD endpoints
- Local caching with freshness validation
- CSCA→DSC chain validation
- VDS-NC signature verification
- Fail-closed policy for unknown keys
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import aiohttp
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
# Import crypto_bridge for certificate operations
from marty_plugin.common.crypto_bridge import (
    Certificate as CertificateBridge,
    load_pem_x509_certificate as load_pem_certificate,
)

logger = logging.getLogger(__name__)


class TrustPolicy(Enum):
    """Trust verification policy."""

    FAIL_CLOSED = "fail_closed"  # Reject unknown keys (RECOMMENDED)
    FAIL_OPEN = "fail_open"  # Accept with warning (NOT RECOMMENDED)
    SELECTIVE = "selective"  # Configurable per issuer


class ValidationResult:
    """Result of trust validation."""

    def __init__(
        self,
        valid: bool,
        reason: str = "",
        security_level: str = "strict",
        warnings: list[str] | None = None,
    ) -> None:
        self.valid = valid
        self.reason = reason
        self.security_level = security_level
        self.warnings = warnings or []

    def __repr__(self) -> str:
        return f"ValidationResult(valid={self.valid}, reason='{self.reason}')"


@dataclass
class VDSNCPublicKey:
    """VDS-NC public key with metadata."""

    kid: str
    public_key: EllipticCurvePublicKey
    issuer_country: str
    role: str
    not_before: datetime
    not_after: datetime
    status: str
    rotation_generation: int
    algorithm: str = "ES256"

    def is_valid_now(self) -> bool:
        """Check if key is currently valid."""
        now = datetime.now(timezone.utc)
        return self.status in ["active", "rotating"] and self.not_before <= now <= self.not_after


@dataclass
class TrustList:
    """Unified trust list for all verification paths."""

    csca_certificates: dict[str, x509.Certificate | CertificateBridge] = field(default_factory=dict)
    dsc_certificates: dict[str, list[x509.Certificate | CertificateBridge]] = field(default_factory=dict)
    vds_nc_keys: dict[str, VDSNCPublicKey] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    next_update: datetime | None = None
    source: str = ""
    signature: bytes | None = None

    def is_stale(self, warning_hours: int = 24, critical_hours: int = 48) -> tuple[bool, str]:
        """Check if trust list is stale.

        Returns:
            Tuple of (is_critical, status_message)
        """
        now = datetime.now(timezone.utc)
        age = now - self.last_updated
        age_hours = age.total_seconds() / 3600

        if age_hours > critical_hours:
            return True, f"Trust list critically stale ({age_hours:.1f} hours old)"
        if age_hours > warning_hours:
            return False, f"Trust list stale ({age_hours:.1f} hours old)"

        return False, "Trust list fresh"

    def get_stats(self) -> dict[str, Any]:
        """Get trust list statistics."""
        return {
            "csca_count": len(self.csca_certificates),
            "dsc_count": sum(len(dscs) for dscs in self.dsc_certificates.values()),
            "vds_nc_key_count": len(self.vds_nc_keys),
            "last_updated": self.last_updated.isoformat(),
            "age_hours": (datetime.now(timezone.utc) - self.last_updated).total_seconds() / 3600,
        }


class TrustListCache:
    """Local cache for trust list with persistence."""

    def __init__(self, cache_dir: Path | str) -> None:
        """Initialize trust list cache.

        Args:
            cache_dir: Directory for cache storage
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, trust_list: TrustList) -> None:
        """Save trust list to cache."""
        def cert_to_pem(cert) -> str:
            """Convert certificate to PEM string."""
            if isinstance(cert, CertificateBridge):
                return cert.to_pem().decode('utf-8') if isinstance(cert.to_pem(), bytes) else cert.to_pem()
            return cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
        
        cache_data = {
            "last_updated": trust_list.last_updated.isoformat(),
            "next_update": trust_list.next_update.isoformat() if trust_list.next_update else None,
            "source": trust_list.source,
            "csca_certificates": {
                country: cert_to_pem(cert)
                for country, cert in trust_list.csca_certificates.items()
            },
            "dsc_certificates": {
                country: [cert_to_pem(cert) for cert in certs]
                for country, certs in trust_list.dsc_certificates.items()
            },
            "vds_nc_keys": {
                kid: {
                    "kid": key.kid,
                    "issuer_country": key.issuer_country,
                    "role": key.role,
                    "not_before": key.not_before.isoformat(),
                    "not_after": key.not_after.isoformat(),
                    "status": key.status,
                    "rotation_generation": key.rotation_generation,
                    "algorithm": key.algorithm,
                    "public_key_pem": key.public_key.public_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo,
                    ).decode("utf-8"),
                }
                for kid, key in trust_list.vds_nc_keys.items()
            },
        }

        cache_file = self.cache_dir / "trust_list.json"
        with open(cache_file, "w") as f:
            json.dump(cache_data, f, indent=2)

        logger.info(f"Saved trust list to cache: {cache_file}")

    async def load(self) -> TrustList | None:
        """Load trust list from cache.

        Returns:
            Cached trust list or None if not found/invalid
        """
        cache_file = self.cache_dir / "trust_list.json"

        if not cache_file.exists():
            logger.warning("No cached trust list found")
            return None

        try:
            with open(cache_file) as f:
                cache_data = json.load(f)

            # Parse CSCA certificates using crypto_bridge
            csca_certs = {}
            for country, pem_data in cache_data.get("csca_certificates", {}).items():
                cert = load_pem_certificate(pem_data.encode("utf-8"))
                csca_certs[country] = cert

            # Parse DSC certificates using crypto_bridge
            dsc_certs: dict[str, list[CertificateBridge]] = {}
            for country, pem_list in cache_data.get("dsc_certificates", {}).items():
                dsc_certs[country] = [
                    load_pem_certificate(pem.encode("utf-8")) for pem in pem_list
                ]

            # Parse VDS-NC keys
            vds_nc_keys = {}
            for kid, key_data in cache_data.get("vds_nc_keys", {}).items():
                public_key_pem = key_data["public_key_pem"]
                public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))

                if isinstance(public_key, EllipticCurvePublicKey):
                    vds_nc_keys[kid] = VDSNCPublicKey(
                        kid=key_data["kid"],
                        public_key=public_key,
                        issuer_country=key_data["issuer_country"],
                        role=key_data["role"],
                        not_before=datetime.fromisoformat(key_data["not_before"]),
                        not_after=datetime.fromisoformat(key_data["not_after"]),
                        status=key_data["status"],
                        rotation_generation=key_data["rotation_generation"],
                        algorithm=key_data.get("algorithm", "ES256"),
                    )

            trust_list = TrustList(
                csca_certificates=csca_certs,
                dsc_certificates=dsc_certs,
                vds_nc_keys=vds_nc_keys,
                last_updated=datetime.fromisoformat(cache_data["last_updated"]),
                next_update=(
                    datetime.fromisoformat(cache_data["next_update"])
                    if cache_data.get("next_update")
                    else None
                ),
                source=cache_data.get("source", ""),
            )

            logger.info(
                f"Loaded trust list from cache (age: {trust_list.get_stats()['age_hours']:.1f} hours)"
            )

        except Exception as e:
            logger.exception(f"Failed to load trust list from cache: {e}")
            return None
        else:
            return trust_list


class PKDClient:
    """Client for fetching trust materials from PKD endpoints."""

    def __init__(self, pkd_base_url: str, timeout: int = 30) -> None:
        """Initialize PKD client.

        Args:
            pkd_base_url: Base URL of PKD service
            timeout: Request timeout in seconds
        """
        self.pkd_base_url = pkd_base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def fetch_vds_nc_keys(self, country_code: str | None = None) -> dict[str, VDSNCPublicKey]:
        """Fetch VDS-NC keys from PKD.

        Args:
            country_code: Country code or None for all

        Returns:
            Dictionary of kid → VDSNCPublicKey
        """
        url = (
            f"{self.pkd_base_url}/api/v1/pkd/vds-nc-keys/{country_code}"
            if country_code
            else f"{self.pkd_base_url}/api/v1/pkd/vds-nc-keys/all"
        )

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()

                vds_nc_keys = {}
                for key_jwk in data.get("keys", []):
                    # Convert JWK to public key
                    public_key = self._jwk_to_public_key(key_jwk)

                    vds_nc_keys[key_jwk["kid"]] = VDSNCPublicKey(
                        kid=key_jwk["kid"],
                        public_key=public_key,
                        issuer_country=key_jwk["issuer"],
                        role=key_jwk["role"],
                        not_before=datetime.fromisoformat(key_jwk["not_before"]),
                        not_after=datetime.fromisoformat(key_jwk["not_after"]),
                        status=key_jwk["status"],
                        rotation_generation=key_jwk["rotation_generation"],
                        algorithm=key_jwk.get("alg", "ES256"),
                    )

                logger.info(f"Fetched {len(vds_nc_keys)} VDS-NC keys from PKD")
                return vds_nc_keys

    async def fetch_vds_nc_key_by_kid(self, kid: str) -> VDSNCPublicKey | None:
        """Fetch single VDS-NC key by KID.

        Args:
            kid: Key identifier

        Returns:
            VDS-NC public key or None
        """
        url = f"{self.pkd_base_url}/api/v1/pkd/vds-nc-keys/key/{kid}"

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url) as response:
                    if response.status == 404:
                        return None

                    response.raise_for_status()
                    key_jwk = await response.json()

                    public_key = self._jwk_to_public_key(key_jwk)

                    return VDSNCPublicKey(
                        kid=key_jwk["kid"],
                        public_key=public_key,
                        issuer_country=key_jwk["issuer"],
                        role=key_jwk["role"],
                        not_before=datetime.fromisoformat(key_jwk["not_before"]),
                        not_after=datetime.fromisoformat(key_jwk["not_after"]),
                        status=key_jwk["status"],
                        rotation_generation=key_jwk["rotation_generation"],
                        algorithm=key_jwk.get("alg", "ES256"),
                    )
        except Exception as e:
            logger.exception(f"Failed to fetch VDS-NC key {kid}: {e}")
            return None

    def _jwk_to_public_key(self, jwk: dict[str, Any]) -> EllipticCurvePublicKey:
        """Convert JWK to EC public key."""
        import base64

        if jwk["kty"] != "EC" or jwk["crv"] != "P-256":
            msg = f"Unsupported key type: {jwk['kty']}/{jwk.get('crv')}"
            raise ValueError(msg)

        # Decode coordinates
        x_bytes = base64.urlsafe_b64decode(jwk["x"] + "==")
        y_bytes = base64.urlsafe_b64decode(jwk["y"] + "==")

        # Convert to integers
        x = int.from_bytes(x_bytes, "big")
        y = int.from_bytes(y_bytes, "big")

        # Create public key
        from cryptography.hazmat.primitives.asymmetric.ec import (
            SECP256R1,
            EllipticCurvePublicNumbers,
        )

        public_numbers = EllipticCurvePublicNumbers(x, y, SECP256R1())
        return public_numbers.public_key()


class TrustListManager:
    """Manage trust list with periodic refresh and validation."""

    def __init__(
        self,
        pkd_client: PKDClient,
        cache: TrustListCache,
        refresh_interval_hours: int = 24,
        trust_policy: TrustPolicy = TrustPolicy.FAIL_CLOSED,
    ) -> None:
        """Initialize trust list manager.

        Args:
            pkd_client: PKD client for fetching trust materials
            cache: Trust list cache
            refresh_interval_hours: Refresh interval in hours
            trust_policy: Trust verification policy
        """
        self.pkd_client = pkd_client
        self.cache = cache
        self.refresh_interval = timedelta(hours=refresh_interval_hours)
        self.trust_policy = trust_policy
        self.trust_list: TrustList | None = None
        self._refresh_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        """Initialize trust list (load from cache or fetch)."""
        # Try to load from cache
        self.trust_list = await self.cache.load()

        if self.trust_list:
            is_critical, status_msg = self.trust_list.is_stale()
            logger.info(f"Loaded trust list from cache: {status_msg}")

            if is_critical:
                logger.warning("Cached trust list is critically stale, forcing refresh")
                await self.refresh_trust_list()
        else:
            logger.info("No cached trust list, performing initial fetch")
            await self.refresh_trust_list()

        # Start periodic refresh
        self.start_periodic_refresh()

    async def refresh_trust_list(self) -> bool:
        """Refresh trust list from PKD.

        Returns:
            Success status
        """
        try:
            logger.info("Refreshing trust list from PKD")

            # Fetch VDS-NC keys
            vds_nc_keys = await self.pkd_client.fetch_vds_nc_keys()

            # Create new trust list
            new_trust_list = TrustList(
                vds_nc_keys=vds_nc_keys,
                last_updated=datetime.now(timezone.utc),
                next_update=datetime.now(timezone.utc) + self.refresh_interval,
                source=self.pkd_client.pkd_base_url,
            )

            # Update trust list
            self.trust_list = new_trust_list

            # Save to cache
            await self.cache.save(new_trust_list)

            logger.info(f"Trust list refreshed: {new_trust_list.get_stats()}")

        except Exception as e:
            logger.exception(f"Failed to refresh trust list: {e}")
            return False
        else:
            return True

    def start_periodic_refresh(self) -> None:
        """Start periodic trust list refresh task."""
        if self._refresh_task and not self._refresh_task.done():
            logger.warning("Refresh task already running")
            return

        self._refresh_task = asyncio.create_task(self._periodic_refresh_loop())
        logger.info(f"Started periodic trust list refresh (interval: {self.refresh_interval})")

    async def _periodic_refresh_loop(self) -> None:
        """Periodic refresh loop."""
        while True:
            try:
                await asyncio.sleep(self.refresh_interval.total_seconds())
                await self.refresh_trust_list()
            except asyncio.CancelledError:
                logger.info("Periodic refresh task cancelled")
                break
            except Exception as e:
                logger.exception(f"Error in periodic refresh: {e}")

    async def stop_periodic_refresh(self) -> None:
        """Stop periodic refresh task."""
        if self._refresh_task:
            self._refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._refresh_task

    async def get_vds_nc_key(self, kid: str) -> VDSNCPublicKey | None:
        """Get VDS-NC key by KID.

        Fetches from PKD if not in local trust list (key miss).

        Args:
            kid: Key identifier

        Returns:
            VDS-NC public key or None
        """
        if not self.trust_list:
            logger.error("Trust list not initialized")
            return None

        # Check local trust list
        key = self.trust_list.vds_nc_keys.get(kid)
        if key:
            return key

        # Key miss - fetch from PKD
        logger.info(f"VDS-NC key {kid} not in trust list, fetching from PKD")
        key = await self.pkd_client.fetch_vds_nc_key_by_kid(kid)

        if key:
            # Add to trust list
            self.trust_list.vds_nc_keys[kid] = key
            # Update cache
            await self.cache.save(self.trust_list)
            logger.info(f"Added VDS-NC key {kid} to trust list")

        return key

    def verify_vds_nc_signature(
        self, kid: str, message: bytes, signature: bytes
    ) -> ValidationResult:
        """Verify VDS-NC signature.

        Args:
            kid: Key identifier
            message: Signed message
            signature: Signature bytes

        Returns:
            Validation result
        """
        if not self.trust_list:
            return ValidationResult(valid=False, reason="Trust list not initialized")

        # Get public key
        key = self.trust_list.vds_nc_keys.get(kid)

        if not key:
            # Apply fail-closed policy
            if self.trust_policy == TrustPolicy.FAIL_CLOSED:
                return ValidationResult(
                    valid=False,
                    reason=f"Unknown VDS-NC key: {kid}",
                    security_level="strict",
                )
            if self.trust_policy == TrustPolicy.FAIL_OPEN:
                return ValidationResult(
                    valid=True,
                    reason=f"Unknown VDS-NC key: {kid}",
                    security_level="permissive",
                    warnings=[f"Unknown key {kid} - verification skipped"],
                )

        # Check key validity
        if not key.is_valid_now():
            return ValidationResult(
                valid=False,
                reason=f"VDS-NC key {kid} is not currently valid (status: {key.status})",
            )

        # Verify signature
        try:
            key.public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
            return ValidationResult(valid=True, reason="VDS-NC signature verified")
        except Exception as e:
            return ValidationResult(
                valid=False, reason=f"VDS-NC signature verification failed: {e}"
            )

    def validate_trust_list_freshness(self) -> ValidationResult:
        """Validate that trust list is not stale.

        Returns:
            Validation result
        """
        if not self.trust_list:
            return ValidationResult(valid=False, reason="Trust list not initialized")

        is_critical, status_msg = self.trust_list.is_stale()

        if is_critical:
            return ValidationResult(valid=False, reason=status_msg)

        return ValidationResult(valid=True, reason=status_msg)


# Example usage
async def example_verifier_workflow() -> None:
    """Example verifier workflow with trust list management."""
    # Initialize components
    pkd_client = PKDClient(pkd_base_url="https://pkd.example.com")
    cache = TrustListCache(cache_dir="/var/cache/marty/trust_list")
    trust_manager = TrustListManager(
        pkd_client=pkd_client,
        cache=cache,
        refresh_interval_hours=24,
        trust_policy=TrustPolicy.FAIL_CLOSED,
    )

    # Initialize trust list
    await trust_manager.initialize()

    # Verify a VDS-NC signature
    kid = "VDS-NC-USA-CMC-2025-01"
    message = b"Header+Payload"
    signature = b"..."  # Signature bytes

    result = trust_manager.verify_vds_nc_signature(kid, message, signature)
    print(f"Verification result: {result}")

    # Check trust list freshness
    freshness = trust_manager.validate_trust_list_freshness()
    print(f"Trust list freshness: {freshness}")

    # Get statistics
    if trust_manager.trust_list:
        stats = trust_manager.trust_list.get_stats()
        print(f"Trust list stats: {stats}")

    # Stop periodic refresh
    await trust_manager.stop_periodic_refresh()


if __name__ == "__main__":
    import asyncio

    asyncio.run(example_verifier_workflow())
