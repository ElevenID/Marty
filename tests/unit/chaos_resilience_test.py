"""Deterministic acceptance of retained Python resilience primitives."""

import asyncio
from types import SimpleNamespace

import pytest

from marty_common.resilience import circuit_breaker as breaker_module
from marty_common.resilience.chaos_testing import ChaosConfig, ChaosInjector, ChaosType, chaos_context
from marty_common.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from marty_common.resilience.enhanced_errors import ExternalServiceError, TransientError
from marty_common.resilience.graceful_degradation import DefaultValueProvider, GracefulDegradationManager
from marty_common.resilience.retry_enhanced import RetryConfig, create_retry_policy_enhanced


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,error", [
    (ChaosType.NETWORK_FAILURE, TransientError),
    (ChaosType.SERVICE_UNAVAILABLE, ExternalServiceError),
])
async def test_injected_failure_propagates_and_releases_target(kind, error):
    injector = ChaosInjector()
    with pytest.raises(error):
        await injector.inject_chaos(ChaosConfig(kind, probability=1), "dependency")
    assert not injector.is_chaos_active("dependency")
    assert injector.get_chaos_history()[0]["target"] == "dependency"


@pytest.mark.asyncio
async def test_disabled_injection_leaves_dependency_available():
    injector = ChaosInjector()
    await injector.inject_chaos(ChaosConfig(ChaosType.NETWORK_FAILURE, enabled=False))
    assert not injector.is_chaos_active()
    assert injector.get_chaos_history() == []


@pytest.mark.asyncio
async def test_context_exit_cancels_pending_delay_and_cleans_target(monkeypatch):
    injector = ChaosInjector()
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def delay(config):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(injector, "_inject_network_delay", delay)
    async with chaos_context(injector, ChaosConfig(ChaosType.NETWORK_DELAY, probability=1)):
        await asyncio.wait_for(started.wait(), timeout=2)
        assert injector.is_chaos_active()
    assert stopped.is_set()
    assert not injector.is_chaos_active()


def test_breaker_failed_probe_reopens_then_successful_probes_recover(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(breaker_module, "time", SimpleNamespace(time=lambda: now[0]))
    breaker = CircuitBreaker("recovery", CircuitBreakerConfig(
        failure_threshold=1, recovery_timeout=5, half_open_success_threshold=2))
    assert breaker.allow_request()
    breaker.record_failure(ConnectionError())
    assert not breaker.allow_request()
    now[0] += 5
    assert breaker.allow_request()
    breaker.record_failure(ConnectionError())
    assert not breaker.allow_request()
    now[0] += 5
    for _ in range(2):
        assert breaker.allow_request()
        breaker.record_success()
    assert breaker.state.value == "closed"
    assert breaker.allow_request()


@pytest.mark.asyncio
async def test_dependency_outage_is_bounded_falls_back_and_recovers(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(breaker_module, "time", SimpleNamespace(time=lambda: now[0]))
    breaker = CircuitBreaker("dependency", CircuitBreakerConfig(
        failure_threshold=2, recovery_timeout=5, half_open_success_threshold=1))
    manager = GracefulDegradationManager()
    manager.add_fallback_provider("catalog", DefaultValueProvider("cached catalog"))
    unavailable = True
    attempts = []

    @create_retry_policy_enhanced(RetryConfig(
        max_attempts=3, base_delay=0, max_delay=0, exponential_backoff=False, jitter=False))
    async def dependency():
        if not breaker.allow_request():
            raise ConnectionError("circuit open")
        attempts.append(1)
        if unavailable:
            breaker.record_failure(ConnectionError())
            raise ConnectionError("dependency unavailable")
        breaker.record_success()
        return "live catalog"

    assert await manager.execute_with_fallback("catalog", dependency) == "cached catalog"
    assert len(attempts) == 2
    assert breaker.state.value == "open"
    assert await manager.execute_with_fallback("catalog", dependency) == "cached catalog"
    assert len(attempts) == 2
    unavailable = False
    now[0] += 5
    manager.set_feature_health("catalog", True)
    assert await manager.execute_with_fallback("catalog", dependency) == "live catalog"
    assert breaker.state.value == "closed"
    assert len(attempts) == 3


@pytest.mark.asyncio
async def test_exhausted_dependency_without_fallback_remains_failure():
    manager = GracefulDegradationManager()

    async def unavailable():
        raise ConnectionError("offline")

    with pytest.raises(TransientError, match="no fallback"):
        await manager.execute_with_fallback("catalog", unavailable)
