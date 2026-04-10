"""
Challenge Store

Redis-backed storage for push authentication challenges.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class ChallengeStoreConfig:
    """Challenge store configuration."""
    redis_url: str = "redis://localhost:6379/0"
    challenges_key: str = "push_challenges"


class ChallengeStore:
    """
    Redis-backed storage for push authentication challenges.
    
    Stores challenges with TTL for automatic expiration.
    
    Multi-Tenant Redis Key Pattern (with hash tags for Redis Cluster):
      {org:{organization_id}}:challenges:{device_id}:{challenge_id}
    
    Hash tags {...} ensure all challenges for an organization hash to the same
    Redis Cluster slot, enabling efficient multi-key operations and org-scoped queries.
    
    Example keys:
      {org:550e8400}:challenges:device-123:abc-def-ghi
      {org:550e8400}:challenges:device-456:xyz-789-012
    """
    
    def __init__(
        self,
        config: ChallengeStoreConfig,
        redis_client: Optional[Any] = None,
    ):
        """
        Initialize the challenge store.
        
        Args:
            config: Challenge store configuration
            redis_client: Redis client (async)
        """
        self.config = config
        self._redis = redis_client
    
    async def _get_redis(self):
        """Get or create Redis client."""
        if self._redis is not None:
            return self._redis
        
        try:
            import redis.asyncio as redis
            pool = redis.ConnectionPool.from_url(
                self.config.redis_url, max_connections=20
            )
            self._redis = redis.Redis(connection_pool=pool)
            return self._redis
        except ImportError:
            raise RuntimeError(
                "redis package is required for ChallengeStore. "
                "Install with: pip install redis"
            )
    
    async def create_challenge(
        self,
        device_id: str,
        challenge_data: dict[str, Any],
        ttl_seconds: int = 120,
        organization_id: Optional[str] = None,
    ) -> str:
        """
        Create and store a push challenge.
        
        Args:
            device_id: Target device ID
            challenge_data: Challenge payload
            ttl_seconds: Time-to-live in seconds
            organization_id: Organization context for multi-tenant isolation (required for production)
            
        Returns:
            Challenge ID
        """
        redis = await self._get_redis()
        
        challenge_id = challenge_data.get("challenge_id", str(uuid4()))
        
        # Multi-tenant key pattern with hash tags for Redis Cluster compatibility
        # Hash tag {org:...} ensures all org challenges hash to same slot
        if organization_id:
            key = f"{{org:{organization_id}}}:{self.config.challenges_key}:{device_id}:{challenge_id}"
        else:
            # Fallback for backwards compatibility (deprecated - should always provide org_id)
            key = f"{self.config.challenges_key}:{device_id}:{challenge_id}"
            logger.warning(
                f"Challenge created without organization_id for device {device_id}. "
                "This is deprecated and breaks multi-tenant isolation."
            )
        
        record = {
            "challenge_id": challenge_id,
            "device_id": device_id,
            "organization_id": organization_id,
            "data": challenge_data,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ttl_seconds": ttl_seconds,
        }
        
        await redis.setex(key, ttl_seconds, json.dumps(record))
        logger.debug(f"Created challenge {challenge_id} for device {device_id} in org {organization_id}")
        
        return challenge_id
    
    async def get_pending_challenges(
        self,
        device_id: str,
        consume: bool = True,
        organization_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Get pending challenges for a device.
        
        Args:
            device_id: Device ID to get challenges for
            consume: If True, delete challenges after retrieval
            organization_id: Organization context for scoped query (recommended)
            
        Returns:
            List of pending challenges
        """
        redis = await self._get_redis()
        
        # Multi-tenant pattern: scan within organization scope
        if organization_id:
            pattern = f"{{org:{organization_id}}}:{self.config.challenges_key}:{device_id}:*"
        else:
            # Fallback for backwards compatibility - scans all orgs (inefficient)
            pattern = f"*:{self.config.challenges_key}:{device_id}:*"
            logger.warning(
                f"Scanning challenges without organization_id for device {device_id}. "
                "This may return challenges from multiple orgs and is inefficient."
            )
        
        challenges = []
        
        async for key in redis.scan_iter(match=pattern):
            data = await redis.get(key)
            if data:
                challenges.append(json.loads(data))
                if consume:
                    await redis.delete(key)
        
        return challenges
    
    async def get_challenge(
        self,
        device_id: str,
        challenge_id: str,
        organization_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Get a specific challenge."""
        redis = await self._get_redis()
        
        # Try org-scoped key first, fall back to legacy key
        if organization_id:
            key = f"{{org:{organization_id}}}:{self.config.challenges_key}:{device_id}:{challenge_id}"
        else:
            key = f"{self.config.challenges_key}:{device_id}:{challenge_id}"
        
        data = await redis.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    async def respond_to_challenge(
        self,
        device_id: str,
        challenge_id: str,
        response: str,
        signature: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Record a response to a challenge.
        
        Args:
            device_id: Device ID
            challenge_id: Challenge ID
            response: 'accept' or 'reject'
            signature: Optional cryptographic signature
            organization_id: Organization context for scoped lookup
            
        Returns:
            Tuple of (success, error_message)
        """
        redis = await self._get_redis()
        
        # Try org-scoped key first, fall back to legacy key
        if organization_id:
            key = f"{{org:{organization_id}}}:{self.config.challenges_key}:{device_id}:{challenge_id}"
        else:
            key = f"{self.config.challenges_key}:{device_id}:{challenge_id}"
        
        data = await redis.get(key)
        
        if not data:
            return False, "Challenge not found or expired"
        
        # Delete the challenge (consumed)
        await redis.delete(key)
        
        logger.info(f"Challenge {challenge_id} responded with: {response} (org: {organization_id})")
        return True, None
    
    async def clear_challenges(
        self,
        device_id: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> int:
        """
        Clear challenges.
        
        Args:
            device_id: If provided, clear only for this device
            organization_id: If provided, clear only for this organization
            
        Returns:
            Number of challenges cleared
        """
        redis = await self._get_redis()
        
        # Build pattern based on scope
        if organization_id and device_id:
            pattern = f"{{org:{organization_id}}}:{self.config.challenges_key}:{device_id}:*"
        elif organization_id:
            pattern = f"{{org:{organization_id}}}:{self.config.challenges_key}:*"
        elif device_id:
            pattern = f"*:{self.config.challenges_key}:{device_id}:*"
        else:
            pattern = f"*:{self.config.challenges_key}:*"
        
        count = 0
        async for key in redis.scan_iter(match=pattern):
            await redis.delete(key)
            count += 1
        
        return count
