"""Exercise actual limiter code, Redis transactions and synchronous gRPC calls."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import grpc
import pytest
import redis


@pytest.fixture(scope="module")
def rate_module():
    # Load the maintained module without unrelated package initialization.
    path = (
        Path(__file__).resolve().parents[2]
        / "packages/marty-common/marty_common/middleware/rate_limiter.py"
    )
    spec = importlib.util.spec_from_file_location("tested_marty_rate_limiter", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name)


class Clock:
    def __init__(self):
        self.now = 100_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def make_limiter(rate_module, clock):
    def make(backend=None, **overrides):
        values = dict(
            requests_per_second=10,
            requests_per_minute=100,
            requests_per_hour=1000,
            burst_size=10,
        )
        values.update(overrides)
        limiter = rate_module.RateLimiter(backend, clock=clock)
        limiter.default_rule = rate_module.RateLimitRule(**values)
        return limiter

    return make


@pytest.fixture(scope="module")
def redis_connection(tmp_path_factory):
    """Use the CI Redis service or an isolated, nonpersistent local server."""
    url = os.environ.get("MARTY_TEST_REDIS_URL")
    if url:
        client = redis.Redis.from_url(url, socket_timeout=3, socket_connect_timeout=3)
        assert client.ping()
        client.close()
        yield {"url": url}
        return
    executable = os.environ.get("MARTY_TEST_REDIS_SERVER") or shutil.which(
        "redis-server"
    )
    if executable is None:
        pytest.fail(
            "Install redis-server or set MARTY_TEST_REDIS_URL/MARTY_TEST_REDIS_SERVER; real Redis tests must run"
        )
    directory = tmp_path_factory.mktemp("rate-limit-redis")
    socket = directory / "redis.sock"
    with (directory / "redis.log").open("wb") as output:
        process = subprocess.Popen(
            [
                executable,
                "--port",
                "0",
                "--unixsocket",
                str(socket),
                "--save",
                "",
                "--appendonly",
                "no",
            ],
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        client = redis.Redis(unix_socket_path=str(socket), socket_timeout=3)
        try:
            deadline = time.monotonic() + 5
            while True:
                try:
                    if client.ping():
                        break
                except redis.ConnectionError:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        pytest.fail("isolated Redis did not become ready")
                    time.sleep(0.01)
            yield {"unix_socket_path": str(socket)}
        finally:
            client.close()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@pytest.fixture(params=[False, True], ids=["bytes", "text"])
def redis_backend(request, redis_connection, rate_module):
    options = dict(
        decode_responses=request.param, socket_timeout=3, socket_connect_timeout=3
    )
    if "url" in redis_connection:
        client = redis.Redis.from_url(redis_connection["url"], **options)
    else:
        client = redis.Redis(**redis_connection, **options)
    prefix = f"marty:test:rate-limit:{uuid.uuid4().hex}:"
    backend = rate_module.RedisRateLimitBackend(client, prefix)
    try:
        yield backend
    finally:
        keys = list(client.scan_iter(match=f"{prefix}*"))
        if keys:
            client.delete(*keys)
        client.close()


def test_minute_limit_has_actual_retry_time_and_exact_boundary(make_limiter, clock):
    limiter = make_limiter(requests_per_minute=1)
    assert limiter.check_limit("one").allowed
    rejected = limiter.check_limit("one")
    assert not rejected.allowed
    assert rejected.retry_after == 60
    assert rejected.reset_time == clock.now + 60
    assert limiter.get_client_stats("one")["total_requests"] == 1
    clock.now += 60
    assert limiter.check_limit("one").allowed


def test_retry_waits_for_both_windows_and_handles_lowered_limits(make_limiter, clock):
    limiter = make_limiter(requests_per_minute=3, requests_per_hour=3)
    for _ in range(3):
        assert limiter.check_limit("one").allowed
        clock.now += 1
    limiter.default_rule.requests_per_minute = 1
    limiter.default_rule.requests_per_hour = 1
    rejected = limiter.check_limit("one")
    assert rejected.reset_time == 100_002 + 3600
    clock.now = rejected.reset_time
    assert limiter.check_limit("one").allowed


def test_burst_cost_denial_does_not_consume_window_and_clock_rollback_is_safe(
    make_limiter, clock
):
    limiter = make_limiter(burst_size=3, requests_per_second=2)
    assert limiter.check_limit("one", request_cost=3).allowed
    rejected = limiter.check_limit("one")
    assert rejected.retry_after == 0.5
    assert limiter.get_client_stats("one")["requests_last_hour"] == 1
    clock.now -= 10
    rejected = limiter.check_limit("one")
    assert rejected.retry_after == 10.5
    clock.now += 10.5
    assert limiter.check_limit("one").allowed


def test_memory_buckets_are_snapshots_and_slow_refill_survives_cleanup(
    make_limiter, clock
):
    limiter = make_limiter(requests_per_second=0.0001, burst_size=1)
    assert limiter.check_limit("one").allowed
    snapshot = limiter.backend.get_client_data("one")
    snapshot.tokens = 100
    snapshot.requests_in_window.clear()
    clock.now += 3601
    assert not limiter.check_limit("one").allowed
    assert limiter.get_client_stats("one")["total_requests"] == 1


@pytest.mark.parametrize(
    "setting",
    [
        {"requests_per_second": 0},
        {"requests_per_second": float("nan")},
        {"requests_per_minute": -1},
        {"requests_per_hour": float("inf")},
        {"burst_size": 0},
        {"burst_size": True},
    ],
)
def test_invalid_rules_fail_before_admission(make_limiter, setting):
    with pytest.raises(ValueError):
        make_limiter(**setting)


@pytest.mark.parametrize("cost", [0, -1, True, 1.5, 11])
def test_invalid_costs_fail_before_admission(make_limiter, cost):
    limiter = make_limiter()
    with pytest.raises(ValueError):
        limiter.check_limit("one", request_cost=cost)
    assert limiter.get_client_stats("one")["total_requests"] == 0


def test_memory_shared_backend_admission_is_atomic(rate_module, make_limiter):
    backend = rate_module.MemoryRateLimitBackend()
    limiters = [make_limiter(backend, requests_per_minute=5) for _ in range(20)]
    barrier = threading.Barrier(len(limiters))

    def attempt(limiter):
        barrier.wait(timeout=5)
        return limiter.check_limit("same-client").allowed

    with ThreadPoolExecutor(max_workers=len(limiters)) as pool:
        assert sum(pool.map(attempt, limiters)) == 5
    assert limiters[0].get_client_stats("same-client")["total_requests"] == 5


def test_redis_preserves_windows_across_instances(
    redis_backend, rate_module, make_limiter, clock
):
    first = make_limiter(redis_backend, requests_per_minute=1, requests_per_hour=2)
    assert first.check_limit("one").allowed
    second_backend = rate_module.RedisRateLimitBackend(
        redis_backend.redis, redis_backend.key_prefix
    )
    second = make_limiter(second_backend, requests_per_minute=1, requests_per_hour=2)
    assert not second.check_limit("one").allowed
    assert second.get_client_stats("one")["requests_last_minute"] == 1
    assert second.backend.get_client_data("one").tokens == 9
    clock.now += 60
    assert second.check_limit("one").allowed
    clock.now += 60
    rejected = first.check_limit("one")
    assert not rejected.allowed
    assert rejected.reset_time == 100_000 + 3600
    assert first.get_client_stats("one")["total_requests"] == 2


def test_redis_shared_admission_is_atomic(redis_backend, rate_module, make_limiter):
    limiters = [
        make_limiter(
            rate_module.RedisRateLimitBackend(
                redis_backend.redis, redis_backend.key_prefix
            ),
            requests_per_minute=5,
        )
        for _ in range(20)
    ]
    barrier = threading.Barrier(len(limiters))

    def attempt(limiter):
        barrier.wait(timeout=5)
        return limiter.check_limit("same-client").allowed

    with ThreadPoolExecutor(max_workers=len(limiters)) as pool:
        assert sum(pool.map(attempt, limiters)) == 5
    assert limiters[0].get_client_stats("same-client")["total_requests"] == 5


def test_redis_retains_slow_refill_state(redis_backend, make_limiter):
    limiter = make_limiter(redis_backend, requests_per_second=0.0001, burst_size=1)
    assert limiter.check_limit("one").allowed
    assert redis_backend.redis.ttl(redis_backend._get_key("one")) > 9990


def test_redis_retention_includes_clock_rollback(redis_backend, make_limiter, clock):
    limiter = make_limiter(redis_backend, requests_per_second=0.0001, burst_size=1)
    assert limiter.check_limit("one").allowed
    clock.now -= 10
    rejected = limiter.check_limit("one")
    assert not rejected.allowed
    assert rejected.retry_after == 10010
    # A new full bucket must not appear ten seconds before token refill.
    assert redis_backend.redis.ttl(redis_backend._get_key("one")) >= 10009


@pytest.mark.parametrize(
    "corruption", ["legacy", "malformed-history", "future-history", "wrong-type"]
)
def test_redis_invalid_or_legacy_storage_never_creates_a_new_burst(
    redis_backend, rate_module, make_limiter, corruption
):
    limiter = make_limiter(redis_backend)
    assert limiter.check_limit("one").allowed
    key = redis_backend._get_key("one")
    if corruption == "legacy":
        redis_backend.redis.hdel(key, "requests_in_window")
    elif corruption == "malformed-history":
        redis_backend.redis.hset(key, "requests_in_window", "not-json")
    elif corruption == "future-history":
        redis_backend.redis.hset(key, "requests_in_window", "[9999999]")
    else:
        redis_backend.redis.delete(key)
        redis_backend.redis.set(key, "wrong-type")
    with pytest.raises(rate_module.RateLimitBackendError):
        limiter.check_limit("one")


def test_redis_failure_and_bounded_contention_are_explicit(rate_module, make_limiter):
    class BrokenClient:
        def pipeline(self):
            raise redis.ConnectionError("simulated connection failure")

        def hgetall(self, key):
            raise redis.ConnectionError("simulated connection failure")

    backend = rate_module.RedisRateLimitBackend(BrokenClient())
    with pytest.raises(rate_module.RateLimitBackendError):
        make_limiter(backend).check_limit("one")
    with pytest.raises(rate_module.RateLimitBackendError):
        backend.get_client_data("one")
    with pytest.raises(rate_module.RateLimitBackendError):
        backend.set_client_data("one", rate_module.ClientBucket(1, 1))

    class ContendedPipeline:
        attempts = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def watch(self, key):
            self.attempts += 1
            raise redis.WatchError("concurrent update")

    class ContendedClient:
        pipe = ContendedPipeline()

        def pipeline(self):
            return self.pipe

    client = ContendedClient()
    backend = rate_module.RedisRateLimitBackend(client, max_retries=3)
    with pytest.raises(rate_module.RateLimitBackendError):
        make_limiter(backend).check_limit("one")
    assert client.pipe.attempts == 3


@pytest.fixture
def rpc_server(rate_module):
    servers = []

    def start(limiter):
        server = grpc.server(
            ThreadPoolExecutor(max_workers=4),
            interceptors=[rate_module.RateLimitMiddleware(limiter)],
        )
        common = dict(
            request_deserializer=lambda data: data.decode(),
            response_serializer=lambda text: text.encode(),
        )
        handlers = {
            "Unary": grpc.unary_unary_rpc_method_handler(
                lambda request, context: request.upper(), **common
            ),
            "ServerStream": grpc.unary_stream_rpc_method_handler(
                lambda request, context: iter([request.upper(), "DONE"]), **common
            ),
            "ClientStream": grpc.stream_unary_rpc_method_handler(
                lambda requests, context: "".join(requests).upper(), **common
            ),
            "Bidi": grpc.stream_stream_rpc_method_handler(
                lambda requests, context: (value.upper() for value in requests),
                **common,
            ),
        }
        server.add_generic_rpc_handlers(
            [grpc.method_handlers_generic_handler("test.Limiter", handlers)]
        )
        port = server.add_insecure_port("127.0.0.1:0")
        assert port
        server.start()
        channel = grpc.insecure_channel(f"127.0.0.1:{port}")
        grpc.channel_ready_future(channel).result(timeout=5)
        servers.append((server, channel))
        return channel

    yield start
    for server, channel in servers:
        channel.close()
        server.stop(0).wait(timeout=5)


def test_real_grpc_preserves_all_cardinalities_and_serializers(
    rpc_server, make_limiter
):
    limiter = make_limiter()
    channel = rpc_server(limiter)
    common = dict(
        request_serializer=lambda value: value.encode(),
        response_deserializer=lambda data: data.decode(),
    )
    options = dict(metadata=(("client-id", "stream-client"),), timeout=5)
    assert (
        channel.unary_unary("/test.Limiter/Unary", **common)("hello", **options)
        == "HELLO"
    )
    assert list(
        channel.unary_stream("/test.Limiter/ServerStream", **common)("hello", **options)
    ) == ["HELLO", "DONE"]
    assert (
        channel.stream_unary("/test.Limiter/ClientStream", **common)(
            iter(["a", "b"]), **options
        )
        == "AB"
    )
    assert list(
        channel.stream_stream("/test.Limiter/Bidi", **common)(
            iter(["a", "b"]), **options
        )
    ) == ["A", "B"]
    assert limiter.get_client_stats("stream-client")["total_requests"] == 4
    with pytest.raises(grpc.RpcError) as error:
        channel.unary_unary("/test.Limiter/Unknown")(b"", timeout=5)
    assert error.value.code() == grpc.StatusCode.UNIMPLEMENTED


def test_real_grpc_rejection_keeps_all_metadata_and_rounds_retry_up(
    rpc_server, make_limiter
):
    channel = rpc_server(make_limiter(requests_per_second=2, burst_size=1))
    call = channel.unary_unary("/test.Limiter/Unary")
    metadata = (("client-id", "one"),)
    assert call(b"ok", metadata=metadata, timeout=5) == b"OK"
    with pytest.raises(grpc.RpcError) as error:
        call(b"blocked", metadata=metadata, timeout=5)
    assert error.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
    trailers = dict(error.value.trailing_metadata())
    assert trailers["retry-after"] == "1"
    assert trailers["x-ratelimit-remaining"] == "0"
    assert trailers["x-ratelimit-reset"] == "100001"


def test_real_grpc_storage_failure_is_unavailable_without_running_handler(
    rate_module, rpc_server
):
    class UnavailableLimiter:
        def check_limit(self, client_id, client_type):
            raise rate_module.RateLimitBackendError("private storage detail")

    channel = rpc_server(UnavailableLimiter())
    with pytest.raises(grpc.RpcError) as error:
        channel.unary_unary("/test.Limiter/Unary")(b"must not run", timeout=5)
    assert error.value.code() == grpc.StatusCode.UNAVAILABLE
    assert error.value.details() == "Rate-limit storage is unavailable"


def test_legacy_backend_subclass_retains_public_contract(rate_module, make_limiter):
    class LegacyBackend(rate_module.RateLimitBackend):
        buckets = {}

        def get_client_data(self, client_id):
            return self.buckets.get(client_id)

        def set_client_data(self, client_id, bucket):
            self.buckets[client_id] = bucket

        def cleanup_expired(self, before_timestamp):
            pass

    limiter = make_limiter(LegacyBackend(), requests_per_minute=1)
    assert limiter.check_limit("one").allowed
    assert not limiter.check_limit("one").allowed
