"""Regression coverage for ownership of circuit-breaker admission slots."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from marty_common.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig


@pytest.mark.asyncio
async def test_cancelled_call_releases_slot_without_counting_dependency_failure():
    breaker = CircuitBreaker("cancelled", CircuitBreakerConfig(max_concurrent_requests=1))
    started = asyncio.Event()

    @breaker.decorate_async
    async def dependency(block):
        if block:
            started.set()
            await asyncio.Event().wait()
        return "recovered"

    pending = asyncio.create_task(dependency(True))
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        assert breaker.stats()["concurrent_requests"] == 1
    finally:
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending

    stats = breaker.stats()
    assert stats["concurrent_requests"] == 0
    assert stats["total_successes"] == stats["total_failures"] == 0
    assert stats["state"] == "closed"
    assert await dependency(False) == "recovered"
    assert breaker.stats()["total_successes"] == 1


def test_sync_base_exception_releases_slot_and_propagates():
    class Interrupted(BaseException):
        pass

    breaker = CircuitBreaker("interrupted", CircuitBreakerConfig(max_concurrent_requests=1))
    interruption = Interrupted()

    @breaker.decorate
    def dependency(fail):
        if fail:
            raise interruption
        return "recovered"

    with pytest.raises(Interrupted) as caught:
        dependency(True)
    assert caught.value is interruption
    assert breaker.stats()["concurrent_requests"] == 0
    assert breaker.stats()["total_failures"] == 0
    assert dependency(False) == "recovered"


class SimultaneousAdmissionLock:
    """Schedule both callers after their first locked admission decision."""

    def __init__(self):
        self.lock = threading.RLock()
        self.local = threading.local()
        self.first_admissions = threading.Barrier(2)
        self.exits = 0

    def __enter__(self):
        self.lock.acquire()
        self.local.depth = getattr(self.local, "depth", 0) + 1
        return self

    def __exit__(self, *args):
        self.local.depth -= 1
        if self.local.depth == 0:
            self.exits += 1
        synchronize = self.local.depth == 0 and self.exits <= 2
        self.lock.release()
        if synchronize:
            self.first_admissions.wait(timeout=5)


def test_concurrent_decorated_calls_reserve_the_last_slot_atomically():
    breaker = CircuitBreaker("concurrent", CircuitBreakerConfig(max_concurrent_requests=1))
    breaker._lock = SimultaneousAdmissionLock()

    @breaker.decorate
    def dependency():
        return "completed"

    def invoke():
        try:
            return dependency()
        except RuntimeError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = [pool.submit(invoke) for _ in range(2)]
        assert sorted(call.result(timeout=5) for call in calls) == ["completed", "rejected"]

    stats = breaker.stats()
    assert stats["concurrent_requests"] == 0
    assert stats["total_requests"] == stats["total_successes"] == stats["total_rejected"] == 1


@pytest.mark.parametrize("failure", [ConnectionError("offline"), ValueError("invalid")])
def test_completed_calls_release_slots_and_preserve_error_classification(failure):
    breaker = CircuitBreaker(
        "failure", CircuitBreakerConfig(max_concurrent_requests=1, failure_threshold=1)
    )

    @breaker.decorate
    def dependency():
        raise failure

    with pytest.raises(type(failure)) as caught:
        dependency()
    assert caught.value is failure
    assert breaker.stats()["concurrent_requests"] == 0
    assert breaker.state.value == ("open" if isinstance(failure, ConnectionError) else "closed")


def test_public_admission_check_remains_reservation_free():
    breaker = CircuitBreaker("preflight", CircuitBreakerConfig(max_concurrent_requests=1))
    assert breaker.allow_request()
    assert breaker.allow_request()
    assert breaker.stats()["concurrent_requests"] == 0
    assert breaker.stats()["total_requests"] == 0


@pytest.mark.asyncio
async def test_decorators_preserve_custom_admission_policy():
    class DeniedBreaker(CircuitBreaker):
        def allow_request(self):
            return False

    breaker = DeniedBreaker("custom")
    called = []

    def dependency():
        called.append(1)

    with pytest.raises(RuntimeError, match="Circuit 'custom'"):
        breaker.decorate(dependency)()
    with pytest.raises(RuntimeError, match="Circuit 'custom'"):
        await breaker.decorate_async(dependency)()
    assert called == []
    assert breaker.stats()["concurrent_requests"] == breaker.stats()["total_requests"] == 0


@pytest.mark.asyncio
async def test_disabled_decorators_collect_outcomes_without_admission_limits():
    breaker = CircuitBreaker(
        "disabled",
        CircuitBreakerConfig(max_concurrent_requests=0, failure_threshold=1),
        enabled=False,
    )

    def success():
        return "completed"

    async def failure():
        raise ConnectionError("offline")

    assert breaker.decorate(success)() == "completed"
    with pytest.raises(ConnectionError, match="offline"):
        await breaker.decorate_async(failure)()
    assert breaker.state.value == "closed"
    assert breaker.stats()["concurrent_requests"] == 0
    assert breaker.stats()["total_successes"] == breaker.stats()["total_failures"] == 1
