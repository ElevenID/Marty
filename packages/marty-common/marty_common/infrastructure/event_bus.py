"""Kafka-backed event bus abstraction."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from aiokafka import AIOKafkaProducer


@dataclass(slots=True)
class EventBusConfig:
    brokers: list[str]
    client_id: str = "marty"
    topic_prefix: str = ""
    security_protocol: str = "PLAINTEXT"
    ssl_cafile: str | None = None
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None
    enabled: bool = True
    consumer_group: str | None = None
    auto_offset_reset: str = "earliest"

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> EventBusConfig:
        brokers = raw.get("brokers") or []
        if isinstance(brokers, str):
            brokers = [broker.strip() for broker in brokers.split(",") if broker.strip()]
        return cls(
            brokers=brokers,
            client_id=raw.get("client_id", "marty"),
            topic_prefix=raw.get("topic_prefix", ""),
            security_protocol=raw.get("security_protocol", "PLAINTEXT"),
            ssl_cafile=raw.get("ssl_cafile"),
            ssl_certfile=raw.get("ssl_certfile"),
            ssl_keyfile=raw.get("ssl_keyfile"),
            enabled=bool(raw.get("enabled", True)),
            consumer_group=raw.get("consumer_group"),
            auto_offset_reset=raw.get("auto_offset_reset", "earliest"),
        )


@dataclass(slots=True)
class EventBusMessage:
    topic: str
    payload: bytes
    headers: dict[str, bytes] | None = None
    key: bytes | None = None


class EventBusProvider:
    """Lazy Kafka producer wrapper that can be disabled per environment."""

    def __init__(self, config: EventBusConfig) -> None:
        self._config = config
        self._producer: AIOKafkaProducer | None = None
        self._lock = asyncio.Lock()

    async def _ensure_started(self) -> None:
        if not self._config.enabled:
            return
        async with self._lock:
            if self._producer is not None:
                return
            kwargs: dict[str, Any] = {
                "bootstrap_servers": self._config.brokers,
                "client_id": self._config.client_id,
                "security_protocol": self._config.security_protocol,
            }
            if self._config.security_protocol.upper() == "SSL":
                kwargs.update(
                    ssl_context=None,
                    ssl_cafile=self._config.ssl_cafile,
                    ssl_certfile=self._config.ssl_certfile,
                    ssl_keyfile=self._config.ssl_keyfile,
                )
            self._producer = AIOKafkaProducer(**kwargs)
            await self._producer.start()

    async def publish(self, message: EventBusMessage) -> None:
        if not self._config.enabled:
            return
        await self._ensure_started()
        assert self._producer is not None  # for mypy/static hints
        topic = (
            f"{self._config.topic_prefix}{message.topic}"
            if self._config.topic_prefix
            else message.topic
        )
        headers = None
        if message.headers:
            headers = [(key, value) for key, value in message.headers.items()]
        await self._producer.send_and_wait(
            topic,
            message.payload,
            headers=headers,
            key=message.key,
        )

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
