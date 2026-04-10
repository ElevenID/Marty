"""Transactional outbox repository and dispatcher helpers."""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from .event_bus import EventBusMessage, EventBusProvider
from .models import EventDeadLetterRecord, EventOutboxRecord

if TYPE_CHECKING:  # pragma: no cover - imported for type checking only
    from .database import DatabaseManager

logger = logging.getLogger(__name__)


def _encode_headers(headers: dict[str, bytes] | None) -> dict[str, str] | None:
    if not headers:
        return None
    return {key: base64.b64encode(value).decode("ascii") for key, value in headers.items()}


def _decode_headers(headers: dict[str, str] | None) -> dict[str, bytes] | None:
    if not headers:
        return None
    return {key: base64.b64decode(value.encode("ascii")) for key, value in headers.items()}


class OutboxRepository:
    """Repository exposing minimal helpers for the event outbox."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self,
        *,
        topic: str,
        payload: bytes,
        key: bytes | None = None,
        headers: dict[str, bytes] | None = None,
        available_at: datetime | None = None,
    ) -> EventOutboxRecord:
        record = EventOutboxRecord(
            topic=topic,
            key=key,
            payload=payload,
            headers=_encode_headers(headers),
            available_at=available_at or datetime.now(timezone.utc),
        )
        self._session.add(record)
        return record

    async def claim_batch(self, limit: int) -> list[EventOutboxRecord]:
        now = datetime.now(timezone.utc)
        stmt: Select[tuple[EventOutboxRecord]] = (
            select(EventOutboxRecord)
            .where(
                EventOutboxRecord.processed_at.is_(None),
                EventOutboxRecord.available_at <= now,
            )
            .order_by(EventOutboxRecord.id)
            .limit(limit)
        )
        bind = self._session.get_bind()
        if bind is not None and bind.dialect.name in {"postgresql", "mysql", "mariadb"}:
            stmt = stmt.with_for_update(skip_locked=True)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_processed(self, record: EventOutboxRecord) -> None:
        record.processed_at = datetime.now(timezone.utc)
        record.last_error = None

    async def mark_failed(
        self,
        record: EventOutboxRecord,
        error: str,
        retry_delay: timedelta,
        max_attempts: int = 5,
    ) -> None:
        record.attempts += 1
        record.last_error = error[:1024]

        if record.attempts >= max_attempts:
            # Move to dead-letter queue
            await self._move_to_dead_letter_queue(record, error)
        else:
            # Requeue for retry
            record.available_at = datetime.now(timezone.utc) + retry_delay

    async def _move_to_dead_letter_queue(self, record: EventOutboxRecord, error: str) -> None:
        """Move a failed event to the dead-letter queue."""
        dlq_record = EventDeadLetterRecord(
            original_topic=record.topic,
            key=record.key,
            payload=record.payload,
            headers=record.headers,
            attempts=record.attempts,
            last_error=error[:1024],
            original_created_at=record.created_at,
        )
        self._session.add(dlq_record)
        # Remove from outbox
        await self._session.delete(record)

    async def requeue(self, records: Iterable[EventOutboxRecord], delay: timedelta) -> None:
        for record in records:
            record.available_at = datetime.now(timezone.utc) + delay


@dataclass(slots=True)
class OutboxDispatcherSettings:
    """Behavior tuning knobs for the outbox dispatcher."""

    poll_interval: float = 2.0
    batch_size: int = 50
    initial_retry_delay: float = 5.0
    max_retry_delay: float = 300.0
    max_attempts: int = 5


class OutboxDispatcher:
    """Background worker that drains the transactional outbox."""

    def __init__(
        self,
        database: DatabaseManager,
        event_bus: EventBusProvider,
        settings: OutboxDispatcherSettings | None = None,
    ) -> None:
        self._database = database
        self._event_bus = event_bus
        self._settings = settings or OutboxDispatcherSettings()
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._lock:
            if self._task is not None and not self._task.done():
                return
            self._stopping.clear()
            self._task = asyncio.create_task(self._run(), name="event-outbox-dispatcher")

    async def stop(self) -> None:
        async with self._lock:
            if self._task is None:
                return
            self._stopping.set()
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            finally:
                self._task = None
                self._stopping.clear()

    async def flush_once(self) -> int:
        async with self._database.session_scope() as session:
            repo = OutboxRepository(session)
            records = await repo.claim_batch(self._settings.batch_size)
            processed = 0
            for record in records:
                message = EventBusMessage(
                    topic=record.topic,
                    payload=bytes(record.payload),
                    headers=_decode_headers(record.headers),
                    key=bytes(record.key) if record.key is not None else None,
                )
                try:
                    await self._event_bus.publish(message)
                except Exception as exc:  # pragma: no cover - defensive logging path
                    retry_delay = self._compute_retry_delay(record.attempts + 1)
                    await repo.mark_failed(
                        record, str(exc), retry_delay, self._settings.max_attempts
                    )
                    logger.exception("Failed to publish outbox event %s", record.id)
                else:
                    await repo.mark_processed(record)
                    processed += 1
            return processed

    async def _run(self) -> None:
        try:
            while not self._stopping.is_set():
                try:
                    processed = await self.flush_once()
                except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
                    raise
                except Exception:  # pragma: no cover - defensive logging path
                    logger.exception("Outbox dispatcher flush failed")
                    processed = 0

                if processed == 0:
                    try:
                        await asyncio.wait_for(
                            self._stopping.wait(),
                            timeout=self._settings.poll_interval,
                        )
                    except asyncio.TimeoutError:
                        continue
        finally:
            self._stopping.clear()

    def _compute_retry_delay(self, attempt: int) -> timedelta:
        delay = self._settings.initial_retry_delay * (2 ** max(attempt - 1, 0))
        delay = min(delay, self._settings.max_retry_delay)
        return timedelta(seconds=delay)
