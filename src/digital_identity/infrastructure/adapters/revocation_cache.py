"""
Revocation Cache Adapter using Redis.

Provides caching for revocation check results with TTL support
to enable offline grace period enforcement.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RevocationCacheEntry:
    """
    Cached revocation check result.
    
    Stores the result of a revocation check along with metadata
    for offline grace period enforcement.
    """
    
    certificate_fingerprint: str
    is_revoked: bool
    check_timestamp: datetime
    revocation_timestamp: datetime | None = None
    reason: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "certificate_fingerprint": self.certificate_fingerprint,
            "is_revoked": self.is_revoked,
            "check_timestamp": self.check_timestamp.isoformat(),
            "revocation_timestamp": self.revocation_timestamp.isoformat() if self.revocation_timestamp else None,
            "reason": self.reason,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RevocationCacheEntry:
        """Deserialize from dictionary."""
        return cls(
            certificate_fingerprint=data["certificate_fingerprint"],
            is_revoked=data["is_revoked"],
            check_timestamp=datetime.fromisoformat(data["check_timestamp"]),
            revocation_timestamp=datetime.fromisoformat(data["revocation_timestamp"]) if data.get("revocation_timestamp") else None,
            reason=data.get("reason"),
        )


class RevocationCacheAdapter:
    """
    Redis-backed cache for revocation check results.
    
    Uses organization-scoped keys with hash tags for Redis Cluster support:
    {org_id}:revocation:{cert_fingerprint}
    """
    
    def __init__(self, cache_manager: Any, default_ttl: int = 3600):
        """
        Initialize revocation cache.
        
        Args:
            cache_manager: MMF ICacheManager implementation (e.g., RedisCacheManager)
            default_ttl: Default TTL in seconds (default: 1 hour)
        """
        self.cache_manager = cache_manager
        self.default_ttl = default_ttl
    
    def _make_key(self, organization_id: str, certificate_fingerprint: str) -> str:
        """
        Generate cache key with hash tag for Redis Cluster.
        
        Format: {org_id}:revocation:{cert_fingerprint}
        Hash tag ensures all keys for an org are on same cluster node.
        """
        return f"{{{organization_id}}}:revocation:{certificate_fingerprint}"
    
    def _compute_fingerprint(self, certificate_der: bytes) -> str:
        """Compute SHA-256 fingerprint of certificate."""
        return hashlib.sha256(certificate_der).hexdigest()
    
    async def get(
        self,
        organization_id: str,
        certificate_der: bytes,
    ) -> RevocationCacheEntry | None:
        """
        Get cached revocation result.
        
        Args:
            organization_id: Organization ID for key scoping
            certificate_der: DER-encoded certificate
            
        Returns:
            Cached entry or None if not found
        """
        fingerprint = self._compute_fingerprint(certificate_der)
        key = self._make_key(organization_id, fingerprint)
        
        try:
            value = await self.cache_manager.get(key)
            if value is None:
                return None
            
            # Parse JSON
            data = json.loads(value.decode() if isinstance(value, bytes) else value)
            return RevocationCacheEntry.from_dict(data)
            
        except Exception as e:
            logger.warning(f"Failed to get revocation cache entry for {fingerprint}: {e}")
            return None
    
    async def set(
        self,
        organization_id: str,
        certificate_der: bytes,
        is_revoked: bool,
        revocation_timestamp: datetime | None = None,
        reason: str | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        """
        Store revocation check result.
        
        Args:
            organization_id: Organization ID for key scoping
            certificate_der: DER-encoded certificate
            is_revoked: Whether certificate is revoked
            revocation_timestamp: When certificate was revoked (if revoked)
            reason: Revocation reason (if revoked)
            ttl_seconds: TTL override (default: use configured TTL)
        """
        fingerprint = self._compute_fingerprint(certificate_der)
        key = self._make_key(organization_id, fingerprint)
        
        entry = RevocationCacheEntry(
            certificate_fingerprint=fingerprint,
            is_revoked=is_revoked,
            check_timestamp=datetime.now(timezone.utc),
            revocation_timestamp=revocation_timestamp,
            reason=reason,
        )
        
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        
        try:
            value = json.dumps(entry.to_dict())
            await self.cache_manager.set(key, value, ttl_seconds=ttl)
            logger.debug(f"Cached revocation result for {fingerprint}: is_revoked={is_revoked}, ttl={ttl}s")
            
        except Exception as e:
            logger.error(f"Failed to cache revocation result for {fingerprint}: {e}")
            # Don't raise - caching is best-effort
    
    async def delete(
        self,
        organization_id: str,
        certificate_der: bytes,
    ) -> bool:
        """
        Delete cached revocation result.
        
        Args:
            organization_id: Organization ID for key scoping
            certificate_der: DER-encoded certificate
            
        Returns:
            True if deleted, False if not found
        """
        fingerprint = self._compute_fingerprint(certificate_der)
        key = self._make_key(organization_id, fingerprint)
        
        try:
            return await self.cache_manager.delete(key)
        except Exception as e:
            logger.warning(f"Failed to delete revocation cache entry for {fingerprint}: {e}")
            return False
    
    async def is_within_grace_period(
        self,
        organization_id: str,
        certificate_der: bytes,
        grace_period: timedelta,
    ) -> tuple[bool, RevocationCacheEntry | None]:
        """
        Check if cached entry exists and is within offline grace period.
        
        Args:
            organization_id: Organization ID for key scoping
            certificate_der: DER-encoded certificate
            grace_period: Grace period duration
            
        Returns:
            Tuple of (is_within_grace_period, cached_entry)
        """
        entry = await self.get(organization_id, certificate_der)
        
        if entry is None:
            return False, None
        
        age = datetime.now(timezone.utc) - entry.check_timestamp
        within_grace = age <= grace_period
        
        return within_grace, entry


def create_revocation_cache_adapter(
    redis_host: str = "localhost",
    redis_port: int = 6379,
    redis_db: int = 0,
    default_ttl: int = 3600,
    max_connections: int = 50,
) -> RevocationCacheAdapter:
    """
    Factory function to create RevocationCacheAdapter with Redis backend.
    
    Args:
        redis_host: Redis server host
        redis_port: Redis server port
        redis_db: Redis database number
        default_ttl: Default cache TTL in seconds
        max_connections: Maximum Redis connection pool size
        
    Returns:
        RevocationCacheAdapter instance
    """
    import redis.asyncio as aioredis
    from mmf.adapters.cache import RedisCacheManager
    from mmf.core.cache import PrefixConfig
    
    # Create connection pool
    pool = aioredis.ConnectionPool(
        host=redis_host,
        port=redis_port,
        db=redis_db,
        max_connections=max_connections,
        decode_responses=False,  # We handle encoding/decoding
    )
    
    redis_client = aioredis.Redis(connection_pool=pool)
    
    # Create cache manager with minimal prefix (we manage keys ourselves)
    prefix_config = PrefixConfig(service="marty", module="revocation")
    cache_manager = RedisCacheManager(redis_client, prefix_config, metrics=None)
    
    return RevocationCacheAdapter(cache_manager, default_ttl=default_ttl)
