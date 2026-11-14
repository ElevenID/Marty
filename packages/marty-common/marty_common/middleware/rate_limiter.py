"""
Rate limiting middleware for Marty services.

Provides rate limiting functionality to protect services from excessive requests
and ensure fair resource allocation across clients.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import grpc
from redis.exceptions import RedisError, WatchError

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

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Reject rules that cannot produce a finite admission time."""
        for name in ("requests_per_second", "requests_per_minute", "requests_per_hour"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if isinstance(self.burst_size, bool) or not isinstance(self.burst_size, int) or self.burst_size < 1:
            raise ValueError("burst_size must be a positive integer")


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
    requests_in_window: deque[float] = field(default_factory=deque)
    total_requests: int = 0
    expires_at: float | None = None
    updated_at: float | None = None


class RateLimitBackendError(RuntimeError):
    """Storage could not establish an admission decision; callers must not allow it."""


BucketUpdate = Callable[[ClientBucket | None], tuple[ClientBucket, RateLimitStatus]]


class RateLimitBackend(ABC):
    """Abstract backend for rate limiting storage."""

    # Retain compatibility with existing in-process get/set backend subclasses.
    # Distributed backends must override update_client_data atomically.
    _update_lock = threading.RLock()

    @abstractmethod
    def get_client_data(self, client_id: str) -> ClientBucket | None:
        """Get client bucket data."""

    @abstractmethod
    def set_client_data(self, client_id: str, bucket: ClientBucket) -> None:
        """Set client bucket data."""

    @abstractmethod
    def cleanup_expired(self, before_timestamp: float) -> None:
        """Clean up expired client data."""

    def update_client_data(self, client_id: str, update: BucketUpdate) -> RateLimitStatus:
        """Apply admission atomically within this process for legacy backends."""
        with self._update_lock:
            bucket, status = update(self.get_client_data(client_id))
            self.set_client_data(client_id, bucket)
            return status


class MemoryRateLimitBackend(RateLimitBackend):
    """In-memory rate limiting backend."""

    def __init__(self) -> None:
        self._clients: dict[str, ClientBucket] = {}
        self._lock = threading.RLock()

    def get_client_data(self, client_id: str) -> ClientBucket | None:
        """Retrieve client bucket data for the given client ID."""
        with self._lock:
            bucket = self._clients.get(client_id)
            return self._copy_bucket(bucket) if bucket is not None else None

    def set_client_data(self, client_id: str, bucket: ClientBucket) -> None:
        """Store client bucket data for the given client ID."""
        with self._lock:
            self._clients[client_id] = self._copy_bucket(bucket)

    @staticmethod
    def _copy_bucket(bucket: ClientBucket) -> ClientBucket:
        return ClientBucket(
            bucket.tokens,
            bucket.last_refill,
            deque(bucket.requests_in_window),
            bucket.total_requests,
            bucket.expires_at,
            bucket.updated_at,
        )

    def update_client_data(self, client_id: str, update: BucketUpdate) -> RateLimitStatus:
        with self._lock:
            bucket, status = update(self.get_client_data(client_id))
            self.set_client_data(client_id, bucket)
            return status

    def cleanup_expired(self, before_timestamp: float) -> None:
        """Remove expired client buckets from memory."""
        with self._lock:
            expired_clients = [
                client_id
                for client_id, bucket in self._clients.items()
                if bucket.last_refill < before_timestamp
                and (bucket.expires_at is None or bucket.expires_at <= before_timestamp + 3600)
            ]
            for client_id in expired_clients:
                del self._clients[client_id]


class RedisRateLimitBackend(RateLimitBackend):
    """Redis storage with optimistic transactions and explicit failure semantics."""

    def __init__(self, redis_client, key_prefix: str = "marty:ratelimit:", *, max_retries: int = 32) -> None:
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 1:
            raise ValueError("max_retries must be a positive integer")
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.max_retries = max_retries

    def _get_key(self, client_id: str) -> str:
        return f"{self.key_prefix}{client_id}"

    def get_client_data(self, client_id: str) -> ClientBucket | None:
        try:
            return self._decode_bucket(self.redis.hgetall(self._get_key(client_id)))
        except RedisError as exc:
            raise RateLimitBackendError("Could not read rate-limit storage") from exc

    @staticmethod
    def _decode_bucket(data) -> ClientBucket | None:
        if not data:
            return None
        try:
            fields = {key.decode() if isinstance(key, bytes) else key: value for key, value in data.items()}
            history = json.loads(fields["requests_in_window"])
            if not isinstance(history, list):
                raise ValueError("Request history must be a list")
            timestamps = [float(value) for value in history]
            bucket = ClientBucket(
                tokens=float(fields["tokens"]),
                last_refill=float(fields["last_refill"]),
                total_requests=int(fields["total_requests"]),
                requests_in_window=deque(timestamps),
                expires_at=float(fields["expires_at"]) if "expires_at" in fields else None,
                updated_at=float(fields["updated_at"]) if "updated_at" in fields else None,
            )
            values = [bucket.tokens, bucket.last_refill, *timestamps]
            if bucket.expires_at is not None:
                values.append(bucket.expires_at)
                if bucket.expires_at < bucket.last_refill:
                    raise ValueError("Bucket expiry precedes refill")
            if bucket.updated_at is not None:
                values.append(bucket.updated_at)
            if any(not math.isfinite(value) or value < 0 for value in values):
                raise ValueError("Bucket values must be finite and nonnegative")
            if (
                bucket.total_requests < len(timestamps)
                or timestamps != sorted(timestamps)
                or (timestamps and timestamps[-1] > bucket.last_refill)
            ):
                raise ValueError("Request history is inconsistent")
            return bucket
        except (KeyError, TypeError, ValueError, UnicodeError, OverflowError) as exc:
            # Old hashes without request history cannot prove window admission.
            # Fail closed until they expire rather than silently resetting limits.
            raise RateLimitBackendError("Rate-limit storage contains an incomplete or invalid bucket") from exc

    @staticmethod
    def _write_bucket(pipe, key: str, bucket: ClientBucket) -> None:
        expires_at = bucket.expires_at if bucket.expires_at is not None else bucket.last_refill + 3600
        updated_at = bucket.updated_at if bucket.updated_at is not None else bucket.last_refill
        pipe.hset(
            key,
            mapping={
                "tokens": bucket.tokens,
                "last_refill": bucket.last_refill,
                "total_requests": bucket.total_requests,
                "requests_in_window": json.dumps(list(bucket.requests_in_window), allow_nan=False),
                "expires_at": expires_at,
                "updated_at": updated_at,
            },
        )
        # Preserve slow-refilling buckets until a new full bucket is equivalent.
        pipe.expire(key, max(3600, math.ceil(expires_at - updated_at)))

    def set_client_data(self, client_id: str, bucket: ClientBucket) -> None:
        try:
            with self.redis.pipeline() as pipe:
                self._write_bucket(pipe, self._get_key(client_id), bucket)
                pipe.execute()
        except RedisError as exc:
            raise RateLimitBackendError("Could not write rate-limit storage") from exc

    def update_client_data(self, client_id: str, update: BucketUpdate) -> RateLimitStatus:
        key = self._get_key(client_id)
        for _ in range(self.max_retries):
            try:
                with self.redis.pipeline() as pipe:
                    pipe.watch(key)
                    bucket, status = update(self._decode_bucket(pipe.hgetall(key)))
                    pipe.multi()
                    self._write_bucket(pipe, key, bucket)
                    pipe.execute()
                    return status
            except WatchError:
                continue
            except RedisError as exc:
                raise RateLimitBackendError("Could not update rate-limit storage") from exc
        raise RateLimitBackendError("Rate-limit storage remained busy after bounded retries")

    def cleanup_expired(self, before_timestamp: float) -> None:
        # Redis TTL handles cleanup automatically
        pass


class RateLimiter:
    """Main rate limiter implementation."""

    def __init__(self, backend: RateLimitBackend | None = None, *, clock: Callable[[], float] | None = None) -> None:
        self.backend = backend if backend is not None else MemoryRateLimitBackend()
        self.rules: dict[str, RateLimitRule] = {}
        self.default_rule = RateLimitRule(
            requests_per_second=10, requests_per_minute=600, requests_per_hour=3600, burst_size=20
        )
        self._lock = threading.RLock()
        self._clock = clock or time.time
        self._last_cleanup = self._clock()

    def add_rule(self, name: str, rule: RateLimitRule) -> None:
        """Add a rate limiting rule."""
        rule.validate()
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
            matching_rules = [rule for rule in self.rules.values() if rule.client_type in (client_type, "default")]

            if not matching_rules:
                return self.default_rule

            # Return highest priority rule
            return max(matching_rules, key=lambda r: r.priority)

    def _refill_bucket(self, bucket: ClientBucket, rule: RateLimitRule, now: float) -> None:
        """Refill the token bucket."""
        tokens_to_add = max(0, now - bucket.last_refill) * rule.requests_per_second
        bucket.tokens = min(rule.burst_size, bucket.tokens + tokens_to_add)
        bucket.last_refill = max(now, bucket.last_refill)

    def _check_window_limits(self, bucket: ClientBucket, rule: RateLimitRule, now: float) -> tuple[bool, float | None]:
        """Check minute and hour window limits."""
        # Clean old requests from window
        minute_ago = now - 60
        hour_ago = now - 3600

        while bucket.requests_in_window and bucket.requests_in_window[0] <= hour_ago:
            bucket.requests_in_window.popleft()

        # Count requests in windows
        minute_requests = [stamp for stamp in bucket.requests_in_window if stamp > minute_ago]
        retry_times = []
        for requests, limit, window in (
            (minute_requests, rule.requests_per_minute, 60),
            (list(bucket.requests_in_window), rule.requests_per_hour, 3600),
        ):
            if len(requests) >= limit:
                retry_times.append(requests[len(requests) - math.ceil(limit)] + window)
        return (False, max(retry_times)) if retry_times else (True, None)

    def check_limit(self, client_id: str, client_type: str = "default", request_cost: int = 1) -> RateLimitStatus:
        """Check if a request should be rate limited."""
        if isinstance(request_cost, bool) or not isinstance(request_cost, int) or request_cost < 1:
            raise ValueError("request_cost must be a positive integer")
        rule = self.get_rule_for_client(client_id, client_type)
        rule.validate()
        if request_cost > rule.burst_size:
            raise ValueError("request_cost cannot exceed burst_size")
        now = self._clock()

        # Periodic cleanup
        with self._lock:
            if now - self._last_cleanup > 300:  # 5 minutes
                self.backend.cleanup_expired(now - 3600)
                self._last_cleanup = now
        return self.backend.update_client_data(client_id, lambda bucket: self._admit(bucket, rule, now, request_cost))

    def _admit(
        self, bucket: ClientBucket | None, rule: RateLimitRule, now: float, request_cost: int
    ) -> tuple[ClientBucket, RateLimitStatus]:
        if bucket is None:
            bucket = ClientBucket(tokens=rule.burst_size, last_refill=now, requests_in_window=deque())

        # A wall-clock adjustment must not create tokens or unordered history.
        observed_now = now
        bucket.updated_at = observed_now
        now = max(now, bucket.last_refill)
        self._refill_bucket(bucket, rule, now)
        window_ok, window_reset = self._check_window_limits(bucket, rule, now)
        burst_reset = now + max(0, request_cost - bucket.tokens) / rule.requests_per_second
        bucket.expires_at = now + max(3600, (rule.burst_size - bucket.tokens) / rule.requests_per_second)
        if burst_reset > now or not window_ok:
            reset_time = max(burst_reset, window_reset or now)
            return bucket, RateLimitStatus(
                allowed=False,
                remaining_requests=0 if not window_ok else int(bucket.tokens),
                reset_time=reset_time,
                retry_after=reset_time - observed_now,
                rule_applied="window_limit"
                if window_reset is not None and window_reset >= burst_reset
                else "burst_limit",
            )

        # Allow request - consume tokens
        bucket.tokens -= request_cost
        bucket.requests_in_window.append(now)
        bucket.total_requests += 1

        bucket.expires_at = now + max(3600, (rule.burst_size - bucket.tokens) / rule.requests_per_second)
        return bucket, RateLimitStatus(
            allowed=True,
            remaining_requests=int(bucket.tokens),
            reset_time=now + (rule.burst_size - bucket.tokens) / rule.requests_per_second,
        )

    def get_client_stats(self, client_id: str) -> dict[str, Any]:
        """Get statistics for a client."""
        bucket = self.backend.get_client_data(client_id)
        if not bucket:
            return {"total_requests": 0, "current_tokens": 0}

        now = self._clock()
        hour_ago = now - 3600
        minute_ago = now - 60

        # Clean old requests
        while bucket.requests_in_window and bucket.requests_in_window[0] <= hour_ago:
            bucket.requests_in_window.popleft()

        requests_last_minute = sum(1 for req_time in bucket.requests_in_window if req_time > minute_ago)
        requests_last_hour = len(bucket.requests_in_window)

        return {
            "total_requests": bucket.total_requests,
            "current_tokens": int(bucket.tokens),
            "requests_last_minute": requests_last_minute,
            "requests_last_hour": requests_last_hour,
            "last_request": bucket.last_refill,
        }


class RateLimitMiddleware(grpc.ServerInterceptor):
    """Synchronous gRPC interceptor: one admission per RPC, including streams."""

    def __init__(self, rate_limiter: RateLimiter, extract_client_id=None, extract_client_type=None) -> None:
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
        """Preserve the resolved handler's serializers and streaming cardinality."""
        handler = continuation(handler_call_details)
        if handler is None:
            return None
        if handler.request_streaming and handler.response_streaming:
            behavior, factory = handler.stream_stream, grpc.stream_stream_rpc_method_handler
        elif handler.request_streaming:
            behavior, factory = handler.stream_unary, grpc.stream_unary_rpc_method_handler
        elif handler.response_streaming:
            behavior, factory = handler.unary_stream, grpc.unary_stream_rpc_method_handler
        else:
            behavior, factory = handler.unary_unary, grpc.unary_unary_rpc_method_handler

        def rate_limited_handler(request, context):
            client_id = self.extract_client_id(context)
            client_type = self.extract_client_type(context)

            try:
                status = self.rate_limiter.check_limit(client_id, client_type)
            except RateLimitBackendError:
                logger.warning("Rate-limit storage unavailable; rejecting RPC")
                context.abort(grpc.StatusCode.UNAVAILABLE, "Rate-limit storage is unavailable")
            metadata = [
                ("x-ratelimit-remaining", str(status.remaining_requests)),
                ("x-ratelimit-reset", str(math.ceil(status.reset_time))),
            ]
            if status.retry_after is not None:
                metadata.append(("retry-after", str(math.ceil(status.retry_after))))
            context.set_trailing_metadata(metadata)
            if not status.allowed:
                context.abort(
                    grpc.StatusCode.RESOURCE_EXHAUSTED,
                    f"Rate limit exceeded. Rule: {status.rule_applied}",
                )

            return behavior(request, context)

        return factory(
            rate_limited_handler,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )


def create_default_rate_limiter(redis_client=None) -> RateLimiter:
    """Create a rate limiter with default rules."""
    backend = RedisRateLimitBackend(redis_client) if redis_client is not None else MemoryRateLimitBackend()
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
