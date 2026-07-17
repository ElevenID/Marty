"""
Database utilities to consolidate common patterns.

This module provides enhanced database patterns and utilities to reduce
code duplication in database operations across services.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import Select

from marty_common.errors import ErrorHandler, MartyDatabaseError
from marty_common.infrastructure.database import DatabaseManager

T = TypeVar("T")
ModelT = TypeVar("ModelT", bound=DeclarativeBase)

logger = logging.getLogger(__name__)


class DatabaseOperations:
    """
    Enhanced database operations with common patterns.

    Provides utilities for transaction management, error handling,
    and common query patterns to reduce code duplication.
    """

    def __init__(self, database: DatabaseManager) -> None:
        """Initialize database operations."""
        self.database = database

    @ErrorHandler.handle_common_exceptions(logger, reraise=True)
    async def execute_in_transaction(
        self,
        operation: Callable[[AsyncSession], Awaitable[T]],
        operation_name: str = "database_operation",
    ) -> T:
        """
        Execute operation within a transaction with error handling.

        Args:
            operation: Async function that takes a session and returns a result
            operation_name: Name for logging purposes

        Returns:
            Result from the operation

        Raises:
            MartyDatabaseError: If operation fails
        """
        try:
            return await self.database.run_within_transaction(operation)
        except Exception as e:
            error_msg = f"Failed to execute {operation_name}: {e}"
            logger.exception(error_msg)
            raise MartyDatabaseError(error_msg) from e

    @ErrorHandler.handle_common_exceptions(logger, reraise=True)
    async def execute_with_session(
        self,
        operation: Callable[[AsyncSession], Awaitable[T]],
        operation_name: str = "database_operation",
    ) -> T:
        """
        Execute operation with session scope (auto-commit).

        Args:
            operation: Async function that takes a session and returns a result
            operation_name: Name for logging purposes

        Returns:
            Result from the operation

        Raises:
            MartyDatabaseError: If operation fails
        """
        try:
            async with self.database.session_scope() as session:
                return await operation(session)
        except Exception as e:
            error_msg = f"Failed to execute {operation_name}: {e}"
            logger.exception(error_msg)
            raise MartyDatabaseError(error_msg) from e

    async def create_record(
        self, model_class: type[ModelT], data: dict[str, Any], operation_name: str | None = None
    ) -> ModelT:
        """
        Create a new record in the database.

        Args:
            model_class: SQLAlchemy model class
            data: Data to create the record with
            operation_name: Optional operation name for logging

        Returns:
            Created model instance
        """
        operation_name = operation_name or f"create_{model_class.__name__}"

        async def handler(session: AsyncSession) -> ModelT:
            instance = model_class(**data)
            session.add(instance)
            await session.flush()
            await session.refresh(instance)
            return instance

        return await self.execute_in_transaction(handler, operation_name)

    async def update_record(
        self, instance: ModelT, updates: dict[str, Any], operation_name: str | None = None
    ) -> ModelT:
        """
        Update an existing record.

        Args:
            instance: Model instance to update
            updates: Dictionary of field updates
            operation_name: Optional operation name for logging

        Returns:
            Updated model instance
        """
        operation_name = operation_name or f"update_{type(instance).__name__}"

        async def handler(session: AsyncSession) -> ModelT:
            # Merge the instance into the session
            merged_instance = await session.merge(instance)

            # Apply updates
            for field, value in updates.items():
                setattr(merged_instance, field, value)

            await session.flush()
            await session.refresh(merged_instance)
            return merged_instance

        return await self.execute_in_transaction(handler, operation_name)

    async def delete_record(self, instance: ModelT, operation_name: str | None = None) -> None:
        """
        Delete a record from the database.

        Args:
            instance: Model instance to delete
            operation_name: Optional operation name for logging
        """
        operation_name = operation_name or f"delete_{type(instance).__name__}"

        async def handler(session: AsyncSession) -> None:
            merged_instance = await session.merge(instance)
            await session.delete(merged_instance)
            await session.flush()

        await self.execute_in_transaction(handler, operation_name)

    async def find_by_id(
        self, model_class: type[ModelT], record_id: Any, operation_name: str | None = None
    ) -> ModelT | None:
        """
        Find a record by its primary key.

        Args:
            model_class: SQLAlchemy model class
            record_id: Primary key value
            operation_name: Optional operation name for logging

        Returns:
            Model instance or None if not found
        """
        operation_name = operation_name or f"find_{model_class.__name__}_by_id"

        async def handler(session: AsyncSession) -> ModelT | None:
            return await session.get(model_class, record_id)

        return await self.execute_with_session(handler, operation_name)

    async def find_one(
        self, query: Select[tuple[ModelT]], operation_name: str | None = None
    ) -> ModelT | None:
        """
        Execute a query and return a single result.

        Args:
            query: SQLAlchemy select query
            operation_name: Optional operation name for logging

        Returns:
            Single model instance or None
        """
        operation_name = operation_name or "find_one"

        async def handler(session: AsyncSession) -> ModelT | None:
            result = await session.execute(query)
            return result.scalar_one_or_none()

        return await self.execute_with_session(handler, operation_name)

    async def find_many(
        self, query: Select[tuple[ModelT]], operation_name: str | None = None
    ) -> Sequence[ModelT]:
        """
        Execute a query and return multiple results.

        Args:
            query: SQLAlchemy select query
            operation_name: Optional operation name for logging

        Returns:
            Sequence of model instances
        """
        operation_name = operation_name or "find_many"

        async def handler(session: AsyncSession) -> Sequence[ModelT]:
            result = await session.execute(query)
            return result.scalars().all()

        return await self.execute_with_session(handler, operation_name)

    async def count_records(
        self, query: Select[tuple[int]], operation_name: str | None = None
    ) -> int:
        """
        Count records matching a query.

        Args:
            query: SQLAlchemy count query
            operation_name: Optional operation name for logging

        Returns:
            Count of matching records
        """
        operation_name = operation_name or "count_records"

        async def handler(session: AsyncSession) -> int:
            result = await session.execute(query)
            return result.scalar_one()

        return await self.execute_with_session(handler, operation_name)


class RepositoryBase:
    """
    Base repository class with common database operations.

    Provides standardized patterns for data access operations
    to reduce repository code duplication.
    """

    def __init__(self, db_ops: DatabaseOperations) -> None:
        """Initialize repository with database operations."""
        self.db_ops = db_ops

    async def create(self, model_class: type[ModelT], data: dict[str, Any]) -> ModelT:
        """Create a new record."""
        return await self.db_ops.create_record(model_class, data)

    async def update(self, instance: ModelT, updates: dict[str, Any]) -> ModelT:
        """Update an existing record."""
        return await self.db_ops.update_record(instance, updates)

    async def delete(self, instance: ModelT) -> None:
        """Delete a record."""
        await self.db_ops.delete_record(instance)

    async def find_by_id(self, model_class: type[ModelT], record_id: Any) -> ModelT | None:
        """Find record by ID."""
        return await self.db_ops.find_by_id(model_class, record_id)


class TransactionManager:
    """
    Transaction manager for complex multi-step operations.

    Provides utilities for managing transactions across multiple
    database operations with rollback support.
    """

    def __init__(self, database: DatabaseManager) -> None:
        """Initialize transaction manager."""
        self.database = database

    @asynccontextmanager
    async def transaction(self, operation_name: str = "transaction"):
        """
        Context manager for explicit transaction control.

        Args:
            operation_name: Name for logging purposes

        Yields:
            AsyncSession for database operations
        """
        try:
            async with self.database.session_scope() as session:
                logger.debug("Starting transaction: %s", operation_name)
                yield session
                logger.debug("Committing transaction: %s", operation_name)
        except Exception as e:
            logger.error("Rolling back transaction %s: %s", operation_name, e)
            raise MartyDatabaseError(f"Transaction {operation_name} failed: {e}") from e

    async def execute_batch(
        self,
        operations: list[Callable[[AsyncSession], Awaitable[Any]]],
        operation_name: str = "batch_operation",
    ) -> list[Any]:
        """
        Execute multiple operations in a single transaction.

        Args:
            operations: List of async functions that take a session
            operation_name: Name for logging purposes

        Returns:
            List of results from each operation
        """
        async with self.transaction(operation_name) as session:
            results = []
            for i, operation in enumerate(operations):
                try:
                    result = await operation(session)
                    results.append(result)
                except Exception as e:
                    error_msg = f"Batch operation {i} failed in {operation_name}: {e}"
                    logger.exception(error_msg)
                    raise MartyDatabaseError(error_msg) from e
            return results


# Convenience decorators
def with_database_error_handling(operation_name: str | None = None):
    """
    Decorator to add database error handling to methods.

    Args:
        operation_name: Optional operation name for logging
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            op_name = operation_name or f"{func.__name__}"
            try:
                return await func(*args, **kwargs)
            except MartyDatabaseError:
                # Re-raise database errors as-is
                raise
            except Exception as e:
                error_msg = f"Database operation {op_name} failed: {e}"
                logger.exception(error_msg)
                raise MartyDatabaseError(error_msg) from e

        return wrapper

    return decorator


# Factory functions
def create_database_operations(database: DatabaseManager) -> DatabaseOperations:
    """Create DatabaseOperations instance."""
    return DatabaseOperations(database)


def create_transaction_manager(database: DatabaseManager) -> TransactionManager:
    """Create TransactionManager instance."""
    return TransactionManager(database)


def create_repository(repository_class: type[T], database: DatabaseManager) -> T:
    """
    Create repository instance with database operations.

    Args:
        repository_class: Repository class to instantiate
        database: Database manager instance

    Returns:
        Repository instance
    """
    db_ops = create_database_operations(database)
    return repository_class(db_ops)


def create_service_database_tables(service_name: str, base_metadata: Any, engine: Any) -> None:
    """
    Standard database table creation for services.

    This consolidates the duplicate database setup pattern used across
    multiple services, reducing code duplication from ~6 lines to 1 line.

    Args:
        service_name: Name of the service for logging
        base_metadata: SQLAlchemy Base.metadata object
        engine: SQLAlchemy engine instance

    Example:
        from marty_common.database.utilities import create_service_database_tables
        from marty_plugin.shared.database import Base, engine

        create_service_database_tables("my-service", Base.metadata, engine)
    """
    from marty_common.logging_config import get_logger

    logger = get_logger(f"{service_name}.database")
    logger.info(f"Creating database tables for {service_name}...")

    try:
        base_metadata.create_all(bind=engine)
        logger.info("Database tables created successfully.")
    except Exception as e:
        logger.exception(f"Failed to create database tables for {service_name}")
        raise
