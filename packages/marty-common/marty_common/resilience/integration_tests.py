"""Integration tests for end-to-end resilience validation."""

from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, List

import pytest

# Import resilience components
from marty_common.resilience import CircuitBreaker, CircuitBreakerConfig
from marty_common.resilience.enhanced_errors import (
    DatabaseError,
    ExternalServiceError,
    TransientError,
    ValidationError,
)
from marty_common.resilience.graceful_degradation import (
    DefaultValueProvider,
    DegradationLevel,
    GracefulDegradationManager,
)
from marty_common.resilience.retry_enhanced import (
    RetryConfig,
    create_retry_policy_enhanced,
    get_retry_metrics,
)


@dataclass
class TestMetrics:
    """Metrics collected during integration tests."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    circuit_breaker_activations: int = 0
    retry_attempts: int = 0
    fallback_invocations: int = 0
    recovery_time_seconds: float = 0.0


class MockService:
    """Mock service for testing resilience patterns."""

    def __init__(self, name: str):
        self.name = name
        self.failure_rate = 0.0
        self.latency_ms = 0
        self.is_available = True
        self.request_count = 0

    async def call(self, data: dict[str, Any]) -> dict[str, Any]:
        """Simulate service call with configurable failures."""
        self.request_count += 1

        if not self.is_available:
            unavailable_msg = f"Service {self.name} is unavailable"
            raise ExternalServiceError(unavailable_msg, service_name=self.name)

        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000.0)

        if random.random() < self.failure_rate:
            failure_msg = f"Random failure in {self.name}"
            raise TransientError(failure_msg)

        return {
            "service": self.name,
            "status": "success",
            "request_id": self.request_count,
            "data": data,
        }

    def set_failure_rate(self, rate: float) -> None:
        """Set the failure rate for this service."""
        self.failure_rate = max(0.0, min(1.0, rate))

    def set_latency(self, latency_ms: int) -> None:
        """Set the latency for this service."""
        self.latency_ms = max(0, latency_ms)

    def set_availability(self, available: bool) -> None:
        """Set service availability."""
        self.is_available = available


class ResilienceIntegrationTest:
    """Integration test suite for resilience patterns."""

    def __init__(self):
        self.services: dict[str, MockService] = {}
        self.metrics = TestMetrics()
        self.degradation_manager = GracefulDegradationManager()

    def add_service(self, name: str) -> MockService:
        """Add a mock service to the test environment."""
        service = MockService(name)
        self.services[name] = service
        return service

    async def test_circuit_breaker_integration(self) -> TestMetrics:
        """Test circuit breaker integration with real service calls."""
        service = self.add_service("payment_service")
        service.set_failure_rate(0.8)  # High failure rate

        circuit_config = CircuitBreakerConfig(
            failure_threshold=3, recovery_timeout=1.0, half_open_success_threshold=2
        )
        circuit_breaker = CircuitBreaker("payment_circuit", circuit_config)

        test_metrics = TestMetrics()

        # Phase 1: Trigger circuit breaker opening
        for i in range(10):
            test_metrics.total_requests += 1

            if not circuit_breaker.allow_request():
                test_metrics.circuit_breaker_activations += 1
                continue

            try:
                await service.call({"amount": 100, "currency": "USD"})
                circuit_breaker.record_success()
                test_metrics.successful_requests += 1
            except Exception:
                circuit_breaker.record_failure()
                test_metrics.failed_requests += 1

        # Phase 2: Wait for recovery and test
        await asyncio.sleep(circuit_config.recovery_timeout + 0.1)
        service.set_failure_rate(0.1)  # Reduce failure rate

        recovery_start = asyncio.get_event_loop().time()
        for i in range(5):
            test_metrics.total_requests += 1

            if not circuit_breaker.allow_request():
                test_metrics.circuit_breaker_activations += 1
                continue

            try:
                await service.call({"amount": 50, "currency": "EUR"})
                circuit_breaker.record_success()
                test_metrics.successful_requests += 1
                if circuit_breaker.state.value == "closed":
                    test_metrics.recovery_time_seconds = (
                        asyncio.get_event_loop().time() - recovery_start
                    )
                    break
            except Exception:
                circuit_breaker.record_failure()
                test_metrics.failed_requests += 1

        return test_metrics

    async def test_retry_integration(self) -> TestMetrics:
        """Test retry mechanism integration."""
        service = self.add_service("user_service")
        service.set_failure_rate(0.6)  # Moderate failure rate

        retry_config = RetryConfig(
            max_attempts=4, base_delay=0.1, max_delay=0.5, exponential_backoff=True
        )

        retry_policy = create_retry_policy_enhanced(retry_config, "user_retry")
        retry_metrics = get_retry_metrics("user_retry")

        test_metrics = TestMetrics()

        @retry_policy
        async def call_user_service(user_id: int) -> dict[str, Any]:
            # Gradually reduce failure rate on retries
            current_rate = service.failure_rate * (0.7**retry_metrics.current_retry_count)
            service.set_failure_rate(current_rate)

            return await service.call({"user_id": user_id, "action": "get_profile"})

        # Test multiple calls with retry
        for user_id in range(5):
            service.set_failure_rate(0.6)  # Reset failure rate
            test_metrics.total_requests += 1

            try:
                result = await call_user_service(user_id)
                test_metrics.successful_requests += 1
            except Exception:
                test_metrics.failed_requests += 1

        test_metrics.retry_attempts = retry_metrics.total_retries
        return test_metrics

    async def test_graceful_degradation_integration(self) -> TestMetrics:
        """Test graceful degradation integration."""
        primary_service = self.add_service("recommendation_service")
        primary_service.set_availability(False)  # Service unavailable

        # Set up fallback providers
        self.degradation_manager.add_fallback_provider(
            "recommendations",
            DefaultValueProvider(
                [
                    {"id": 1, "title": "Popular Item", "score": 0.8},
                    {"id": 2, "title": "Trending Item", "score": 0.7},
                ]
            ),
        )

        test_metrics = TestMetrics()

        async def get_recommendations(user_id: int) -> list[dict[str, Any]]:
            """Get recommendations with fallback."""
            return await primary_service.call(
                {"user_id": user_id, "type": "personal_recommendations"}
            )

        # Test degraded operation
        for user_id in range(5):
            test_metrics.total_requests += 1

            try:
                result = await self.degradation_manager.execute_with_fallback(
                    "recommendations", lambda: get_recommendations(user_id)
                )

                if isinstance(result, list) and len(result) == 2:
                    test_metrics.fallback_invocations += 1
                else:
                    test_metrics.successful_requests += 1

            except Exception:
                test_metrics.failed_requests += 1

        return test_metrics

    async def test_comprehensive_resilience_stack(self) -> TestMetrics:
        """Test complete resilience stack integration."""
        # Set up services
        auth_service = self.add_service("auth_service")
        data_service = self.add_service("data_service")

        # Configure resilience components
        auth_circuit = CircuitBreaker(
            "auth_circuit", CircuitBreakerConfig(failure_threshold=2, recovery_timeout=1.0)
        )

        data_retry_config = RetryConfig(max_attempts=3, base_delay=0.1, max_delay=0.3)
        data_retry = create_retry_policy_enhanced(data_retry_config, "data_retry")

        # Set up fallback for authentication
        self.degradation_manager.add_fallback_provider(
            "auth", DefaultValueProvider({"user_id": "anonymous", "role": "guest"})
        )

        test_metrics = TestMetrics()

        async def authenticate_user(username: str) -> dict[str, Any]:
            """Authenticate user with circuit breaker."""
            if not auth_circuit.allow_request():
                test_metrics.circuit_breaker_activations += 1
                auth_unavailable_msg = "Auth circuit breaker open"
                raise ExternalServiceError(auth_unavailable_msg, service_name="auth")

            try:
                result = await auth_service.call({"username": username, "action": "authenticate"})
                auth_circuit.record_success()
                return result
            except Exception as exc:
                auth_circuit.record_failure()
                raise exc

        @data_retry
        async def get_user_data(user_id: str) -> dict[str, Any]:
            """Get user data with retry."""
            return await data_service.call(
                {"user_id": user_id, "fields": ["profile", "preferences"]}
            )

        async def process_user_request(username: str) -> dict[str, Any]:
            """Process complete user request with full resilience stack."""
            # Step 1: Authenticate with circuit breaker and fallback
            try:
                auth_result = await authenticate_user(username)
            except Exception:
                # Use fallback authentication
                auth_result = await self.degradation_manager.execute_with_fallback(
                    "auth", lambda: authenticate_user(username)
                )
                test_metrics.fallback_invocations += 1

            user_id = auth_result.get("user_id", "anonymous")

            # Step 2: Get user data with retry
            try:
                data_result = await get_user_data(user_id)
                return {"auth": auth_result, "data": data_result, "status": "success"}
            except Exception:
                # Return partial result
                return {
                    "auth": auth_result,
                    "data": {"error": "Data unavailable"},
                    "status": "partial",
                }

        # Test scenarios
        scenarios = [
            ("auth_failure", lambda: auth_service.set_failure_rate(0.9)),
            ("data_failure", lambda: data_service.set_failure_rate(0.8)),
            (
                "both_failure",
                lambda: (auth_service.set_failure_rate(0.9), data_service.set_failure_rate(0.9)),
            ),
            (
                "recovery",
                lambda: (auth_service.set_failure_rate(0.1), data_service.set_failure_rate(0.1)),
            ),
        ]

        for scenario_name, setup_func in scenarios:
            setup_func()

            for i in range(3):
                test_metrics.total_requests += 1

                try:
                    result = await process_user_request(f"user_{scenario_name}_{i}")

                    if result["status"] == "success":
                        test_metrics.successful_requests += 1
                    elif result["status"] == "partial":
                        test_metrics.successful_requests += 1  # Partial success

                except Exception:
                    test_metrics.failed_requests += 1

        return test_metrics

    async def run_all_tests(self) -> dict[str, TestMetrics]:
        """Run all integration tests."""
        results = {}

        print("Running circuit breaker integration test...")
        results["circuit_breaker"] = await self.test_circuit_breaker_integration()

        print("Running retry integration test...")
        results["retry"] = await self.test_retry_integration()

        print("Running graceful degradation integration test...")
        results["graceful_degradation"] = await self.test_graceful_degradation_integration()

        print("Running comprehensive resilience stack test...")
        results["comprehensive"] = await self.test_comprehensive_resilience_stack()

        return results


# Pytest test cases
@pytest.fixture
def integration_test_suite():
    """Fixture providing integration test suite."""
    return ResilienceIntegrationTest()


@pytest.mark.asyncio
async def test_circuit_breaker_integration(integration_test_suite):
    """Test circuit breaker integration."""
    metrics = await integration_test_suite.test_circuit_breaker_integration()

    assert metrics.total_requests > 0, "Should have made requests"
    assert metrics.circuit_breaker_activations > 0, "Circuit breaker should have activated"
    assert metrics.recovery_time_seconds > 0, "Should have measured recovery time"


@pytest.mark.asyncio
async def test_retry_integration(integration_test_suite):
    """Test retry mechanism integration."""
    metrics = await integration_test_suite.test_retry_integration()

    assert metrics.total_requests > 0, "Should have made requests"
    assert metrics.retry_attempts > 0, "Should have performed retries"
    assert metrics.successful_requests > 0, "Should have some successes"


@pytest.mark.asyncio
async def test_graceful_degradation_integration(integration_test_suite):
    """Test graceful degradation integration."""
    metrics = await integration_test_suite.test_graceful_degradation_integration()

    assert metrics.total_requests > 0, "Should have made requests"
    assert metrics.fallback_invocations > 0, "Should have used fallbacks"


@pytest.mark.asyncio
async def test_comprehensive_integration(integration_test_suite):
    """Test comprehensive resilience integration."""
    metrics = await integration_test_suite.test_comprehensive_resilience_stack()

    assert metrics.total_requests > 0, "Should have made requests"
    assert (
        metrics.successful_requests + metrics.fallback_invocations
    ) > 0, "Should have some successful outcomes"


@pytest.mark.asyncio
async def test_full_integration_suite():
    """Run the complete integration test suite."""
    suite = ResilienceIntegrationTest()
    results = await suite.run_all_tests()

    assert len(results) == 4, "Should run all test categories"

    for test_name, metrics in results.items():
        assert metrics.total_requests > 0, f"{test_name} should have made requests"

    # Print summary
    total_requests = sum(m.total_requests for m in results.values())
    total_successes = sum(m.successful_requests for m in results.values())
    total_fallbacks = sum(m.fallback_invocations for m in results.values())

    print(f"\\nIntegration Test Summary:")
    print(f"Total requests: {total_requests}")
    print(f"Successful requests: {total_successes}")
    print(f"Fallback invocations: {total_fallbacks}")
    print(f"Success rate: {(total_successes + total_fallbacks) / total_requests:.2%}")


if __name__ == "__main__":
    # Example usage
    async def main():
        suite = ResilienceIntegrationTest()
        results = await suite.run_all_tests()

        print("\\n=== Integration Test Results ===")
        for test_name, metrics in results.items():
            print(f"\\n{test_name.upper()}:")
            print(f"  Total requests: {metrics.total_requests}")
            print(f"  Successful: {metrics.successful_requests}")
            print(f"  Failed: {metrics.failed_requests}")
            print(f"  Circuit breaker activations: {metrics.circuit_breaker_activations}")
            print(f"  Retry attempts: {metrics.retry_attempts}")
            print(f"  Fallback invocations: {metrics.fallback_invocations}")

            if metrics.recovery_time_seconds > 0:
                print(f"  Recovery time: {metrics.recovery_time_seconds:.2f}s")

        # Calculate overall metrics
        total_requests = sum(m.total_requests for m in results.values())
        total_successes = sum(m.successful_requests for m in results.values())
        total_fallbacks = sum(m.fallback_invocations for m in results.values())

        success_rate = (
            (total_successes + total_fallbacks) / total_requests if total_requests > 0 else 0
        )

        print(f"\\n=== OVERALL SUMMARY ===")
        print(f"Total requests across all tests: {total_requests}")
        print(f"Effective success rate: {success_rate:.2%}")
        print("Resilience integration tests completed successfully!")

    asyncio.run(main())


__all__ = ["ResilienceIntegrationTest", "MockService", "TestMetrics"]
