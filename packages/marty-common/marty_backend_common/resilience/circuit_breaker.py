"""Thread-safe circuit breaker with enhanced configuration and monitoring."""

from __future__ import annotations

import inspect
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ParamSpec, Protocol, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


class CircuitBreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class ErrorClassifier(Protocol):
    """Protocol for custom error classification logic."""

    def should_trip_circuit(self, exception: Exception) -> bool:
        """Return True if the exception should count as a circuit breaker failure."""
        ...


class DefaultErrorClassifier:
    """Default error classifier that treats all exceptions as failures."""

    def should_trip_circuit(self, exception: Exception) -> bool:
        # Don't trip on validation errors or client errors - import locally to avoid cycles
        try:
            from .error_codes import UnauthorizedError, ValidationError

            return not isinstance(exception, (ValidationError, UnauthorizedError, ValueError))
        except ImportError:
            # Fallback if error_codes module isn't available
            return not isinstance(exception, ValueError)


@dataclass(slots=True)
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_success_threshold: int = 2
    failure_reset_timeout: float = 60.0
    # Enhanced configuration options
    max_concurrent_requests: int = 10
    error_classifier: ErrorClassifier = field(default_factory=DefaultErrorClassifier)
    enable_metrics: bool = True


class CircuitBreaker:
    """Enhanced circuit breaker with monitoring and flexible configuration."""

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state: CircuitBreakerState = CircuitBreakerState.CLOSED
        self._lock = threading.Lock()
        self._failure_count = 0
        self._success_count = 0
        self._opened_at = 0.0
        self._last_failure_at = 0.0
        self._logger = logging.getLogger(f"marty.circuit_breaker.{name}")

        # Enhanced metrics tracking
        self._total_requests = 0
        self._total_failures = 0
        self._total_successes = 0
        self._total_rejected = 0
        self._concurrent_requests = 0
        self._last_state_change = time.time()
        self._state_durations = {
            CircuitBreakerState.CLOSED: 0.0,
            CircuitBreakerState.OPEN: 0.0,
            CircuitBreakerState.HALF_OPEN: 0.0,
        }

    @property
    def state(self) -> CircuitBreakerState:  # pragma: no cover - trivial
        return self._state

    def allow_request(self) -> bool:
        with self._lock:
            now = time.time()

            # Check for state transitions
            if self._state == CircuitBreakerState.OPEN:
                if now - self._opened_at >= self.config.recovery_timeout:
                    self._transition_to(CircuitBreakerState.HALF_OPEN, now)
                    self._failure_count = 0
                    self._success_count = 0
                    return self._can_make_request()
                self._total_rejected += 1
                return False

            if self._state == CircuitBreakerState.HALF_OPEN:
                return self._can_make_request()

            # CLOSED state
            if (
                self._failure_count > 0
                and (now - self._last_failure_at) > self.config.failure_reset_timeout
            ):
                self._failure_count = 0

            return self._can_make_request()

    def _can_make_request(self) -> bool:
        """Check if we can make a request based on concurrent limits."""
        if self._concurrent_requests >= self.config.max_concurrent_requests:
            self._total_rejected += 1
            return False
        return True

    def _transition_to(self, new_state: CircuitBreakerState, now: float) -> None:
        """Transition to a new state and update metrics."""
        if self._state != new_state:
            # Record time spent in current state
            duration = now - self._last_state_change
            self._state_durations[self._state] += duration

            old_state = self._state
            self._state = new_state
            self._last_state_change = now

            self._logger.info(
                "Circuit breaker '%s' transitioned from %s to %s",
                self.name,
                old_state.value,
                new_state.value,
            )

    def record_success(self) -> None:
        with self._lock:
            now = time.time()
            self._total_successes += 1
            self._concurrent_requests = max(0, self._concurrent_requests - 1)

            if self._state == CircuitBreakerState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.half_open_success_threshold:
                    self._transition_to(CircuitBreakerState.CLOSED, now)
                    self._failure_count = 0
                    self._success_count = 0

    def record_failure(self, exception: Exception | None = None) -> None:
        with self._lock:
            now = time.time()
            self._concurrent_requests = max(0, self._concurrent_requests - 1)

            # Use error classifier to determine if this should count as a failure
            if exception and not self.config.error_classifier.should_trip_circuit(exception):
                return

            self._total_failures += 1
            self._last_failure_at = now

            if self._state == CircuitBreakerState.HALF_OPEN:
                self._transition_to(CircuitBreakerState.OPEN, now)
                self._opened_at = now
                self._failure_count = 1
                self._success_count = 0
                return

            if self._state == CircuitBreakerState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.config.failure_threshold:
                    self._transition_to(CircuitBreakerState.OPEN, now)
                    self._opened_at = now

    def decorate(self, func: Callable[P, T]) -> Callable[P, T]:
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            if not self.allow_request():
                msg = f"Circuit '{self.name}' is OPEN"
                raise RuntimeError(msg)

            with self._lock:
                self._total_requests += 1
                self._concurrent_requests += 1

            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                self.record_failure(exc)
                raise
            else:
                self.record_success()
                return result

        return wrapper

    def decorate_async(self, func: Callable[P, T | Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            if not self.allow_request():
                msg = f"Circuit '{self.name}' is OPEN"
                raise RuntimeError(msg)

            with self._lock:
                self._total_requests += 1
                self._concurrent_requests += 1

            try:
                result = func(*args, **kwargs)
                if inspect.isawaitable(result):  # type: ignore[arg-type]
                    result = await result  # type: ignore[assignment]
            except Exception as exc:
                self.record_failure(exc)
                raise
            else:
                self.record_success()
                return result  # type: ignore[return-value]

        return wrapper

    def stats(self) -> dict[str, Any]:
        """Get comprehensive circuit breaker statistics."""
        with self._lock:
            now = time.time()
            current_state_duration = now - self._last_state_change

            # Calculate success rate
            total_completed = self._total_successes + self._total_failures
            success_rate = self._total_successes / total_completed if total_completed > 0 else 0.0

            return {
                "name": self.name,
                "state": self._state.value,
                "failures": self._failure_count,
                "success_trial": self._success_count,
                "opened_at": self._opened_at,
                "last_failure_at": self._last_failure_at,
                # Enhanced metrics
                "total_requests": self._total_requests,
                "total_successes": self._total_successes,
                "total_failures": self._total_failures,
                "total_rejected": self._total_rejected,
                "concurrent_requests": self._concurrent_requests,
                "success_rate": success_rate,
                "current_state_duration": current_state_duration,
                "state_durations": dict(self._state_durations),
                "config": {
                    "failure_threshold": self.config.failure_threshold,
                    "recovery_timeout": self.config.recovery_timeout,
                    "half_open_success_threshold": self.config.half_open_success_threshold,
                    "max_concurrent_requests": self.config.max_concurrent_requests,
                },
            }

    def health_check(self) -> dict[str, Any]:
        """Perform a health check and return status information."""
        with self._lock:
            now = time.time()
            is_healthy = self._state != CircuitBreakerState.OPEN

            # Calculate time until recovery if circuit is open
            time_until_recovery = None
            if self._state == CircuitBreakerState.OPEN:
                time_until_recovery = max(0, self.config.recovery_timeout - (now - self._opened_at))

            return {
                "healthy": is_healthy,
                "state": self._state.value,
                "time_until_recovery": time_until_recovery,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "concurrent_requests": self._concurrent_requests,
            }

    def reset(self) -> None:
        """Reset the circuit breaker to its initial state."""
        with self._lock:
            old_state = self._state
            self._state = CircuitBreakerState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._opened_at = 0.0
            self._last_failure_at = 0.0
            self._concurrent_requests = 0
            self._last_state_change = time.time()

            self._logger.info(
                "Circuit breaker '%s' manually reset from %s to CLOSED", self.name, old_state.value
            )


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerState",
    "DefaultErrorClassifier",
    "ErrorClassifier",
]
