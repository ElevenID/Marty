"""Chaos engineering tests for validating resilience patterns."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pytest


class ChaosType(str, Enum):
    """Types of chaos that can be injected."""

    NETWORK_DELAY = "network_delay"
    NETWORK_FAILURE = "network_failure"
    SERVICE_UNAVAILABLE = "service_unavailable"
    HIGH_LATENCY = "high_latency"
    MEMORY_PRESSURE = "memory_pressure"
    CPU_SPIKE = "cpu_spike"
    DISK_FULL = "disk_full"
    RANDOM_ERRORS = "random_errors"
    INTERMITTENT_FAILURES = "intermittent_failures"


@dataclass
class ChaosConfig:
    """Configuration for chaos injection."""

    chaos_type: ChaosType
    probability: float = 0.3  # 30% chance by default
    duration_seconds: float = 10.0
    intensity: float = 1.0  # Scale from 0.0 to 1.0
    target_services: list[str] = field(default_factory=list)
    enabled: bool = True


class ChaosInjector:
    """Inject various types of chaos into the system."""

    def __init__(self) -> None:
        self.active_chaos: dict[str, ChaosConfig] = {}
        self.injection_history: list[dict[str, Any]] = []

    async def inject_chaos(self, config: ChaosConfig, target: str = "default") -> None:
        """Inject specified chaos into the system."""
        if not config.enabled:
            return

        if random.random() > config.probability:
            return

        self.active_chaos[target] = config
        start_time = time.time()

        self.injection_history.append(
            {
                "target": target,
                "chaos_type": config.chaos_type.value,
                "start_time": start_time,
                "duration": config.duration_seconds,
                "intensity": config.intensity,
            }
        )

        try:
            if config.chaos_type == ChaosType.NETWORK_DELAY:
                await self._inject_network_delay(config)
            elif config.chaos_type == ChaosType.NETWORK_FAILURE:
                await self._inject_network_failure(config)
            elif config.chaos_type == ChaosType.SERVICE_UNAVAILABLE:
                await self._inject_service_unavailable(config)
            elif config.chaos_type == ChaosType.HIGH_LATENCY:
                await self._inject_high_latency(config)
            elif config.chaos_type == ChaosType.RANDOM_ERRORS:
                await self._inject_random_errors(config)
            elif config.chaos_type == ChaosType.INTERMITTENT_FAILURES:
                await self._inject_intermittent_failures(config)
        finally:
            if target in self.active_chaos:
                del self.active_chaos[target]

    async def _inject_network_delay(self, config: ChaosConfig) -> None:
        """Simulate network delays."""
        delay = config.intensity * 2.0  # Up to 2 seconds delay
        await asyncio.sleep(delay)

    async def _inject_network_failure(self, config: ChaosConfig) -> None:
        """Simulate complete network failure."""
        from marty_common.resilience.enhanced_errors import TransientError

        raise TransientError("Simulated network failure")

    async def _inject_service_unavailable(self, config: ChaosConfig) -> None:
        """Simulate service unavailability."""
        from marty_common.resilience.enhanced_errors import ExternalServiceError

        raise ExternalServiceError("Service temporarily unavailable", service_name="chaos_target")

    async def _inject_high_latency(self, config: ChaosConfig) -> None:
        """Simulate high latency responses."""
        latency = config.intensity * 5.0  # Up to 5 seconds latency
        await asyncio.sleep(latency)

    async def _inject_random_errors(self, config: ChaosConfig) -> None:
        """Inject random errors."""
        from marty_common.resilience.enhanced_errors import (
            AuthorizationError,
            DatabaseError,
            ValidationError,
        )

        errors = [
            DatabaseError("Random database connection error"),
            ValidationError("Random validation failure", field_name="test_field"),
            AuthorizationError("Random authorization error"),
        ]

        error = random.choice(errors)
        raise error

    async def _inject_intermittent_failures(self, config: ChaosConfig) -> None:
        """Inject intermittent failures that come and go."""
        if random.random() < config.intensity:
            from marty_common.resilience.enhanced_errors import TransientError

            raise TransientError("Intermittent failure injection")

    def is_chaos_active(self, target: str = "default") -> bool:
        """Check if chaos is currently active for a target."""
        return target in self.active_chaos

    def get_chaos_history(self) -> list[dict[str, Any]]:
        """Get history of chaos injections."""
        return self.injection_history.copy()


@asynccontextmanager
async def chaos_context(
    chaos_injector: ChaosInjector, config: ChaosConfig, target: str = "default"
) -> AsyncIterator[None]:
    """Context manager for chaos injection during testing."""
    chaos_task = asyncio.create_task(chaos_injector.inject_chaos(config, target))
    try:
        yield
    finally:
        if not chaos_task.done():
            chaos_task.cancel()
            try:
                await chaos_task
            except asyncio.CancelledError:
                pass


class ResilienceTestSuite:
    """Comprehensive test suite for resilience patterns."""

    def __init__(self) -> None:
        self.chaos_injector = ChaosInjector()
        self.test_results: dict[str, dict[str, Any]] = {}

    async def test_circuit_breaker_resilience(
        self, operation: Callable[[], Awaitable[Any]], expected_failures: int = 5
    ) -> dict[str, Any]:
        """Test circuit breaker behavior under failure conditions."""
        from marty_common.resilience import CircuitBreaker, CircuitBreakerConfig

        # Configure circuit breaker with low threshold for testing
        config = CircuitBreakerConfig(
            failure_threshold=expected_failures, recovery_timeout=1.0, half_open_success_threshold=2
        )
        circuit_breaker = CircuitBreaker("test_circuit", config)

        results = {
            "total_requests": 0,
            "successful_requests": 0,
            "circuit_breaker_rejections": 0,
            "exceptions": 0,
            "circuit_opened": False,
            "circuit_recovered": False,
        }

        # Inject failures to trigger circuit breaker
        chaos_config = ChaosConfig(
            chaos_type=ChaosType.RANDOM_ERRORS,
            probability=0.8,  # High failure rate
            duration_seconds=0.1,
        )

        # Test failure injection phase
        for i in range(expected_failures + 2):
            results["total_requests"] += 1

            if not circuit_breaker.allow_request():
                results["circuit_breaker_rejections"] += 1
                results["circuit_opened"] = True
                continue

            try:
                async with chaos_context(self.chaos_injector, chaos_config):
                    await operation()
                circuit_breaker.record_success()
                results["successful_requests"] += 1
            except Exception:
                circuit_breaker.record_failure()
                results["exceptions"] += 1

        # Wait for recovery and test recovery phase
        await asyncio.sleep(config.recovery_timeout + 0.1)

        # Test recovery with successful operations
        for i in range(3):
            results["total_requests"] += 1

            if not circuit_breaker.allow_request():
                results["circuit_breaker_rejections"] += 1
                continue

            try:
                # No chaos injection for recovery test
                await operation()
                circuit_breaker.record_success()
                results["successful_requests"] += 1
                if circuit_breaker.state.value == "closed":
                    results["circuit_recovered"] = True
            except Exception:
                circuit_breaker.record_failure()
                results["exceptions"] += 1

        self.test_results["circuit_breaker"] = results
        return results

    async def test_retry_resilience(
        self, operation: Callable[[], Awaitable[Any]], max_retries: int = 3
    ) -> dict[str, Any]:
        """Test retry mechanism under transient failures."""
        from marty_common.resilience.retry_enhanced import (
            RetryConfig,
            create_retry_policy_enhanced,
            get_retry_metrics,
        )

        config = RetryConfig(
            max_attempts=max_retries + 1,
            base_delay=0.1,
            max_delay=0.5,
            exponential_backoff=True,
            jitter=True,
        )

        retry_policy = create_retry_policy_enhanced(config, "test_retry")
        metrics = get_retry_metrics("test_retry")

        # Reset metrics
        metrics.total_attempts = 0
        metrics.total_retries = 0
        metrics.successful_calls = 0
        metrics.failed_calls = 0

        results = {
            "attempts": 0,
            "successes": 0,
            "final_failures": 0,
            "transient_errors_recovered": 0,
        }

        # Test transient failures that eventually succeed
        chaos_config = ChaosConfig(
            chaos_type=ChaosType.INTERMITTENT_FAILURES,
            probability=0.7,  # High initial failure rate
            intensity=0.5,  # Moderate intensity
        )

        @retry_policy
        async def retryable_operation():
            # Reduce chaos probability with each attempt to simulate recovery
            chaos_config.probability *= 0.7
            async with chaos_context(self.chaos_injector, chaos_config):
                return await operation()

        # Run multiple test scenarios
        for scenario in range(5):
            chaos_config.probability = 0.7  # Reset for each scenario
            try:
                await retryable_operation()
                results["successes"] += 1
                if metrics.total_retries > 0:
                    results["transient_errors_recovered"] += 1
            except Exception:
                results["final_failures"] += 1

        results["attempts"] = metrics.total_attempts
        results["total_retries"] = metrics.total_retries

        self.test_results["retry"] = results
        return results

    async def test_graceful_degradation(
        self,
        primary_operation: Callable[[], Awaitable[Any]],
        fallback_operation: Callable[[], Awaitable[Any]],
    ) -> dict[str, Any]:
        """Test graceful degradation and fallback mechanisms."""
        from marty_common.resilience.graceful_degradation import (
            DefaultValueProvider,
            DegradationLevel,
            GracefulDegradationManager,
        )

        manager = GracefulDegradationManager()
        manager.add_fallback_provider("test_feature", DefaultValueProvider("fallback_response"))

        results = {
            "primary_successes": 0,
            "fallback_used": 0,
            "total_requests": 0,
            "degradation_triggered": False,
        }

        # Test normal operation
        for i in range(3):
            results["total_requests"] += 1
            try:
                result = await manager.execute_with_fallback("test_feature", primary_operation)
                if result == "fallback_response":
                    results["fallback_used"] += 1
                else:
                    results["primary_successes"] += 1
            except Exception:
                pass

        # Trigger degradation by injecting failures
        manager.set_degradation_level(DegradationLevel.PARTIAL)
        results["degradation_triggered"] = True

        chaos_config = ChaosConfig(
            chaos_type=ChaosType.SERVICE_UNAVAILABLE,
            probability=1.0,  # Always fail
            duration_seconds=0.1,
        )

        # Test degraded operation
        for i in range(3):
            results["total_requests"] += 1
            try:
                async with chaos_context(self.chaos_injector, chaos_config):
                    result = await manager.execute_with_fallback("test_feature", primary_operation)
                    if result == "fallback_response":
                        results["fallback_used"] += 1
                    else:
                        results["primary_successes"] += 1
            except Exception:
                pass

        self.test_results["graceful_degradation"] = results
        return results

    async def test_end_to_end_resilience(
        self, operation: Callable[[], Awaitable[Any]]
    ) -> dict[str, Any]:
        """Comprehensive end-to-end resilience test."""
        from marty_common.resilience import CircuitBreaker, CircuitBreakerConfig
        from marty_common.resilience.graceful_degradation import (
            DefaultValueProvider,
            GracefulDegradationManager,
        )
        from marty_common.resilience.retry_enhanced import RetryConfig, create_retry_policy_enhanced

        # Set up comprehensive resilience stack
        circuit_breaker = CircuitBreaker(
            "e2e_test", CircuitBreakerConfig(failure_threshold=3, recovery_timeout=2.0)
        )

        retry_config = RetryConfig(max_attempts=3, base_delay=0.1, max_delay=0.5)
        retry_policy = create_retry_policy_enhanced(retry_config, "e2e_retry")

        degradation_manager = GracefulDegradationManager()
        degradation_manager.add_fallback_provider(
            "e2e_feature", DefaultValueProvider("emergency_fallback")
        )

        results = {
            "total_requests": 0,
            "successes": 0,
            "circuit_breaker_trips": 0,
            "fallbacks_used": 0,
            "complete_failures": 0,
            "scenarios_tested": [],
        }

        # Scenario 1: Normal operation
        results["scenarios_tested"].append("normal_operation")
        for i in range(5):
            results["total_requests"] += 1
            try:
                await operation()
                results["successes"] += 1
            except Exception:
                results["complete_failures"] += 1

        # Scenario 2: Intermittent failures with retry recovery
        results["scenarios_tested"].append("intermittent_failures")
        chaos_config = ChaosConfig(
            chaos_type=ChaosType.INTERMITTENT_FAILURES, probability=0.6, intensity=0.4
        )

        @retry_policy
        async def retryable_with_circuit():
            if not circuit_breaker.allow_request():
                results["circuit_breaker_trips"] += 1
                raise Exception("Circuit breaker open")

            try:
                async with chaos_context(self.chaos_injector, chaos_config):
                    result = await operation()
                circuit_breaker.record_success()
                return result
            except Exception as exc:
                circuit_breaker.record_failure()
                raise

        for i in range(5):
            results["total_requests"] += 1
            try:
                await retryable_with_circuit()
                results["successes"] += 1
            except Exception:
                # Try fallback through degradation manager
                try:
                    result = await degradation_manager.execute_with_fallback(
                        "e2e_feature", lambda: operation()
                    )
                    results["fallbacks_used"] += 1
                except Exception:
                    results["complete_failures"] += 1

        # Scenario 3: Complete service failure with circuit breaker
        results["scenarios_tested"].append("complete_failure")
        failure_config = ChaosConfig(
            chaos_type=ChaosType.SERVICE_UNAVAILABLE, probability=1.0, duration_seconds=0.1
        )

        for i in range(8):  # Trigger circuit breaker
            results["total_requests"] += 1
            try:
                async with chaos_context(self.chaos_injector, failure_config):
                    await retryable_with_circuit()
                results["successes"] += 1
            except Exception:
                try:
                    result = await degradation_manager.execute_with_fallback(
                        "e2e_feature", lambda: operation()
                    )
                    results["fallbacks_used"] += 1
                except Exception:
                    results["complete_failures"] += 1

        self.test_results["end_to_end"] = results
        return results

    def get_test_summary(self) -> dict[str, Any]:
        """Get summary of all test results."""
        return {
            "test_results": self.test_results,
            "chaos_history": self.chaos_injector.get_chaos_history(),
            "total_tests_run": len(self.test_results),
        }


# Pytest fixtures and test cases
@pytest.fixture
async def resilience_test_suite():
    """Fixture providing a resilience test suite."""
    return ResilienceTestSuite()


@pytest.fixture
async def simple_operation():
    """Simple operation for testing."""

    async def operation():
        await asyncio.sleep(0.01)  # Simulate some work
        return "success"

    return operation


@pytest.mark.asyncio
async def test_circuit_breaker_resilience(resilience_test_suite, simple_operation):
    """Test circuit breaker resilience patterns."""
    results = await resilience_test_suite.test_circuit_breaker_resilience(simple_operation)

    # Verify circuit breaker opened
    assert results["circuit_opened"], "Circuit breaker should have opened"
    assert results["circuit_breaker_rejections"] > 0, "Should have rejected requests when open"

    # Verify some recovery
    assert results["circuit_recovered"], "Circuit breaker should have recovered"


@pytest.mark.asyncio
async def test_retry_resilience(resilience_test_suite, simple_operation):
    """Test retry mechanism resilience."""
    results = await resilience_test_suite.test_retry_resilience(simple_operation)

    # Verify retries occurred
    assert results["total_retries"] > 0, "Should have retried failed operations"
    assert results["successes"] > 0, "Should have eventually succeeded"


@pytest.mark.asyncio
async def test_graceful_degradation(resilience_test_suite, simple_operation):
    """Test graceful degradation patterns."""

    async def fallback_operation():
        return "fallback_response"

    results = await resilience_test_suite.test_graceful_degradation(
        simple_operation, fallback_operation
    )

    # Verify degradation and fallback
    assert results["degradation_triggered"], "Degradation should have been triggered"
    assert results["fallback_used"] > 0, "Fallback should have been used"


@pytest.mark.asyncio
async def test_comprehensive_resilience(resilience_test_suite, simple_operation):
    """Comprehensive end-to-end resilience test."""
    results = await resilience_test_suite.test_end_to_end_resilience(simple_operation)

    # Verify comprehensive resilience
    assert len(results["scenarios_tested"]) >= 3, "Should test multiple scenarios"
    assert (
        results["successes"] + results["fallbacks_used"] > 0
    ), "Should have some successful outcomes"

    # Get test summary
    summary = resilience_test_suite.get_test_summary()
    assert summary["total_tests_run"] >= 1, "Should have run tests"


if __name__ == "__main__":
    # Example usage
    async def main():
        suite = ResilienceTestSuite()

        async def test_operation():
            await asyncio.sleep(0.01)
            return {"status": "success", "data": "test_data"}

        print("Running chaos engineering tests...")

        # Test circuit breaker
        print("\\nTesting Circuit Breaker...")
        cb_results = await suite.test_circuit_breaker_resilience(test_operation)
        print(f"Circuit Breaker Results: {cb_results}")

        # Test retry mechanisms
        print("\\nTesting Retry Mechanisms...")
        retry_results = await suite.test_retry_resilience(test_operation)
        print(f"Retry Results: {retry_results}")

        # Test graceful degradation
        print("\\nTesting Graceful Degradation...")

        async def fallback_op():
            return {"status": "degraded", "data": "fallback_data"}

        degradation_results = await suite.test_graceful_degradation(test_operation, fallback_op)
        print(f"Degradation Results: {degradation_results}")

        # Comprehensive test
        print("\\nRunning Comprehensive Test...")
        e2e_results = await suite.test_end_to_end_resilience(test_operation)
        print(f"End-to-End Results: {e2e_results}")

        # Summary
        summary = suite.get_test_summary()
        print(f"\\nTest Summary: {summary}")

    asyncio.run(main())


__all__ = [
    "ChaosConfig",
    "ChaosInjector",
    "ChaosType",
    "ResilienceTestSuite",
    "chaos_context",
]
