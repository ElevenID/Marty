import base64
from datetime import datetime, timedelta, timezone

import pytest

from marty_backend_common.infrastructure import (
    DatabaseConfig,
    DatabaseManager,
    OutboxDispatcher,
    OutboxRepository,
)
from marty_backend_common.infrastructure.outbox import (
    OutboxDispatcherSettings,
    _decode_headers,
    _encode_headers,
)


@pytest.fixture
async def database():
    database = DatabaseManager(DatabaseConfig(url="sqlite+aiosqlite:///:memory:"))
    await database.create_all()
    try:
        yield database
    finally:
        await database.dispose()


# ------------------------------------------------------------------
# Existing tests (happy path)
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_outbox_repository_enqueue_and_claim(database):
    async with database.session_scope() as session:
        repo = OutboxRepository(session)
        await repo.enqueue(topic="test.topic", payload=b"{}", key=b"key")

    async with database.session_scope() as session:
        repo = OutboxRepository(session)
        batch = await repo.claim_batch(limit=5)
        assert len(batch) == 1
        record = batch[0]
        assert record.topic == "test.topic"
        assert bytes(record.key) == b"key"
        await repo.mark_processed(record)


class _StubEventBus:
    def __init__(self) -> None:
        self.messages = []

    async def publish(self, message):
        self.messages.append(message)


@pytest.mark.asyncio
async def test_outbox_dispatcher_flushes_messages(database):
    async with database.session_scope() as session:
        repo = OutboxRepository(session)
        await repo.enqueue(topic="flush.topic", payload=b"payload", key=None)

    stub_bus = _StubEventBus()
    dispatcher = OutboxDispatcher(database, stub_bus)

    processed = await dispatcher.flush_once()
    assert processed == 1
    assert len(stub_bus.messages) == 1

    async with database.session_scope() as session:
        repo = OutboxRepository(session)
        remaining = await repo.claim_batch(limit=5)
        assert remaining == []


# ------------------------------------------------------------------
# Headers encode/decode round-trip
# ------------------------------------------------------------------
def test_encode_decode_headers_roundtrip():
    headers = {"content-type": b"application/json", "x-trace-id": b"\x01\x02\x03"}
    encoded = _encode_headers(headers)
    assert isinstance(encoded, dict)
    # Encoded values should be base64 strings
    for v in encoded.values():
        assert isinstance(v, str)
        base64.b64decode(v)  # should not raise

    decoded = _decode_headers(encoded)
    assert decoded == headers


def test_encode_headers_none():
    assert _encode_headers(None) is None
    assert _decode_headers(None) is None


def test_encode_headers_empty():
    assert _encode_headers({}) is None
    assert _decode_headers({}) is None


# ------------------------------------------------------------------
# Enqueue with headers
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enqueue_with_headers(database):
    headers = {"x-request-id": b"req-123"}
    async with database.session_scope() as session:
        repo = OutboxRepository(session)
        record = await repo.enqueue(
            topic="headers.topic", payload=b"data", headers=headers
        )
        assert record.headers is not None

    async with database.session_scope() as session:
        repo = OutboxRepository(session)
        batch = await repo.claim_batch(limit=5)
        assert len(batch) == 1
        # Headers should be stored encoded on the record
        assert batch[0].headers is not None


# ------------------------------------------------------------------
# claim_batch respects available_at in future
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_claim_batch_excludes_future_available_at(database):
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    async with database.session_scope() as session:
        repo = OutboxRepository(session)
        await repo.enqueue(topic="future.topic", payload=b"data", available_at=future)
        # Also enqueue one that IS available now
        await repo.enqueue(topic="now.topic", payload=b"data2")

    async with database.session_scope() as session:
        repo = OutboxRepository(session)
        batch = await repo.claim_batch(limit=10)
        topics = [r.topic for r in batch]
        assert "now.topic" in topics
        assert "future.topic" not in topics


# ------------------------------------------------------------------
# mark_failed below max_attempts (reschedule)
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mark_failed_below_max_reschedules(database):
    async with database.session_scope() as session:
        repo = OutboxRepository(session)
        record = await repo.enqueue(topic="retry.topic", payload=b"data")
        await session.flush()

        original_available_at = record.available_at
        await repo.mark_failed(record, "transient error", timedelta(seconds=30), max_attempts=5)

        assert record.attempts == 1
        assert record.last_error == "transient error"
        assert record.available_at > original_available_at


# ------------------------------------------------------------------
# mark_failed at max_attempts (dead-letter)
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mark_failed_at_max_moves_to_dlq(database):
    from marty_backend_common.infrastructure.models import EventDeadLetterRecord
    from sqlalchemy import select

    async with database.session_scope() as session:
        repo = OutboxRepository(session)
        record = await repo.enqueue(topic="dlq.topic", payload=b"important", key=b"k1")
        await session.flush()

        # Simulate prior failures
        record.attempts = 4
        await repo.mark_failed(record, "permanent failure", timedelta(seconds=5), max_attempts=5)
        await session.flush()

        # DLQ record should exist
        result = await session.execute(select(EventDeadLetterRecord))
        dlq_records = list(result.scalars().all())
        assert len(dlq_records) == 1
        assert dlq_records[0].original_topic == "dlq.topic"
        assert dlq_records[0].last_error == "permanent failure"
        assert dlq_records[0].attempts == 5


# ------------------------------------------------------------------
# mark_failed truncates long error messages
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mark_failed_truncates_error(database):
    async with database.session_scope() as session:
        repo = OutboxRepository(session)
        record = await repo.enqueue(topic="truncate.topic", payload=b"data")
        await session.flush()

        long_error = "x" * 2000
        await repo.mark_failed(record, long_error, timedelta(seconds=5), max_attempts=10)
        assert len(record.last_error) <= 1024


# ------------------------------------------------------------------
# requeue delays records
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_requeue_sets_future_available_at(database):
    async with database.session_scope() as session:
        repo = OutboxRepository(session)
        r1 = await repo.enqueue(topic="rq1", payload=b"a")
        r2 = await repo.enqueue(topic="rq2", payload=b"b")
        await session.flush()

        before = datetime.now(timezone.utc)
        await repo.requeue([r1, r2], timedelta(minutes=10))

        assert r1.available_at > before
        assert r2.available_at > before


# ------------------------------------------------------------------
# _compute_retry_delay (exponential backoff with cap)
# ------------------------------------------------------------------
def test_compute_retry_delay_exponential_backoff():
    settings = OutboxDispatcherSettings(initial_retry_delay=5.0, max_retry_delay=300.0)
    database = DatabaseManager(DatabaseConfig(url="sqlite+aiosqlite:///:memory:"))
    stub_bus = _StubEventBus()
    dispatcher = OutboxDispatcher(database, stub_bus, settings)

    d1 = dispatcher._compute_retry_delay(1)
    d2 = dispatcher._compute_retry_delay(2)
    d3 = dispatcher._compute_retry_delay(3)

    assert d1.total_seconds() == 5.0   # 5 * 2^0
    assert d2.total_seconds() == 10.0  # 5 * 2^1
    assert d3.total_seconds() == 20.0  # 5 * 2^2


def test_compute_retry_delay_capped_at_max():
    settings = OutboxDispatcherSettings(initial_retry_delay=5.0, max_retry_delay=60.0)
    database = DatabaseManager(DatabaseConfig(url="sqlite+aiosqlite:///:memory:"))
    stub_bus = _StubEventBus()
    dispatcher = OutboxDispatcher(database, stub_bus, settings)

    d_large = dispatcher._compute_retry_delay(100)
    assert d_large.total_seconds() == 60.0


# ------------------------------------------------------------------
# Dispatcher start/stop lifecycle
# ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dispatcher_start_and_stop(database):
    stub_bus = _StubEventBus()
    dispatcher = OutboxDispatcher(database, stub_bus)

    await dispatcher.start()
    assert dispatcher._task is not None
    assert not dispatcher._task.done()

    await dispatcher.stop()
    assert dispatcher._task is None


@pytest.mark.asyncio
async def test_dispatcher_start_idempotent(database):
    stub_bus = _StubEventBus()
    dispatcher = OutboxDispatcher(database, stub_bus)

    await dispatcher.start()
    task1 = dispatcher._task
    await dispatcher.start()  # second start should be no-op
    assert dispatcher._task is task1

    await dispatcher.stop()


@pytest.mark.asyncio
async def test_dispatcher_stop_when_not_started(database):
    stub_bus = _StubEventBus()
    dispatcher = OutboxDispatcher(database, stub_bus)

    # Should not raise
    await dispatcher.stop()
