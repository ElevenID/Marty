"""Compatibility facade for the shared retry policy and types.

Keep the historical enhanced metrics namespace separate from basic decorators.
"""

from __future__ import annotations

import logging
from typing import Any

from .retry import (
    RetryConfig,
    RetryMetrics,
    _create_retry_policy,
)
from .retry import (
    is_retryable_exception as is_retryable_exception_enhanced,
)

logger = logging.getLogger(__name__)
_retry_metrics: dict[str, RetryMetrics] = {}


def get_retry_metrics(name: str) -> RetryMetrics:
    """Get the historical enhanced namespace's metric history."""
    if name not in _retry_metrics:
        _retry_metrics[name] = RetryMetrics()
    return _retry_metrics[name]


def get_all_retry_metrics() -> dict[str, dict[str, Any]]:
    """Return enhanced metric histories without merging the basic registry."""
    return {name: metrics.get_stats() for name, metrics in _retry_metrics.items()}


def create_retry_policy_enhanced(
    config: RetryConfig | None = None, name: str | None = None, enable_logging: bool = True
) -> Any:
    """Use the canonical policy with the existing enhanced logger/predicate."""
    return _create_retry_policy(
        config, name, enable_logging, is_retryable_exception_enhanced, logger
    )


__all__ = [
    "RetryConfig", "RetryMetrics", "create_retry_policy_enhanced",
    "get_all_retry_metrics", "get_retry_metrics", "is_retryable_exception_enhanced",
]
