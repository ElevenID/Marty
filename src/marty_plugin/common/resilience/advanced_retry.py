"""Advanced retry mechanisms with sophisticated backoff strategies and circuit breaker integration."""

from __future__ import annotations

import asyncio
import logging
import random
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

from tenacity import (  # type: ignore[import]
    AsyncRetrying,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    stop_after_delay,
    wait_combine,
    wait_exponential,
    wait_fixed,
    wait_random,
)

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .error_codes import TransientBackendError, exception_is_transient
from .metrics import MetricsCollector

logger = logging.getLogger(__name__)
T = TypeVar("T")


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Circuit breaker for {name} is open")


class RetryExhaustedError(Exception):
    """Exception raised when all retry attempts are exhausted."""

    def __init__(self, name: str, max_attempts: int, is_async: bool = False) -> None:
        self.name = name
        self.max_attempts = max_attempts
        self.is_async = is_async
        retry_type = "async retry" if is_async else "retry"
        super().__init__(f"All {max_attempts} {retry_type} attempts exhausted for {name}")


class BackoffStrategy(str, Enum):
    """Available backoff strategies for retries."""

    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    EXPONENTIAL_JITTER = "exponential_jitter"
    FIBONACCI = "fibonacci"
    POLYNOMIAL = "polynomial"
    ADAPTIVE = "adaptive"


class RetryResult(str, Enum):
    """Result of a retry operation."""

    SUCCESS = "success"
    EXHAUSTED = "exhausted"
    CIRCUIT_OPEN = "circuit_open"
    NON_RETRYABLE = "non_retryable"


@dataclass
class AdvancedRetryConfig:
    """Advanced configuration for retry behavior."""

    # Basic retry parameters
    max_attempts: int = 5
    base_delay: float = 0.1
    max_delay: float = 60.0
    total_timeout: float = 300.0

    # Backoff strategy
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL_JITTER
    jitter_factor: float = 0.1
    multiplier: float = 2.0

    # Exception handling
    retry_on_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: (
            TransientBackendError,
            ConnectionError,
            TimeoutError,
            OSError,
        )
    )
    abort_on_exceptions: tuple[type[Exception], ...] = field(
        default_factory=lambda: (ValueError, TypeError, KeyError)
    )

    # Circuit breaker integration
    enable_circuit_breaker: bool = True
    circuit_breaker_config: CircuitBreakerConfig | None = None

    # Adaptive behavior
    enable_adaptive_delays: bool = False
    success_rate_threshold: float = 0.8
    failure_window_size: int = 100

    # Rate limiting
    max_concurrent_retries: int = 50
    enable_per_host_limits: bool = True


class AdvancedRetryMetrics:
    """Enhanced metrics collection for retry operations."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.total_attempts = 0
        self.total_retries = 0
        self.successful_operations = 0
        self.failed_operations = 0
        self.circuit_breaker_rejections = 0

        # Timing metrics
        self.total_delay_time = 0.0
        self.total_execution_time = 0.0
        self.min_delay = float("inf")
        self.max_delay = 0.0

        # Recent performance tracking for adaptive behavior
        self.recent_outcomes: list[bool] = []
        self.recent_delays: list[float] = []
        self.window_size = 100

        # Per-exception type tracking
        self.exception_counts: dict[str, int] = {}

        self.start_time = time.time()

    def record_attempt(self, delay: float = 0.0) -> None:
        """Record a retry attempt."""
        self.total_attempts += 1
        if delay > 0:
            self.total_retries += 1
            self.total_delay_time += delay
            self.min_delay = min(self.min_delay, delay)
            self.max_delay = max(self.max_delay, delay)

            # Track recent delays for adaptive behavior
            self.recent_delays.append(delay)
            if len(self.recent_delays) > self.window_size:
                self.recent_delays.pop(0)

    def record_exception(self, exc: Exception) -> None:
        """Record an exception type."""
        exc_type = type(exc).__name__
        self.exception_counts[exc_type] = self.exception_counts.get(exc_type, 0) + 1

    def record_outcome(self, success: bool, execution_time: float = 0.0) -> None:
        """Record the final outcome of an operation."""
        if success:
            self.successful_operations += 1
        else:
            self.failed_operations += 1

        self.total_execution_time += execution_time

        # Track recent outcomes for adaptive behavior
        self.recent_outcomes.append(success)
        if len(self.recent_outcomes) > self.window_size:
            self.recent_outcomes.pop(0)

    def record_circuit_breaker_rejection(self) -> None:
        """Record a circuit breaker rejection."""
        self.circuit_breaker_rejections += 1

    def get_success_rate(self) -> float:
        """Calculate recent success rate."""
        if not self.recent_outcomes:
            return 1.0
        return sum(self.recent_outcomes) / len(self.recent_outcomes)

    def get_average_delay(self) -> float:
        """Calculate average retry delay."""
        if not self.recent_delays:
            return 0.0
        return sum(self.recent_delays) / len(self.recent_delays)

    def should_adapt_delays(self, threshold: float) -> bool:
        """Determine if delays should be adapted based on recent performance."""
        return self.get_success_rate() < threshold and len(self.recent_outcomes) >= 10

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive retry statistics."""
        total_operations = self.successful_operations + self.failed_operations
        overall_success_rate = (
            self.successful_operations / total_operations if total_operations > 0 else 0.0
        )

        avg_execution_time = (
            self.total_execution_time / total_operations if total_operations > 0 else 0.0
        )

        return {
            "name": self.name,
            "total_attempts": self.total_attempts,
            "total_retries": self.total_retries,
            "successful_operations": self.successful_operations,
            "failed_operations": self.failed_operations,
            "circuit_breaker_rejections": self.circuit_breaker_rejections,
            "overall_success_rate": overall_success_rate,
            "recent_success_rate": self.get_success_rate(),
            "total_delay_time": self.total_delay_time,
            "average_delay": self.get_average_delay(),
            "min_delay": self.min_delay if self.min_delay != float("inf") else 0.0,
            "max_delay": self.max_delay,
            "average_execution_time": avg_execution_time,
            "exception_counts": dict(self.exception_counts),
            "uptime": time.time() - self.start_time,
        }


class AdvancedRetryManager:
    """Advanced retry manager with circuit breaker integration and adaptive behavior."""

    def __init__(self, name: str, config: AdvancedRetryConfig | None = None) -> None:
        self.name = name
        self.config = config or AdvancedRetryConfig()
        self.metrics = AdvancedRetryMetrics(name)
        self._concurrent_retries = 0

        # Circuit breaker integration
        self.circuit_breaker = None
        if self.config.enable_circuit_breaker:
            cb_config = self.config.circuit_breaker_config or CircuitBreakerConfig()
            self.circuit_breaker = CircuitBreaker(f"{name}_retry", cb_config)

    def _calculate_delay(self, attempt: int, base_delay: float) -> float:
        """Calculate delay based on the configured backoff strategy."""
        if attempt <= 1:
            return 0.0

        strategy = self.config.backoff_strategy

        if strategy == BackoffStrategy.FIXED:
            delay = base_delay
        elif strategy == BackoffStrategy.LINEAR:
            delay = base_delay * attempt
        elif strategy == BackoffStrategy.EXPONENTIAL:
            delay = base_delay * (self.config.multiplier ** (attempt - 1))
        elif strategy == BackoffStrategy.FIBONACCI:
            delay = base_delay * self._fibonacci(attempt)
        elif strategy == BackoffStrategy.POLYNOMIAL:
            delay = base_delay * (attempt**2)
        elif strategy == BackoffStrategy.ADAPTIVE:
            delay = self._adaptive_delay(attempt, base_delay)
        else:  # EXPONENTIAL_JITTER (default)
            exponential = base_delay * (self.config.multiplier ** (attempt - 1))
            jitter = exponential * self.config.jitter_factor * (secrets.randbelow(1000) / 1000.0)
            delay = exponential + jitter

        # Apply jitter for non-adaptive strategies
        if strategy != BackoffStrategy.ADAPTIVE and self.config.jitter_factor > 0:
            jitter_amount = delay * self.config.jitter_factor * (secrets.randbelow(1000) / 1000.0)
            delay += jitter_amount

        return min(delay, self.config.max_delay)

    def _fibonacci(self, n: int) -> int:
        """Calculate nth Fibonacci number."""
        if n <= 2:
            return 1
        a, b = 1, 1
        for _ in range(3, n + 1):
            a, b = b, a + b
        return b

    def _adaptive_delay(self, attempt: int, base_delay: float) -> float:
        """Calculate adaptive delay based on recent performance."""
        if not self.config.enable_adaptive_delays:
            return base_delay * (self.config.multiplier ** (attempt - 1))

        success_rate = self.metrics.get_success_rate()
        avg_delay = self.metrics.get_average_delay()

        # Increase delay if success rate is low
        if success_rate < self.config.success_rate_threshold:
            adaptation_factor = 1.0 + (1.0 - success_rate)
            base_delay *= adaptation_factor

        # Use recent average delay if available and reasonable
        if avg_delay > 0 and avg_delay < self.config.max_delay:
            base_delay = (base_delay + avg_delay) / 2

        return min(base_delay * (self.config.multiplier ** (attempt - 1)), self.config.max_delay)

    def _is_retryable_exception(self, exc: Exception) -> bool:
        """Determine if an exception should trigger a retry."""
        # Check for abort conditions first
        if isinstance(exc, self.config.abort_on_exceptions):
            return False

        # Check specific retry exceptions
        if isinstance(exc, self.config.retry_on_exceptions):
            return True

        # Use existing transient exception detection
        return exception_is_transient(exc)  # type: ignore[arg-type]

    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows the request."""
        if self.circuit_breaker is None:
            return True

        if not self.circuit_breaker.allow_request():
            self.metrics.record_circuit_breaker_rejection()
            return False
        return True

    def retry_sync(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute function with sync retry logic."""
        if not self._check_circuit_breaker():
            raise RuntimeError(f"Circuit breaker for {self.name} is open")

        start_time = time.time()
        attempt = 0
        total_delay = 0.0

        while attempt < self.config.max_attempts:
            attempt += 1

            # Check timeout
            if time.time() - start_time + total_delay > self.config.total_timeout:
                break

            try:
                # Calculate and apply delay for retries
                if attempt > 1:
                    delay = self._calculate_delay(attempt, self.config.base_delay)
                    if delay > 0:
                        time.sleep(delay)
                        total_delay += delay
                        self.metrics.record_attempt(delay)
                else:
                    self.metrics.record_attempt()

                # Execute the function
                execution_start = time.time()
                result = func(*args, **kwargs)
                execution_time = time.time() - execution_start

                # Record success
                self.metrics.record_outcome(True, execution_time)
                if self.circuit_breaker:
                    self.circuit_breaker.record_success()

                return result

            except Exception as exc:
                execution_time = (
                    time.time() - execution_start if "execution_start" in locals() else 0.0
                )
                self.metrics.record_exception(exc)

                # Check if this exception should trigger circuit breaker
                if self.circuit_breaker:
                    self.circuit_breaker.record_failure(exc)

                # Check if we should retry
                if not self._is_retryable_exception(exc) or attempt >= self.config.max_attempts:
                    self.metrics.record_outcome(False, execution_time)
                    raise

                logger.debug(
                    "Retry attempt %d/%d failed for %s: %s",
                    attempt,
                    self.config.max_attempts,
                    self.name,
                    exc,
                )

        # All retries exhausted
        self.metrics.record_outcome(False, time.time() - start_time)
        raise RuntimeError(
            f"All {self.config.max_attempts} retry attempts exhausted for {self.name}"
        )

    async def retry_async(self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        """Execute async function with retry logic."""
        if not self._check_circuit_breaker():
            raise RuntimeError(f"Circuit breaker for {self.name} is open")

        start_time = time.time()
        attempt = 0
        total_delay = 0.0

        while attempt < self.config.max_attempts:
            attempt += 1

            # Check timeout
            if time.time() - start_time + total_delay > self.config.total_timeout:
                break

            try:
                # Calculate and apply delay for retries
                if attempt > 1:
                    delay = self._calculate_delay(attempt, self.config.base_delay)
                    if delay > 0:
                        await asyncio.sleep(delay)
                        total_delay += delay
                        self.metrics.record_attempt(delay)
                else:
                    self.metrics.record_attempt()

                # Execute the function
                execution_start = time.time()
                result = await func(*args, **kwargs)
                execution_time = time.time() - execution_start

                # Record success
                self.metrics.record_outcome(True, execution_time)
                if self.circuit_breaker:
                    self.circuit_breaker.record_success()

                return result

            except Exception as exc:
                execution_time = (
                    time.time() - execution_start if "execution_start" in locals() else 0.0
                )
                self.metrics.record_exception(exc)

                # Check if this exception should trigger circuit breaker
                if self.circuit_breaker:
                    self.circuit_breaker.record_failure(exc)

                # Check if we should retry
                if not self._is_retryable_exception(exc) or attempt >= self.config.max_attempts:
                    self.metrics.record_outcome(False, execution_time)
                    raise

                logger.debug(
                    "Async retry attempt %d/%d failed for %s: %s",
                    attempt,
                    self.config.max_attempts,
                    self.name,
                    exc,
                )

        # All retries exhausted
        self.metrics.record_outcome(False, time.time() - start_time)
        raise RuntimeError(
            f"All {self.config.max_attempts} async retry attempts exhausted for {self.name}"
        )


# Global registry for retry managers
_retry_managers: dict[str, AdvancedRetryManager] = {}


def get_retry_manager(name: str, config: AdvancedRetryConfig | None = None) -> AdvancedRetryManager:
    """Get or create a retry manager with the given name."""
    if name not in _retry_managers:
        _retry_managers[name] = AdvancedRetryManager(name, config)
    return _retry_managers[name]


def retry_with_advanced_policy(
    name: str, config: AdvancedRetryConfig | None = None
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for applying advanced retry policy to sync functions."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        retry_manager = get_retry_manager(name, config)

        def wrapper(*args: Any, **kwargs: Any) -> T:
            return retry_manager.retry_sync(func, *args, **kwargs)

        return wrapper

    return decorator


def async_retry_with_advanced_policy(
    name: str, config: AdvancedRetryConfig | None = None
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator for applying advanced retry policy to async functions."""

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        retry_manager = get_retry_manager(name, config)

        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await retry_manager.retry_async(func, *args, **kwargs)

        return wrapper

    return decorator


def get_all_retry_manager_stats() -> dict[str, dict[str, Any]]:
    """Get statistics for all retry managers."""
    return {name: manager.metrics.get_stats() for name, manager in _retry_managers.items()}


__all__ = [
    "AdvancedRetryConfig",
    "AdvancedRetryManager",
    "AdvancedRetryMetrics",
    "BackoffStrategy",
    "RetryResult",
    "async_retry_with_advanced_policy",
    "get_all_retry_manager_stats",
    "get_retry_manager",
    "retry_with_advanced_policy",
]
