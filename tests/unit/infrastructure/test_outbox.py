import pytest
import pytest_asyncio

from marty_common.infrastructure import (
    DatabaseConfig,
    DatabaseManager,
    OutboxDispatcher,
    OutboxRepository,
)


@pytest_asyncio.fixture
async def database():
    database = DatabaseManager(DatabaseConfig(url="sqlite+aiosqlite:///:memory:"))
    try:
        await database.create_all()
        yield database
    finally:
        await database.dispose()


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

    async def publish(self, message):  # pragma: no cover - interface stub
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
