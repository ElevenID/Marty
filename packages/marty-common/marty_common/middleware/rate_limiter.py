"""
Rate limiting middleware for Marty services.

Provides rate limiting functionality to protect services from excessive requests
and ensure fair resource allocation across clients.
"""

from __future__ import annotations

import hashlib
import grpc  # Needed for StatusCode in interceptor
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RateLimitRule:
    """Rate limiting rule configuration."""

    requests_per_second: float
    requests_per_minute: float
    requests_per_hour: float
    burst_size: int = 10
    client_type: str = "default"
    priority: int = 0  # Higher priority overrides lower


@dataclass
class RateLimitStatus:
    """Current rate limiting status for a client."""

    allowed: bool
    remaining_requests: int
    reset_time: float
    retry_after: float | None = None
    rule_applied: str | None = None


@dataclass
class ClientBucket:
    """Token bucket for a specific client."""

    tokens: float
    last_refill: float
    requests_in_window: deque = field(default_factory=deque)
    total_requests: int = 0

    def __post_init__(self):
        if not hasattr(self, "requests_in_window"):
            self.requests_in_window = deque()


class RateLimitBackend(ABC):
    """Abstract backend for rate limiting storage."""

    @abstractmethod
    def get_client_data(self, client_id: str) -> ClientBucket | None:
        """Get client bucket data."""

    @abstractmethod
    def set_client_data(self, client_id: str, bucket: ClientBucket) -> None:
        """Set client bucket data."""

    @abstractmethod
    def cleanup_expired(self, before_timestamp: float) -> None:
        """Clean up expired client data."""


class MemoryRateLimitBackend(RateLimitBackend):
    """In-memory rate limiting backend."""

    def __init__(self) -> None:
        self._clients: dict[str, ClientBucket] = {}
        self._lock = threading.RLock()

    def get_client_data(self, client_id: str) -> ClientBucket | None:
        """Retrieve client bucket data for the given client ID."""
        with self._lock:
            return self._clients.get(client_id)

    def set_client_data(self, client_id: str, bucket: ClientBucket) -> None:
        """Store client bucket data for the given client ID."""
        with self._lock:
            self._clients[client_id] = bucket

    def cleanup_expired(self, before_timestamp: float) -> None:
        """Remove expired client buckets from memory."""
        with self._lock:
            expired_clients = [
                client_id
                for client_id, bucket in self._clients.items()
                if bucket.last_refill < before_timestamp
            ]
            for client_id in expired_clients:
                del self._clients[client_id]


class RedisRateLimitBackend(RateLimitBackend):
    """Redis-based rate limiting backend."""

    def __init__(self, redis_client, key_prefix: str = "marty:ratelimit:") -> None:
        self.redis = redis_client
        self.key_prefix = key_prefix

    def _get_key(self, client_id: str) -> str:
        return f"{self.key_prefix}{client_id}"

    def get_client_data(self, client_id: str) -> ClientBucket | None:
        try:
            data = self.redis.hgetall(self._get_key(client_id))
            if not data:
                return None

            return ClientBucket(
                tokens=float(data.get("tokens", 0)),
                last_refill=float(data.get("last_refill", 0)),
                total_requests=int(data.get("total_requests", 0)),
                requests_in_window=deque(),  # Simplified for Redis
            )
        except Exception:
            logger.exception("Failed to get client data from Redis")
            return None

    def set_client_data(self, client_id: str, bucket: ClientBucket) -> None:
        try:
            key = self._get_key(client_id)
            data = {
                "tokens": bucket.tokens,
                "last_refill": bucket.last_refill,
                "total_requests": bucket.total_requests,
            }
            self.redis.hset(key, mapping=data)
            self.redis.expire(key, 3600)  # 1 hour TTL
        except Exception:
            logger.exception("Failed to set client data in Redis")

    def cleanup_expired(self, before_timestamp: float) -> None:
        # Redis TTL handles cleanup automatically
        pass


class RateLimiter:
    """Main rate limiter implementation."""

    def __init__(self, backend: RateLimitBackend | None = None) -> None:
        self.backend = backend or MemoryRateLimitBackend()
        self.rules: dict[str, RateLimitRule] = {}
        self.default_rule = RateLimitRule(
            requests_per_second=10, requests_per_minute=600, requests_per_hour=3600, burst_size=20
        )
        self._lock = threading.RLock()
        self._last_cleanup = time.time()

    def add_rule(self, name: str, rule: RateLimitRule) -> None:
        """Add a rate limiting rule."""
        with self._lock:
            self.rules[name] = rule

    def remove_rule(self, name: str) -> None:
        """Remove a rate limiting rule."""
        with self._lock:
            self.rules.pop(name, None)

    def get_rule_for_client(self, client_id: str, client_type: str = "default") -> RateLimitRule:
        """Get the applicable rule for a client."""
        with self._lock:
            # Find matching rules by client type
            matching_rules = [
                rule for rule in self.rules.values() if rule.client_type in (client_type, "default")
            ]

            if not matching_rules:
                return self.default_rule

            # Return highest priority rule
            return max(matching_rules, key=lambda r: r.priority)

    def _refill_bucket(self, bucket: ClientBucket, rule: RateLimitRule, now: float) -> None:
        """Refill the token bucket."""
        time_passed = now - bucket.last_refill
        if time_passed <= 0:
            return

        # Calculate tokens to add based on per-second rate
        tokens_to_add = time_passed * rule.requests_per_second
        bucket.tokens = min(rule.burst_size, bucket.tokens + tokens_to_add)
        bucket.last_refill = now

    def _check_window_limits(
        self, bucket: ClientBucket, rule: RateLimitRule, now: float
    ) -> tuple[bool, float | None]:
        """Check minute and hour window limits."""
        # Clean old requests from window
        minute_ago = now - 60
        hour_ago = now - 3600

        while bucket.requests_in_window and bucket.requests_in_window[0] < hour_ago:
            bucket.requests_in_window.popleft()

        # Count requests in windows
        requests_last_minute = sum(
            1 for req_time in bucket.requests_in_window if req_time >= minute_ago
        )
        requests_last_hour = len(bucket.requests_in_window)

        # Check limits
        if requests_last_minute >= rule.requests_per_minute:
            return False, minute_ago + 60

        if requests_last_hour >= rule.requests_per_hour:
            oldest_in_hour = bucket.requests_in_window[0] if bucket.requests_in_window else now
            return False, oldest_in_hour + 3600

        return True, None

    def check_limit(
        self, client_id: str, client_type: str = "default", request_cost: int = 1
    ) -> RateLimitStatus:
        """Check if a request should be rate limited."""
        now = time.time()

        # Periodic cleanup
        if now - self._last_cleanup > 300:  # 5 minutes
            self.backend.cleanup_expired(now - 3600)
            self._last_cleanup = now

        rule = self.get_rule_for_client(client_id, client_type)
        bucket = self.backend.get_client_data(client_id)

        if bucket is None:
            bucket = ClientBucket(
                tokens=rule.burst_size, last_refill=now, requests_in_window=deque()
            )

        # Refill bucket
        self._refill_bucket(bucket, rule, now)

        # Check token bucket (burst/per-second limit)
        if bucket.tokens < request_cost:
            self.backend.set_client_data(client_id, bucket)
            return RateLimitStatus(
                allowed=False,
                remaining_requests=int(bucket.tokens),
                reset_time=now + (request_cost - bucket.tokens) / rule.requests_per_second,
                retry_after=(request_cost - bucket.tokens) / rule.requests_per_second,
                rule_applied="burst_limit",
            )

        # Check window limits
        window_ok, retry_after_time = self._check_window_limits(bucket, rule, now)
        if not window_ok:
            self.backend.set_client_data(client_id, bucket)
            return RateLimitStatus(
                allowed=False,
                remaining_requests=0,
                reset_time=retry_after_time,
                retry_after=retry_after_time - now if retry_after_time else None,
                rule_applied="window_limit",
            )

        # Allow request - consume tokens
        bucket.tokens -= request_cost
        bucket.requests_in_window.append(now)
        bucket.total_requests += 1

        self.backend.set_client_data(client_id, bucket)

        return RateLimitStatus(
            allowed=True,
            remaining_requests=int(bucket.tokens),
            reset_time=now + (rule.burst_size - bucket.tokens) / rule.requests_per_second,
        )

    def get_client_stats(self, client_id: str) -> dict[str, Any]:
        """Get statistics for a client."""
        bucket = self.backend.get_client_data(client_id)
        if not bucket:
            return {"total_requests": 0, "current_tokens": 0}

        now = time.time()
        hour_ago = now - 3600
        minute_ago = now - 60

        # Clean old requests
        while bucket.requests_in_window and bucket.requests_in_window[0] < hour_ago:
            bucket.requests_in_window.popleft()

        requests_last_minute = sum(
            1 for req_time in bucket.requests_in_window if req_time >= minute_ago
        )
        requests_last_hour = len(bucket.requests_in_window)

        return {
            "total_requests": bucket.total_requests,
            "current_tokens": int(bucket.tokens),
            "requests_last_minute": requests_last_minute,
            "requests_last_hour": requests_last_hour,
            "last_request": bucket.last_refill,
        }


class RateLimitMiddleware:
    """gRPC middleware for rate limiting."""

    def __init__(
        self, rate_limiter: RateLimiter, extract_client_id=None, extract_client_type=None
    ) -> None:
        self.rate_limiter = rate_limiter
        self.extract_client_id = extract_client_id or self._default_extract_client_id
        self.extract_client_type = extract_client_type or self._default_extract_client_type

    def _default_extract_client_id(self, context) -> str:
        """Extract client ID from gRPC context."""
        # Try to get from metadata
        metadata = dict(context.invocation_metadata())

        # Check common headers
        if "client-id" in metadata:
            return metadata["client-id"]
        if "x-client-id" in metadata:
            return metadata["x-client-id"]
        if "authorization" in metadata:
            # Use hash of authorization token
            return hashlib.sha256(metadata["authorization"].encode()).hexdigest()[:16]

        # Fallback to peer address
        peer = context.peer()
        if peer:
            return hashlib.sha256(peer.encode()).hexdigest()[:16]

        return "anonymous"

    def _default_extract_client_type(self, context) -> str:
        """Extract client type from gRPC context."""
        metadata = dict(context.invocation_metadata())
        return metadata.get("client-type", metadata.get("x-client-type", "default"))

    def intercept_service(self, continuation, handler_call_details):
        """Intercept gRPC service calls for rate limiting."""

        def rate_limited_handler(request, context):
            client_id = self.extract_client_id(context)
            client_type = self.extract_client_type(context)

            # Check rate limit
            status = self.rate_limiter.check_limit(client_id, client_type)

            if not status.allowed:
                # Add rate limit headers to response
                context.set_trailing_metadata(
                    [
                        ("x-ratelimit-remaining", str(status.remaining_requests)),
                        ("x-ratelimit-reset", str(int(status.reset_time))),
                    ]
                )

                if status.retry_after:
                    context.set_trailing_metadata([("retry-after", str(int(status.retry_after)))])

                # Abort with rate limit exceeded
                context.abort(
                    grpc.StatusCode.RESOURCE_EXHAUSTED,
                    f"Rate limit exceeded. Rule: {status.rule_applied}",
                )

            # Add rate limit info to successful responses
            context.set_trailing_metadata(
                [
                    ("x-ratelimit-remaining", str(status.remaining_requests)),
                    ("x-ratelimit-reset", str(int(status.reset_time))),
                ]
            )

            # Continue with the request
            return continuation(request, context)

        return rate_limited_handler


def create_default_rate_limiter(redis_client=None) -> RateLimiter:
    """Create a rate limiter with default rules."""
    backend = RedisRateLimitBackend(redis_client) if redis_client else MemoryRateLimitBackend()
    limiter = RateLimiter(backend)

    # Add common rules
    limiter.add_rule(
        "public_api",
        RateLimitRule(
            requests_per_second=5,
            requests_per_minute=300,
            requests_per_hour=1000,
            burst_size=10,
            client_type="public",
            priority=10,
        ),
    )

    limiter.add_rule(
        "authenticated",
        RateLimitRule(
            requests_per_second=20,
            requests_per_minute=1200,
            requests_per_hour=10000,
            burst_size=50,
            client_type="authenticated",
            priority=20,
        ),
    )

    limiter.add_rule(
        "premium",
        RateLimitRule(
            requests_per_second=100,
            requests_per_minute=6000,
            requests_per_hour=50000,
            burst_size=200,
            client_type="premium",
            priority=30,
        ),
    )

    return limiter
