"""Shared async database helpers for Marty services."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base


@dataclass(slots=True)
class DatabaseConfig:
    """Runtime configuration for the shared database connection."""

    url: str
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DatabaseConfig:
        if "url" in raw:
            url = raw["url"]
        else:
            host = raw.get("host", "localhost")
            port = raw.get("port", 5432)
            name = raw.get("name", "marty")
            user = raw.get("user", "marty")
            password = raw.get("password", "marty")
            url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"
        return cls(
            url=url,
            echo=bool(raw.get("echo", False)),
            pool_size=int(raw.get("pool_size", 10)),
            max_overflow=int(raw.get("max_overflow", 20)),
            pool_timeout=int(raw.get("pool_timeout", 30)),
        )


T = TypeVar("T")


class DatabaseManager:
    """Factory for async SQLAlchemy sessions with lifecycle hooks."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def create_engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = create_async_engine(
                self._config.url,
                echo=self._config.echo,
                pool_size=self._config.pool_size,
                max_overflow=self._config.max_overflow,
                pool_timeout=self._config.pool_timeout,
                future=True,
            )
        return self._engine

    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            engine = self.create_engine()
            self._session_factory = async_sessionmaker(
                engine,
                expire_on_commit=False,
                autoflush=False,
            )
        return self._session_factory

    async def create_all(self) -> None:
        engine = self.create_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()

    @asynccontextmanager
    async def session_scope(self) -> AsyncIterator[AsyncSession]:
        session = self.session_factory()()
        try:
            yield session
            await session.commit()
        except Exception:  # pylint: disable=broad-except
            await session.rollback()
            raise
        finally:
            await session.close()

    async def run_within_transaction(self, handler: Callable[[AsyncSession], Awaitable[T]]) -> T:
        async with self.session_scope() as session:
            return await handler(session)
