"""Comprehensive integration tests for resilience patterns with failure injection."""

from __future__ import annotations

import asyncio
import concurrent.futures
import random
import time
from collections.abc import Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any, Optional
from unittest.mock import Mock, patch

import grpc
import pytest
from grpc import aio as grpc_aio

from marty_common.resilience import (
    AdvancedRetryConfig,
    AdvancedRetryManager,
    BackoffStrategy,
    CircuitBreaker,
    CircuitBreakerConfig,
)
from marty_common.resilience.comprehensive_interceptors import (
    CompositeResilienceInterceptor,
    ResilienceClientInterceptor,
)
from marty_common.resilience.enhanced_interceptors import AdvancedFailureInjectionConfig
from marty_common.resilience.error_codes import TransientBackendError
from marty_common.resilience.monitoring import get_global_monitor


@dataclass
class FailureScenario:
    """Configuration for a specific failure scenario."""

    name: str
    failure_rate: float
    failure_type: type[Exception] = TransientBackendError
    duration_seconds: float = 10.0
    description: str = ""


class MockGrpcService:
    """Mock gRPC service for testing resilience patterns."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.failure_rate = 0.0
        self.latency_ms = 0
        self.request_count = 0
        self.failure_count = 0
        self.success_count = 0
        self.is_available = True

    def set_failure_rate(self, rate: float) -> None:
        """Set the failure rate for this service."""
        self.failure_rate = max(0.0, min(1.0, rate))

    def set_latency(self, latency_ms: int) -> None:
        """Set the latency for this service."""
        self.latency_ms = max(0, latency_ms)

    def set_availability(self, available: bool) -> None:
        """Set service availability."""
        self.is_available = available

    def call(self, request: str) -> str:
        """Simulate a service call with potential failures."""
        self.request_count += 1

        if not self.is_available:
            self.failure_count += 1
            raise TransientBackendError("Service is unavailable")

        # Simulate latency
        if self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000.0)

        # Simulate failures
        if random.random() < self.failure_rate:  # noqa: S311
            self.failure_count += 1
            raise TransientBackendError(f"Simulated failure in {self.name}")

        self.success_count += 1
        return f"Success from {self.name}: {request}"

    async def async_call(self, request: str) -> str:
        """Simulate an async service call with potential failures."""
        self.request_count += 1

        if not self.is_available:
            self.failure_count += 1
            raise TransientBackendError("Service is unavailable")

        # Simulate latency
        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000.0)

        # Simulate failures
        if random.random() < self.failure_rate:  # noqa: S311
            self.failure_count += 1
            raise TransientBackendError(f"Simulated failure in {self.name}")

        self.success_count += 1
        return f"Async success from {self.name}: {request}"

    def get_stats(self) -> dict[str, Any]:
        """Get service statistics."""
        return {
            "name": self.name,
            "request_count": self.request_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": (
                self.success_count / self.request_count if self.request_count > 0 else 0.0
            ),
            "failure_rate": self.failure_rate,
            "latency_ms": self.latency_ms,
            "is_available": self.is_available,
        }


class ResilienceTestOrchestrator:
    """Orchestrates comprehensive resilience testing scenarios."""

    def __init__(self) -> None:
        self.services: dict[str, MockGrpcService] = {}
        self.circuit_breakers: dict[str, CircuitBreaker] = {}
        self.retry_managers: dict[str, AdvancedRetryManager] = {}
        self.test_results: list[dict[str, Any]] = []

    def create_service(self, name: str) -> MockGrpcService:
        """Create a new mock service."""
        service = MockGrpcService(name)
        self.services[name] = service
        return service

    def create_circuit_breaker(
        self, name: str, config: CircuitBreakerConfig | None = None
    ) -> CircuitBreaker:
        """Create a circuit breaker for testing."""
        cb_config = config or CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=5.0,
            half_open_success_threshold=2,
        )
        circuit_breaker = CircuitBreaker(name, cb_config)
        self.circuit_breakers[name] = circuit_breaker
        return circuit_breaker

    def create_retry_manager(
        self, name: str, config: AdvancedRetryConfig | None = None
    ) -> AdvancedRetryManager:
        """Create a retry manager for testing."""
        retry_config = config or AdvancedRetryConfig(
            max_attempts=3,
            base_delay=0.1,
            max_delay=1.0,
            backoff_strategy=BackoffStrategy.EXPONENTIAL_JITTER,
        )
        retry_manager = AdvancedRetryManager(name, retry_config)
        self.retry_managers[name] = retry_manager
        return retry_manager

    @contextmanager
    def failure_injection(self, scenario: FailureScenario) -> Generator[None]:
        """Context manager for injecting failures during testing."""
        print(f"Starting failure scenario: {scenario.name}")
        print(f"Description: {scenario.description}")

        # Apply failure configuration to all services
        original_rates = {}
        for service_name, service in self.services.items():
            original_rates[service_name] = service.failure_rate
            service.set_failure_rate(scenario.failure_rate)

        start_time = time.time()
        try:
            yield
        finally:
            # Restore original failure rates
            for service_name, service in self.services.items():
                service.set_failure_rate(original_rates[service_name])

            duration = time.time() - start_time
            print(f"Completed failure scenario: {scenario.name} (duration: {duration:.2f}s)")

    def run_circuit_breaker_test(
        self, service_name: str, circuit_breaker_name: str, num_requests: int = 20
    ) -> dict[str, Any]:
        """Test circuit breaker behavior under various conditions."""
        service = self.services[service_name]
        circuit_breaker = self.circuit_breakers[circuit_breaker_name]

        print(f"Testing circuit breaker: {circuit_breaker_name} with service: {service_name}")

        @circuit_breaker.decorate
        def protected_call(request: str) -> str:
            return service.call(request)

        results = {
            "test_name": "circuit_breaker_test",
            "service": service_name,
            "circuit_breaker": circuit_breaker_name,
            "requests_attempted": 0,
            "requests_successful": 0,
            "requests_failed": 0,
            "circuit_breaker_rejections": 0,
            "state_transitions": [],
        }

        initial_state = circuit_breaker.state
        current_state = initial_state

        for i in range(num_requests):
            request = f"request_{i}"
            try:
                result = protected_call(request)
                results["requests_successful"] += 1
                print(f"Request {i}: SUCCESS - {result}")
            except RuntimeError as e:
                if "Circuit" in str(e):
                    results["circuit_breaker_rejections"] += 1
                    print(f"Request {i}: CIRCUIT BREAKER REJECTION - {e}")
                else:
                    results["requests_failed"] += 1
                    print(f"Request {i}: FAILED - {e}")
            except Exception as e:
                results["requests_failed"] += 1
                print(f"Request {i}: FAILED - {e}")

            results["requests_attempted"] += 1

            # Track state transitions
            new_state = circuit_breaker.state
            if new_state != current_state:
                transition = {
                    "request_number": i,
                    "from_state": current_state.value,
                    "to_state": new_state.value,
                    "timestamp": time.time(),
                }
                results["state_transitions"].append(transition)
                print(f"Circuit breaker state changed: {current_state.value} -> {new_state.value}")
                current_state = new_state

            # Small delay between requests
            time.sleep(0.1)

        # Add final circuit breaker stats
        results["final_circuit_breaker_stats"] = circuit_breaker.stats()
        results["final_service_stats"] = service.get_stats()

        self.test_results.append(results)
        return results

    def run_retry_test(
        self, service_name: str, retry_manager_name: str, num_requests: int = 10
    ) -> dict[str, Any]:
        """Test retry behavior under various conditions."""
        service = self.services[service_name]
        retry_manager = self.retry_managers[retry_manager_name]

        print(f"Testing retry manager: {retry_manager_name} with service: {service_name}")

        results = {
            "test_name": "retry_test",
            "service": service_name,
            "retry_manager": retry_manager_name,
            "requests_attempted": 0,
            "requests_successful": 0,
            "requests_failed": 0,
            "total_retry_attempts": 0,
        }

        for i in range(num_requests):
            request = f"retry_request_{i}"
            initial_attempts = retry_manager.metrics.total_attempts

            try:
                result = retry_manager.retry_sync(service.call, request)
                results["requests_successful"] += 1
                print(f"Retry request {i}: SUCCESS - {result}")
            except Exception as e:
                results["requests_failed"] += 1
                print(f"Retry request {i}: FAILED after retries - {e}")

            results["requests_attempted"] += 1
            final_attempts = retry_manager.metrics.total_attempts
            retry_attempts = final_attempts - initial_attempts
            results["total_retry_attempts"] += retry_attempts

            print(f"  Retry attempts for request {i}: {retry_attempts}")

            # Small delay between requests
            time.sleep(0.1)

        # Add final retry manager stats
        results["final_retry_stats"] = retry_manager.metrics.get_stats()
        results["final_service_stats"] = service.get_stats()

        self.test_results.append(results)
        return results

    async def run_async_retry_test(
        self, service_name: str, retry_manager_name: str, num_requests: int = 10
    ) -> dict[str, Any]:
        """Test async retry behavior under various conditions."""
        service = self.services[service_name]
        retry_manager = self.retry_managers[retry_manager_name]

        print(f"Testing async retry manager: {retry_manager_name} with service: {service_name}")

        results = {
            "test_name": "async_retry_test",
            "service": service_name,
            "retry_manager": retry_manager_name,
            "requests_attempted": 0,
            "requests_successful": 0,
            "requests_failed": 0,
            "total_retry_attempts": 0,
        }

        for i in range(num_requests):
            request = f"async_retry_request_{i}"
            initial_attempts = retry_manager.metrics.total_attempts

            try:
                result = await retry_manager.retry_async(service.async_call, request)
                results["requests_successful"] += 1
                print(f"Async retry request {i}: SUCCESS - {result}")
            except Exception as e:
                results["requests_failed"] += 1
                print(f"Async retry request {i}: FAILED after retries - {e}")

            results["requests_attempted"] += 1
            final_attempts = retry_manager.metrics.total_attempts
            retry_attempts = final_attempts - initial_attempts
            results["total_retry_attempts"] += retry_attempts

            print(f"  Async retry attempts for request {i}: {retry_attempts}")

            # Small delay between requests
            await asyncio.sleep(0.1)

        # Add final retry manager stats
        results["final_retry_stats"] = retry_manager.metrics.get_stats()
        results["final_service_stats"] = service.get_stats()

        self.test_results.append(results)
        return results

    def run_combined_resilience_test(
        self,
        service_name: str,
        circuit_breaker_name: str,
        retry_manager_name: str,
        num_requests: int = 15,
    ) -> dict[str, Any]:
        """Test combined circuit breaker and retry behavior."""
        service = self.services[service_name]
        circuit_breaker = self.circuit_breakers[circuit_breaker_name]
        retry_manager = self.retry_managers[retry_manager_name]

        print(f"Testing combined resilience: CB={circuit_breaker_name}, RM={retry_manager_name}")

        @circuit_breaker.decorate
        def protected_call(request: str) -> str:
            return service.call(request)

        results = {
            "test_name": "combined_resilience_test",
            "service": service_name,
            "circuit_breaker": circuit_breaker_name,
            "retry_manager": retry_manager_name,
            "requests_attempted": 0,
            "requests_successful": 0,
            "requests_failed": 0,
            "circuit_breaker_rejections": 0,
            "total_retry_attempts": 0,
        }

        for i in range(num_requests):
            request = f"combined_request_{i}"
            initial_attempts = retry_manager.metrics.total_attempts

            try:
                result = retry_manager.retry_sync(protected_call, request)
                results["requests_successful"] += 1
                print(f"Combined request {i}: SUCCESS - {result}")
            except RuntimeError as e:
                if "Circuit" in str(e):
                    results["circuit_breaker_rejections"] += 1
                    print(f"Combined request {i}: CIRCUIT BREAKER REJECTION - {e}")
                else:
                    results["requests_failed"] += 1
                    print(f"Combined request {i}: FAILED - {e}")
            except Exception as e:
                results["requests_failed"] += 1
                print(f"Combined request {i}: FAILED - {e}")

            results["requests_attempted"] += 1
            final_attempts = retry_manager.metrics.total_attempts
            retry_attempts = final_attempts - initial_attempts
            results["total_retry_attempts"] += retry_attempts

            # Small delay between requests
            time.sleep(0.1)

        # Add final stats
        results["final_circuit_breaker_stats"] = circuit_breaker.stats()
        results["final_retry_stats"] = retry_manager.metrics.get_stats()
        results["final_service_stats"] = service.get_stats()

        self.test_results.append(results)
        return results

    def generate_test_report(self) -> str:
        """Generate a comprehensive test report."""
        report_lines = [
            "Resilience Integration Test Report",
            "=" * 50,
            f"Generated at: {time.ctime()}",
            f"Total tests executed: {len(self.test_results)}",
            "",
        ]

        for i, result in enumerate(self.test_results, 1):
            report_lines.extend(
                [
                    f"Test {i}: {result['test_name']}",
                    "-" * 30,
                    f"Service: {result['service']}",
                    f"Requests attempted: {result['requests_attempted']}",
                    f"Requests successful: {result['requests_successful']}",
                    f"Requests failed: {result['requests_failed']}",
                ]
            )

            if "circuit_breaker_rejections" in result:
                report_lines.append(
                    f"Circuit breaker rejections: {result['circuit_breaker_rejections']}"
                )

            if "total_retry_attempts" in result:
                report_lines.append(f"Total retry attempts: {result['total_retry_attempts']}")

            success_rate = (
                result["requests_successful"] / result["requests_attempted"]
                if result["requests_attempted"] > 0
                else 0.0
            )
            report_lines.append(f"Success rate: {success_rate:.2%}")
            report_lines.append("")

        return "\n".join(report_lines)


# Pre-defined failure scenarios
FAILURE_SCENARIOS = [
    FailureScenario(
        name="high_failure_rate",
        failure_rate=0.7,
        description="High failure rate to test circuit breaker activation",
    ),
    FailureScenario(
        name="intermittent_failures",
        failure_rate=0.3,
        description="Moderate failure rate to test retry mechanisms",
    ),
    FailureScenario(
        name="transient_failures",
        failure_rate=0.1,
        description="Low failure rate for baseline testing",
    ),
    FailureScenario(
        name="total_failure", failure_rate=1.0, description="Complete service failure scenario"
    ),
]


def run_comprehensive_resilience_test() -> str:
    """Run a comprehensive test suite for all resilience patterns."""
    orchestrator = ResilienceTestOrchestrator()

    # Create test services
    primary_service = orchestrator.create_service("primary_service")
    backup_service = orchestrator.create_service("backup_service")

    # Create resilience components
    cb = orchestrator.create_circuit_breaker("test_circuit_breaker")
    rm = orchestrator.create_retry_manager("test_retry_manager")

    print("Starting comprehensive resilience test suite...")
    print("=" * 50)

    # Test 1: Circuit breaker under high failure rate
    print("\nTest 1: Circuit Breaker under High Failure Rate")
    with orchestrator.failure_injection(FAILURE_SCENARIOS[0]):  # high_failure_rate
        orchestrator.run_circuit_breaker_test("primary_service", "test_circuit_breaker")

    # Reset circuit breaker
    cb.reset()
    primary_service.failure_rate = 0.0

    # Test 2: Retry mechanism under intermittent failures
    print("\nTest 2: Retry Mechanism under Intermittent Failures")
    with orchestrator.failure_injection(FAILURE_SCENARIOS[1]):  # intermittent_failures
        orchestrator.run_retry_test("primary_service", "test_retry_manager")

    # Test 3: Combined resilience patterns
    print("\nTest 3: Combined Circuit Breaker and Retry")
    cb.reset()
    primary_service.failure_rate = 0.0
    with orchestrator.failure_injection(FAILURE_SCENARIOS[2]):  # transient_failures
        orchestrator.run_combined_resilience_test(
            "primary_service", "test_circuit_breaker", "test_retry_manager"
        )

    print("\nTest suite completed!")
    report = orchestrator.generate_test_report()
    print("\n" + report)

    return report


async def run_async_resilience_test() -> str:
    """Run async-specific resilience tests."""
    orchestrator = ResilienceTestOrchestrator()

    # Create test service and retry manager
    async_service = orchestrator.create_service("async_service")
    async_rm = orchestrator.create_retry_manager("async_retry_manager")

    print("Starting async resilience test...")
    print("=" * 40)

    # Test async retry under intermittent failures
    with orchestrator.failure_injection(FAILURE_SCENARIOS[1]):  # intermittent_failures
        await orchestrator.run_async_retry_test("async_service", "async_retry_manager")

    print("Async test completed!")
    report = orchestrator.generate_test_report()
    print("\n" + report)

    return report


if __name__ == "__main__":
    # Run synchronous tests
    sync_report = run_comprehensive_resilience_test()

    # Run asynchronous tests
    async_report = asyncio.run(run_async_resilience_test())

    print("\n" + "=" * 60)
    print("ALL RESILIENCE TESTS COMPLETED SUCCESSFULLY")
    print("=" * 60)
