"""Exercise disabled breaker policy and successful outbound recovery probes."""

from types import SimpleNamespace

import pytest

from marty_common.resilience import circuit_breaker as breaker_module
from marty_common.resilience import interceptors, outbound
from marty_common.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig


@pytest.mark.parametrize("setting", ["false", "0", "no"])
def test_disabled_breaker_never_trips_or_seeds_enabled_registry(monkeypatch, setting):
    monkeypatch.setattr(interceptors, "_CIRCUIT_BREAKERS", {})
    monkeypatch.setenv("MARTY_CIRCUIT_BREAKER_ENABLED", setting)
    disabled = interceptors.get_circuit_breaker("/test/disabled")
    for _ in range(20):
        assert disabled.allow_request()
        disabled.record_failure(ConnectionError("offline"))
    assert disabled.state.value == "closed"
    assert interceptors._CIRCUIT_BREAKERS == {}

    monkeypatch.setenv("MARTY_CIRCUIT_BREAKER_ENABLED", "true")
    enabled = interceptors.get_circuit_breaker("/test/disabled")
    assert enabled is not disabled
    for _ in range(enabled.config.failure_threshold):
        assert enabled.allow_request()
        enabled.record_failure(ConnectionError("offline"))
    assert not enabled.allow_request()


def test_disabling_does_not_reuse_or_mutate_an_open_breaker(monkeypatch):
    monkeypatch.setattr(interceptors, "_CIRCUIT_BREAKERS", {})
    monkeypatch.setenv("MARTY_CIRCUIT_BREAKER_ENABLED", "true")
    enabled = interceptors.get_circuit_breaker("/test/cached")
    for _ in range(enabled.config.failure_threshold):
        enabled.record_failure(ConnectionError("offline"))
    assert enabled.state.value == "open"

    monkeypatch.setenv("MARTY_CIRCUIT_BREAKER_ENABLED", "false")
    disabled = interceptors.get_circuit_breaker("/test/cached")
    assert disabled.allow_request()
    disabled.record_success()
    disabled.record_failure(ConnectionError("offline"))
    assert disabled.state.value == "closed"
    assert enabled.state.value == "open"

    monkeypatch.setenv("MARTY_CIRCUIT_BREAKER_ENABLED", "true")
    assert interceptors.get_circuit_breaker("/test/cached") is enabled


@pytest.mark.asyncio
@pytest.mark.parametrize("awaitable", [False, True])
async def test_successful_outbound_probes_close_half_open_breaker(monkeypatch, awaitable):
    now = [100.0]
    monkeypatch.setattr(breaker_module, "time", SimpleNamespace(time=lambda: now[0]))
    breaker = CircuitBreaker(
        "outbound",
        CircuitBreakerConfig(
            failure_threshold=1, recovery_timeout=5, half_open_success_threshold=2
        ),
    )
    monkeypatch.setattr(outbound, "_OUTBOUND_BREAKERS", {"outbound": breaker})
    breaker.record_failure(ConnectionError("offline"))
    assert breaker.state.value == "open"
    now[0] += 5
    response = object()
    calls = []

    async def async_response():
        return response

    def dependency():
        calls.append(1)
        return async_response() if awaitable else response

    for expected_state in ["half_open", "closed"]:
        assert (
            await outbound.async_call_with_resilience(
                "outbound", dependency, retry_kwargs={"max_attempts": 1}
            )
            is response
        )
        assert breaker.state.value == expected_state
    assert len(calls) == 2
    assert breaker.stats()["total_successes"] == 2
    assert breaker.stats()["total_failures"] == 1


@pytest.mark.asyncio
async def test_failed_outbound_probe_propagates_and_reopens(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(breaker_module, "time", SimpleNamespace(time=lambda: now[0]))
    breaker = CircuitBreaker(
        "outbound", CircuitBreakerConfig(failure_threshold=1, recovery_timeout=5)
    )
    monkeypatch.setattr(outbound, "_OUTBOUND_BREAKERS", {"outbound": breaker})
    breaker.record_failure(ConnectionError("offline"))
    now[0] += 5
    failure = ConnectionError("still offline")

    async def dependency():
        raise failure

    with pytest.raises(ConnectionError) as caught:
        await outbound.async_call_with_resilience(
            "outbound", dependency, retry_kwargs={"max_attempts": 1}
        )
    assert caught.value is failure
    assert breaker.state.value == "open"
    assert breaker.stats()["total_successes"] == 0
    assert breaker.stats()["total_failures"] == 2
