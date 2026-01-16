"""
Database Management for Digital Identity Module

Provides async database session management, table creation, and lifecycle hooks.
Follows the existing Marty pattern from common/infrastructure/database.py.
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(slots=True)
class DigitalIdentityDatabaseConfig:
    """Configuration for Digital Identity database connection."""

    url: str
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DigitalIdentityDatabaseConfig:
        """Create config from dictionary (YAML config)."""
        if "url" in raw:
            url = raw["url"]
        else:
            # Build URL from components
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
    
    @classmethod
    def from_env(cls, prefix: str = "DIGITAL_IDENTITY_DB") -> DigitalIdentityDatabaseConfig:
        """Create config from environment variables."""
        import os
        
        url = os.environ.get(
            f"{prefix}_URL",
            os.environ.get("DATABASE_URL", "postgresql+asyncpg://marty:marty@localhost:5432/marty")
        )
        
        return cls(
            url=url,
            echo=os.environ.get(f"{prefix}_ECHO", "false").lower() == "true",
            pool_size=int(os.environ.get(f"{prefix}_POOL_SIZE", "10")),
            max_overflow=int(os.environ.get(f"{prefix}_MAX_OVERFLOW", "20")),
            pool_timeout=int(os.environ.get(f"{prefix}_POOL_TIMEOUT", "30")),
        )


class DigitalIdentityDatabaseManager:
    """
    Async database manager for Digital Identity module.
    
    Provides:
    - Connection pooling with configurable parameters
    - Session factory for repository injection
    - Table creation/migration support
    - Transaction management via session_scope
    """

    def __init__(self, config: DigitalIdentityDatabaseConfig | None = None) -> None:
        """
        Initialize database manager.
        
        Args:
            config: Database configuration. If None, loads from environment.
        """
        self._config = config or DigitalIdentityDatabaseConfig.from_env()
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def create_engine(self) -> AsyncEngine:
        """Create or return cached async engine."""
        if self._engine is None:
            # Determine engine options based on driver
            engine_kwargs: dict[str, Any] = {
                "echo": self._config.echo,
                "future": True,
            }
            
            # SQLite-specific settings (for testing)
            if "sqlite" in self._config.url:
                # SQLite doesn't support pool options
                pass
            else:
                # PostgreSQL pool settings
                engine_kwargs.update({
                    "pool_size": self._config.pool_size,
                    "max_overflow": self._config.max_overflow,
                    "pool_timeout": self._config.pool_timeout,
                })
            
            self._engine = create_async_engine(
                self._config.url,
                **engine_kwargs,
            )
            logger.debug(f"Created database engine: {self._config.url.split('@')[-1]}")
        
        return self._engine

    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Create or return cached session factory."""
        if self._session_factory is None:
            engine = self.create_engine()
            self._session_factory = async_sessionmaker(
                engine,
                expire_on_commit=False,
                autoflush=False,
            )
        return self._session_factory

    async def create_all(self) -> None:
        """
        Create all Digital Identity database tables.
        
        Tables created:
        - trust_profiles
        - credential_templates
        - presentation_policies
        - deployment_profiles
        - flows
        - flow_executions
        """
        engine = self.create_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Digital Identity database tables created")

    async def drop_all(self) -> None:
        """
        Drop all Digital Identity database tables.
        
        WARNING: Use with caution! This will delete all data.
        """
        engine = self.create_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.warning("Digital Identity database tables dropped")

    async def dispose(self) -> None:
        """Dispose of engine and close all connections."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Digital Identity database connections closed")

    @asynccontextmanager
    async def session_scope(self) -> AsyncIterator[AsyncSession]:
        """
        Context manager for database sessions.
        
        Provides automatic commit/rollback and session cleanup.
        
        Usage:
            async with db_manager.session_scope() as session:
                result = await session.execute(select(TrustProfileModel))
        """
        factory = self.session_factory()
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def run_within_transaction(
        self, handler: Callable[[AsyncSession], Awaitable[T]]
    ) -> T:
        """
        Run a handler within a transaction.
        
        Args:
            handler: Async function that receives a session
            
        Returns:
            Result of the handler
        """
        async with self.session_scope() as session:
            return await handler(session)


# Global manager instance (can be overridden)
_db_manager: DigitalIdentityDatabaseManager | None = None


def get_database_manager(
    config: DigitalIdentityDatabaseConfig | None = None
) -> DigitalIdentityDatabaseManager:
    """
    Get or create the global database manager.
    
    Args:
        config: Optional configuration to use
        
    Returns:
        Database manager instance
    """
    global _db_manager
    
    if _db_manager is None:
        _db_manager = DigitalIdentityDatabaseManager(config)
    
    return _db_manager


def set_database_manager(manager: DigitalIdentityDatabaseManager) -> None:
    """
    Set a custom database manager.
    
    Useful for testing or when using a shared database manager.
    
    Args:
        manager: Database manager instance to use
    """
    global _db_manager
    _db_manager = manager


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """
    FastAPI dependency for database sessions.
    
    Usage:
        @app.get("/trust-profiles")
        async def list_profiles(db: AsyncSession = Depends(get_db_session)):
            result = await db.execute(select(TrustProfileModel))
            ...
    """
    manager = get_database_manager()
    factory = manager.session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_database(config: DigitalIdentityDatabaseConfig | None = None) -> None:
    """
    Initialize database tables.
    
    Call during application startup.
    
    Args:
        config: Optional database configuration
    """
    manager = get_database_manager(config)
    await manager.create_all()


async def close_database() -> None:
    """
    Close database connections.
    
    Call during application shutdown.
    """
    global _db_manager
    
    if _db_manager is not None:
        await _db_manager.dispose()
        _db_manager = None
