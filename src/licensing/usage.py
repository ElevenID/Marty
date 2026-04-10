"""
Usage Metering for License Enforcement

Tracks API call counts per organization with monthly rollover.
Uses Redis INCR with TTL keys when available, falls back to
in-memory counters for single-instance deployments.
"""
from __future__ import annotations

import calendar
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _current_month_key(org_id: str) -> str:
    """Build Redis key like usage:{org_id}:2025-01."""
    now = datetime.now(timezone.utc)
    return f"usage:{org_id}:{now.strftime('%Y-%m')}"


def _month_key(org_id: str, month: str) -> str:
    """Build Redis key for a specific month (YYYY-MM format)."""
    return f"usage:{org_id}:{month}"


def _seconds_until_month_end() -> int:
    """Seconds remaining until the end of the current UTC month."""
    now = datetime.now(timezone.utc)
    _, last_day = calendar.monthrange(now.year, now.month)
    end = now.replace(day=last_day, hour=23, minute=59, second=59)
    return max(int((end - now).total_seconds()), 1)


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


class UsageMeter:
    """
    API call counter with Redis storage and in-memory fallback.

    Redis keys: ``usage:{org_id}:{YYYY-MM}`` with TTL set to end-of-month+1day.
    """

    def __init__(self, redis_client: Any | None = None):
        self._redis = redis_client
        # In-memory fallback: {key: count}
        self._mem: dict[str, int] = defaultdict(int)

    @property
    def has_redis(self) -> bool:
        return self._redis is not None

    async def increment(self, org_id: str) -> int:
        """Increment the current month's counter. Returns new count."""
        key = _current_month_key(org_id)

        # Always track in-memory so we have a floor if Redis fails
        self._mem[key] += 1
        mem_count = self._mem[key]

        if self._redis is not None:
            try:
                count = await self._redis.incr(key)
                if count == 1:
                    # First call this month — set TTL
                    ttl = _seconds_until_month_end() + 86400  # +1 day buffer
                    await self._redis.expire(key, ttl)
                redis_count = int(count)
                # Keep in-memory in sync with Redis (Redis is authoritative)
                self._mem[key] = max(mem_count, redis_count)
                return redis_count
            except Exception:
                logger.warning("Redis unavailable, falling back to in-memory counter")

        return mem_count

    async def get_usage(self, org_id: str, month: str | None = None) -> int:
        """Get usage count for a given month (default: current)."""
        m = month or _current_month()
        key = _month_key(org_id, m)
        mem_count = self._mem.get(key, 0)

        if self._redis is not None:
            try:
                val = await self._redis.get(key)
                redis_count = int(val) if val is not None else 0
                # Return the higher of the two to avoid under-counting
                return max(redis_count, mem_count)
            except Exception:
                logger.warning("Redis unavailable, falling back to in-memory counter")

        return mem_count

    async def reset(self, org_id: str, month: str | None = None) -> None:
        """Admin reset — zero out a month's counter."""
        m = month or _current_month()
        key = _month_key(org_id, m)

        if self._redis is not None:
            try:
                await self._redis.delete(key)
            except Exception:
                logger.warning("Redis unavailable for reset")

        self._mem.pop(key, None)
