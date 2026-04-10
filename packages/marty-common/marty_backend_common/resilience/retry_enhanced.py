"""Enhanced retry helpers with comprehensive strategies and monitoring."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from tenacity import (
    after_log,
    before_log,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
    wait_exponential_jitter,
    wait_fixed,
    wait_random,
)
from tenacity import retry as tenacity_retry  # type: ignore[import]

from .error_codes import TransientBackendError, exception_is_transient

logger = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior with comprehensive options."""

    max_attempts: int = 5
    base_delay: float = 0.2
    max_delay: float = 3.0
    jitter: bool = True
    exponential_backoff: bool = True
    max_total_delay: float = 30.0
    retry_on_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: (TransientBackendError, ConnectionError, TimeoutError)
    )


class RetryMetrics:
    """Collect metrics about retry attempts."""

    def __init__(self) -> None:
        self.total_attempts = 0
        self.total_retries = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.last_attempt_time = 0.0

    def record_attempt(self) -> None:
        """Record a retry attempt."""
        self.total_attempts += 1
        self.last_attempt_time = time.time()

    def record_retry(self) -> None:
        """Record a retry (failed attempt that will be retried)."""
        self.total_retries += 1

    def record_success(self) -> None:
        """Record a successful completion."""
        self.successful_calls += 1

    def record_failure(self) -> None:
        """Record a final failure after all retries."""
        self.failed_calls += 1

    def get_stats(self) -> dict[str, Any]:
        """Get retry statistics."""
        return {
            "total_attempts": self.total_attempts,
            "total_retries": self.total_retries,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": (
                self.successful_calls / (self.successful_calls + self.failed_calls)
                if (self.successful_calls + self.failed_calls) > 0
                else 0.0
            ),
            "last_attempt_time": self.last_attempt_time,
        }


# Global metrics registry
_retry_metrics: dict[str, RetryMetrics] = {}


def get_retry_metrics(name: str) -> RetryMetrics:
    """Get or create retry metrics for a named operation."""
    if name not in _retry_metrics:
        _retry_metrics[name] = RetryMetrics()
    return _retry_metrics[name]


def is_retryable_exception_enhanced(exc: BaseException) -> bool:
    """Enhanced retryable exception detection."""
    if isinstance(exc, TransientBackendError) or exception_is_transient(exc):  # type: ignore[arg-type]
        return True

    # Network-related exceptions that should be retried
    retryable_types = (
        ConnectionError,
        TimeoutError,
        OSError,  # Can include network errors
    )

    if isinstance(exc, retryable_types):
        return True

    # gRPC specific errors (if available)
    try:
        import grpc  # noqa: WPS433

        if isinstance(exc, grpc.RpcError):
            status_code = exc.code()  # type: ignore[attr-defined]
            # Retry on transient gRPC errors
            retryable_grpc_codes = {
                grpc.StatusCode.UNAVAILABLE,
                grpc.StatusCode.DEADLINE_EXCEEDED,
                grpc.StatusCode.RESOURCE_EXHAUSTED,
                grpc.StatusCode.ABORTED,
            }
            return status_code in retryable_grpc_codes
    except ImportError:
        pass

    return False


def _create_wait_strategy(config: RetryConfig) -> Any:  # noqa: ANN401
    """Create appropriate wait strategy based on configuration."""
    if config.exponential_backoff:
        if config.jitter:
            return wait_exponential_jitter(exp_base=config.base_delay, max=config.max_delay)
        return wait_exponential(exp_base=config.base_delay, max=config.max_delay)

    if config.jitter:
        return wait_fixed(config.base_delay) + wait_random(0, config.base_delay * 0.1)
    return wait_fixed(config.base_delay)


def _create_stop_strategy(config: RetryConfig) -> Any:  # noqa: ANN401
    """Create stop strategy combining attempts and total delay."""
    strategies = [stop_after_attempt(config.max_attempts)]
    if config.max_total_delay > 0:
        strategies.append(stop_after_delay(config.max_total_delay))
    return strategies[0] if len(strategies) == 1 else strategies


def create_retry_policy_enhanced(
    config: RetryConfig | None = None, name: str | None = None, enable_logging: bool = True
) -> Any:  # noqa: ANN401
    """Create a comprehensive retry policy with monitoring."""
    if config is None:
        config = RetryConfig()

    wait_strategy = _create_wait_strategy(config)
    stop_strategy = _create_stop_strategy(config)

    # Create retry condition
    retry_condition = retry_if_exception(is_retryable_exception_enhanced)
    if config.retry_on_exceptions:
        retry_condition = retry_if_exception_type(config.retry_on_exceptions)

    retry_kwargs = {
        "retry": retry_condition,
        "stop": stop_strategy,
        "wait": wait_strategy,
        "reraise": True,
    }

    # Add logging if enabled
    if enable_logging and name:
        retry_kwargs["before"] = before_log(logger, logging.DEBUG)
        retry_kwargs["after"] = after_log(logger, logging.DEBUG)

    return tenacity_retry(**retry_kwargs)


def get_all_retry_metrics() -> dict[str, dict[str, Any]]:
    """Get metrics for all tracked retry operations."""
    return {name: metrics.get_stats() for name, metrics in _retry_metrics.items()}


__all__ = [
    "RetryConfig",
    "RetryMetrics",
    "create_retry_policy_enhanced",
    "get_all_retry_metrics",
    "get_retry_metrics",
    "is_retryable_exception_enhanced",
]
