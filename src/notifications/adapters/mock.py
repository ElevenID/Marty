"""
Mock Notification Adapter

Mock adapter for testing push notifications.
Stores notifications in Redis for inspection during E2E tests.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from ..types import ChannelType, DeliveryResult, NotificationPayload

logger = logging.getLogger(__name__)


@dataclass
class MockNotificationConfig:
    """Mock adapter configuration."""
    redis_url: str = "redis://localhost:6379/0"
    notifications_key: str = "test:notifications"
    challenges_key: str = "test:push_challenges"
    # Simulate failures
    fail_rate: float = 0.0  # 0.0 = never fail, 1.0 = always fail
    fail_on_tokens: list[str] = None
    # Response delay simulation
    delay_seconds: float = 0.0
    
    def __post_init__(self):
        if self.fail_on_tokens is None:
            self.fail_on_tokens = []


class MockNotificationAdapter:
    """
    Mock push notification adapter for testing.
    
    Instead of sending to FCM, stores notifications in Redis.
    This allows E2E tests to:
    - Verify notifications were "sent"
    - Retrieve notification content for assertions
    - Simulate push challenges for mobile wallet testing
    
    Features:
    - Store notifications in Redis list
    - Simulate delivery failures
    - Provide test endpoints to retrieve/clear notifications
    - Support push challenge creation for wallet testing
    """
    
    def __init__(
        self,
        config: MockNotificationConfig,
        redis_client: Optional[Any] = None,
    ):
        """
        Initialize the mock adapter.
        
        Args:
            config: Mock adapter configuration
            redis_client: Redis client (async or sync, will be detected)
        """
        self.config = config
        self._redis = redis_client
        self._notifications: list[dict] = []  # Fallback if no Redis
        self._challenges: dict[str, list[dict]] = {}  # device_id -> challenges
    
    async def _get_redis(self):
        """Get or create Redis client."""
        if self._redis is not None:
            return self._redis
        
        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(self.config.redis_url)
            return self._redis
        except ImportError:
            logger.warning("redis package not installed, using in-memory storage")
            return None
    
    async def send(self, payload: NotificationPayload) -> DeliveryResult:
        """
        Mock send a notification.
        
        Instead of sending to FCM, stores in Redis for test inspection.
        
        Args:
            payload: The notification payload
            
        Returns:
            DeliveryResult with success status
        """
        import asyncio
        
        # Simulate network delay if configured
        if self.config.delay_seconds > 0:
            await asyncio.sleep(self.config.delay_seconds)
        
        tokens = payload.target.device_tokens if payload.target else []
        
        if not tokens:
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.FCM,
                success=False,
                error_code="NO_TOKENS",
                error_message="No device tokens provided",
            )
        
        # Check for simulated failures
        if self.config.fail_rate > 0:
            import random
            if random.random() < self.config.fail_rate:
                return DeliveryResult(
                    notification_id=payload.id,
                    channel=ChannelType.FCM,
                    success=False,
                    error_code="SIMULATED_FAILURE",
                    error_message="Simulated delivery failure for testing",
                )
        
        # Check for specific token failures
        failed_tokens = [t for t in tokens if t in self.config.fail_on_tokens]
        if failed_tokens:
            return DeliveryResult(
                notification_id=payload.id,
                channel=ChannelType.FCM,
                success=False,
                error_code="INVALID_TOKEN",
                error_message=f"Simulated invalid tokens: {failed_tokens}",
                metadata={"failed_tokens": failed_tokens},
            )
        
        # Store notification
        notification_record = {
            "id": str(payload.id),
            "title": payload.title,
            "body": payload.body,
            "data": payload.data,
            "event_type": payload.event_type,
            "priority": payload.priority.value if hasattr(payload.priority, 'value') else str(payload.priority),
            "tokens": tokens,
            "organization_id": str(payload.target.organization_id) if payload.target and payload.target.organization_id else None,
            "user_id": payload.target.user_id if payload.target else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "correlation_id": payload.correlation_id,
        }
        
        redis_client = await self._get_redis()
        
        if redis_client:
            # Store in Redis
            await redis_client.lpush(
                self.config.notifications_key,
                json.dumps(notification_record),
            )
            # Keep only last 100 notifications
            await redis_client.ltrim(self.config.notifications_key, 0, 99)
            
            logger.info(f"Mock notification stored: {payload.id} to {len(tokens)} tokens")
        else:
            # Fallback to in-memory
            self._notifications.insert(0, notification_record)
            self._notifications = self._notifications[:100]
        
        return DeliveryResult(
            notification_id=payload.id,
            channel=ChannelType.FCM,
            success=True,
            delivered_at=datetime.now(timezone.utc),
            metadata={
                "mock": True,
                "stored_in": "redis" if redis_client else "memory",
                "token_count": len(tokens),
            },
        )
    
    async def create_push_challenge(
        self,
        device_id: str,
        challenge_data: dict[str, Any],
        ttl_seconds: int = 120,
    ) -> str:
        """
        Create a push challenge for a device.
        
        This simulates a push challenge that would normally be delivered via FCM.
        The mobile wallet can poll for these challenges.
        
        Args:
            device_id: Target device ID
            challenge_data: Challenge payload (nonce, title, question, etc.)
            ttl_seconds: Time-to-live for the challenge
            
        Returns:
            Challenge ID
        """
        from uuid import uuid4
        
        challenge_id = str(uuid4())
        challenge_record = {
            "challenge_id": challenge_id,
            "device_id": device_id,
            "data": challenge_data,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ttl_seconds": ttl_seconds,
            "status": "pending",
        }
        
        redis_client = await self._get_redis()
        
        if redis_client:
            # Store challenge in device-specific list
            key = f"{self.config.challenges_key}:{device_id}"
            await redis_client.lpush(key, json.dumps(challenge_record))
            await redis_client.expire(key, ttl_seconds)
            
            logger.info(f"Push challenge created for device {device_id}: {challenge_id}")
        else:
            # Fallback to in-memory
            if device_id not in self._challenges:
                self._challenges[device_id] = []
            self._challenges[device_id].insert(0, challenge_record)
        
        return challenge_id
    
    async def get_pending_challenges(
        self,
        device_id: str,
    ) -> list[dict[str, Any]]:
        """
        Get pending challenges for a device.
        
        Used by mobile wallet to poll for push challenges.
        
        Args:
            device_id: Device ID to get challenges for
            
        Returns:
            List of pending challenges
        """
        redis_client = await self._get_redis()
        
        if redis_client:
            key = f"{self.config.challenges_key}:{device_id}"
            raw_challenges = await redis_client.lrange(key, 0, -1)
            challenges = [json.loads(c) for c in raw_challenges]
            # Filter to pending only
            return [c for c in challenges if c.get("status") == "pending"]
        else:
            return [
                c for c in self._challenges.get(device_id, [])
                if c.get("status") == "pending"
            ]
    
    async def respond_to_challenge(
        self,
        device_id: str,
        challenge_id: str,
        response: str,
        signature: Optional[str] = None,
        public_key_der: Optional[bytes] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Submit a response to a push challenge.
        
        Args:
            device_id: Device ID
            challenge_id: Challenge ID
            response: Response value (accept/reject)
            signature: Base64-encoded RSA signature over the challenge nonce
            public_key_der: Device's RSA public key (PKCS#1 DER) for verification
            
        Returns:
            Tuple of (success, error_message)
        """
        redis_client = await self._get_redis()
        challenge_data = None
        
        # Find the challenge
        if redis_client:
            key = f"{self.config.challenges_key}:{device_id}"
            raw_challenges = await redis_client.lrange(key, 0, -1)
            
            for i, raw in enumerate(raw_challenges):
                challenge = json.loads(raw)
                if challenge["challenge_id"] == challenge_id:
                    challenge_data = (challenge, i, key)
                    break
        else:
            for challenge in self._challenges.get(device_id, []):
                if challenge["challenge_id"] == challenge_id:
                    challenge_data = (challenge, None, None)
                    break
        
        if not challenge_data:
            return False, "Challenge not found"
        
        challenge, idx, redis_key = challenge_data
        
        # Verify signature if public key provided and response is 'accept'
        if response == "accept" and signature and public_key_der:
            try:
                import base64
                # Import Rust crypto bridge for RSA verification
                try:
                    from marty_backend_common.crypto_bridge import rsa_pkcs1_sha256_verify
                except ImportError:
                    # Fallback: skip verification in environments without Rust bindings
                    logger.warning("Rust crypto bridge not available, skipping signature verification")
                    rsa_pkcs1_sha256_verify = None
                
                if rsa_pkcs1_sha256_verify:
                    signature_bytes = base64.b64decode(signature)
                    nonce = challenge["data"].get("nonce", "")
                    nonce_bytes = nonce.encode("utf-8")
                    
                    is_valid = rsa_pkcs1_sha256_verify(
                        public_key_der,
                        nonce_bytes,
                        signature_bytes,
                    )
                    
                    if not is_valid:
                        logger.warning(f"Invalid signature for challenge {challenge_id}")
                        return False, "Invalid signature"
                    
                    logger.info(f"Signature verified for challenge {challenge_id}")
            except Exception as e:
                logger.error(f"Signature verification failed: {e}")
                return False, f"Signature verification error: {str(e)}"
        
        # Update challenge status
        challenge["status"] = "responded"
        challenge["response"] = response
        challenge["signature"] = signature
        challenge["responded_at"] = datetime.now(timezone.utc).isoformat()
        challenge["signature_verified"] = bool(signature and public_key_der)
        
        if redis_client and redis_key is not None:
            await redis_client.lset(redis_key, idx, json.dumps(challenge))
        
        logger.info(f"Challenge {challenge_id} responded: {response}")
        return True, None
    
    # =========================================================================
    # Test Helper Methods
    # =========================================================================
    
    async def get_all_notifications(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get all stored notifications for test assertions."""
        redis_client = await self._get_redis()
        
        if redis_client:
            raw_notifications = await redis_client.lrange(
                self.config.notifications_key, 0, limit - 1
            )
            return [json.loads(n) for n in raw_notifications]
        else:
            return self._notifications[:limit]
    
    async def get_notifications_for_token(
        self,
        token: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get notifications sent to a specific token."""
        all_notifications = await self.get_all_notifications(limit)
        return [n for n in all_notifications if token in n.get("tokens", [])]
    
    async def get_notifications_for_user(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get notifications sent to a specific user."""
        all_notifications = await self.get_all_notifications(limit)
        return [n for n in all_notifications if n.get("user_id") == user_id]
    
    async def get_notifications_by_event_type(
        self,
        event_type: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get notifications by event type."""
        all_notifications = await self.get_all_notifications(limit)
        return [n for n in all_notifications if n.get("event_type") == event_type]
    
    async def clear_all_notifications(self) -> int:
        """Clear all stored notifications. Returns count deleted."""
        redis_client = await self._get_redis()
        
        if redis_client:
            count = await redis_client.llen(self.config.notifications_key)
            await redis_client.delete(self.config.notifications_key)
            return count
        else:
            count = len(self._notifications)
            self._notifications = []
            return count
    
    async def clear_challenges(self, device_id: Optional[str] = None) -> int:
        """Clear challenges. If device_id provided, only that device."""
        redis_client = await self._get_redis()
        
        if redis_client:
            if device_id:
                key = f"{self.config.challenges_key}:{device_id}"
                count = await redis_client.llen(key)
                await redis_client.delete(key)
                return count
            else:
                # Clear all challenges (match pattern)
                keys = await redis_client.keys(f"{self.config.challenges_key}:*")
                if keys:
                    await redis_client.delete(*keys)
                return len(keys)
        else:
            if device_id:
                count = len(self._challenges.get(device_id, []))
                self._challenges[device_id] = []
                return count
            else:
                count = sum(len(v) for v in self._challenges.values())
                self._challenges = {}
                return count
    
    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


# Factory function to match FCM adapter pattern
def create_mock_adapter(
    redis_url: str = "redis://localhost:6379/0",
    **config_kwargs,
) -> MockNotificationAdapter:
    """
    Create a mock notification adapter.
    
    Args:
        redis_url: Redis connection URL
        **config_kwargs: Additional config options
        
    Returns:
        Configured MockNotificationAdapter
    """
    config = MockNotificationConfig(
        redis_url=redis_url,
        **config_kwargs,
    )
    return MockNotificationAdapter(config)
