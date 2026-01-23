"""Protocol definitions for structural typing in Marty.

This module defines Protocol interfaces that enable structural subtyping
and provide clear contracts for key abstractions throughout the codebase.

Following PEP 544, these protocols define the expected interface without
requiring explicit inheritance, allowing for flexible implementation while
maintaining strong type safety.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from .infrastructure.models import (
        CertificateRecord,
        CredentialLedgerEntry,
        EventOutboxRecord,
        TrustEntity,
    )


@runtime_checkable
class RepositoryProtocol(Protocol):
    """Base protocol for all repository implementations."""

    _session: AsyncSession

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        ...


@runtime_checkable
class TrustEntityRepositoryProtocol(RepositoryProtocol, Protocol):
    """Protocol for trust entity repository operations."""

    async def get(self, entity_id: str) -> TrustEntity | None:
        """Retrieve a trust entity by ID."""
        ...

    async def upsert(
        self, entity_id: str, trusted: bool, attributes: dict[str, Any] | None = None
    ) -> TrustEntity:
        """Create or update a trust entity."""
        ...

    async def list_trusted(self) -> list[TrustEntity]:
        """List all trusted entities."""
        ...


@runtime_checkable
class CertificateRepositoryProtocol(RepositoryProtocol, Protocol):
    """Protocol for certificate repository operations."""

    async def upsert(
        self,
        cert_id: str,
        cert_type: str,
        pem: str,
        issuer: str | None = None,
        subject: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> CertificateRecord:
        """Create or update a certificate record."""
        ...

    async def get(self, cert_id: str) -> CertificateRecord | None:
        """Retrieve a certificate by ID."""
        ...

    async def list_all(self) -> list[CertificateRecord]:
        """List all certificates."""
        ...

    async def mark_revoked(self, cert_id: str, reason: str | None, revoked_at: datetime) -> None:
        """Mark a certificate as revoked."""
        ...

    async def list_by_type(self, cert_type: str) -> list[CertificateRecord]:
        """List certificates by type."""
        ...


@runtime_checkable
class CredentialLedgerRepositoryProtocol(RepositoryProtocol, Protocol):
    """Protocol for credential ledger repository operations."""

    async def upsert_entry(
        self,
        credential_id: str,
        credential_type: str,
        status: str,
        metadata: dict[str, Any] | None,
        topic: str,
        offset: int | None,
    ) -> CredentialLedgerEntry:
        """Create or update a credential ledger entry."""
        ...

    async def get_entry(self, credential_id: str) -> CredentialLedgerEntry | None:
        """Retrieve a credential ledger entry."""
        ...

    async def list_by_type(
        self, credential_type: str, limit: int = 100
    ) -> list[CredentialLedgerEntry]:
        """List entries by credential type."""
        ...


@runtime_checkable
class EventOutboxRepositoryProtocol(RepositoryProtocol, Protocol):
    """Protocol for event outbox repository operations."""

    async def enqueue(
        self,
        *,
        topic: str,
        payload: bytes,
        key: bytes | None = None,
        headers: dict[str, bytes] | None = None,
        available_at: datetime | None = None,
    ) -> EventOutboxRecord:
        """Enqueue an event for publishing."""
        ...

    async def claim_batch(self, limit: int) -> list[EventOutboxRecord]:
        """Claim a batch of events for processing."""
        ...

    async def mark_processed(self, record: EventOutboxRecord) -> None:
        """Mark an event as successfully processed."""
        ...

    async def mark_failed(
        self,
        record: EventOutboxRecord,
        error: str,
        retry_delay: datetime,
        max_attempts: int = 5,
    ) -> None:
        """Mark an event as failed with retry logic."""
        ...


@runtime_checkable
class DatabaseManagerProtocol(Protocol):
    """Protocol for database manager operations."""

    async def session(self) -> AsyncIterator[AsyncSession]:
        """Provide an async context manager for database sessions."""
        ...

    async def initialize(self) -> None:
        """Initialize the database connection pool."""
        ...

    async def close(self) -> None:
        """Close all database connections."""
        ...

    async def health_check(self) -> bool:
        """Check database connection health."""
        ...


@runtime_checkable
class EventBusProtocol(Protocol):
    """Protocol for event bus operations."""

    async def publish(
        self,
        topic: str,
        payload: bytes,
        key: bytes | None = None,
        headers: dict[str, bytes] | None = None,
    ) -> None:
        """Publish an event to the event bus."""
        ...

    async def stop(self) -> None:
        """Stop the event bus and clean up resources."""
        ...


@runtime_checkable
class ObjectStorageProtocol(Protocol):
    """Protocol for object storage operations."""

    async def put(
        self, bucket: str, key: str, data: bytes, metadata: dict[str, str] | None = None
    ) -> None:
        """Store an object in storage."""
        ...

    async def get(self, bucket: str, key: str) -> bytes:
        """Retrieve an object from storage."""
        ...

    async def delete(self, bucket: str, key: str) -> None:
        """Delete an object from storage."""
        ...

    async def list_keys(self, bucket: str, prefix: str = "") -> list[str]:
        """List object keys in a bucket."""
        ...

    async def exists(self, bucket: str, key: str) -> bool:
        """Check if an object exists."""
        ...


@runtime_checkable
class CertificateValidatorProtocol(Protocol):
    """Protocol for certificate validation operations."""

    async def validate(self, certificate: bytes, trust_anchors: Sequence[bytes]) -> dict[str, Any]:
        """Validate a certificate against trust anchors."""
        ...

    async def verify_chain(self, certificate: bytes, chain: Sequence[bytes]) -> dict[str, Any]:
        """Verify a certificate chain."""
        ...


@runtime_checkable
class SigningServiceProtocol(Protocol):
    """Protocol for signing service operations."""

    async def sign(self, data: bytes, key_id: str, algorithm: str | None = None) -> bytes:
        """Sign data with the specified key."""
        ...

    async def verify(
        self,
        data: bytes,
        signature: bytes,
        public_key: bytes,
        algorithm: str | None = None,
    ) -> bool:
        """Verify a signature."""
        ...


@runtime_checkable
class GrpcServiceProtocol(Protocol):
    """Protocol for gRPC service implementations."""

    async def serve(self, host: str, port: int, *, tls_enabled: bool = False) -> None:
        """Start serving the gRPC service."""
        ...

    async def stop(self, grace_period: float = 5.0) -> None:
        """Stop the gRPC service gracefully."""
        ...


@runtime_checkable
class ConfigurationProtocol(Protocol):
    """Protocol for configuration management."""

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        ...

    def get_int(self, key: str, default: int = 0) -> int:
        """Get an integer configuration value."""
        ...

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get a boolean configuration value."""
        ...

    def get_str(self, key: str, default: str = "") -> str:
        """Get a string configuration value."""
        ...


@runtime_checkable
class LoggerProtocol(Protocol):
    """Protocol for structured logging."""

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log a debug message."""
        ...

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log an info message."""
        ...

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log a warning message."""
        ...

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log an error message."""
        ...

    def critical(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log a critical message."""
        ...

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log an exception with traceback."""
        ...


@runtime_checkable
class MetricsCollectorProtocol(Protocol):
    """Protocol for metrics collection."""

    def increment(self, metric: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
        """Increment a counter metric."""
        ...

    def gauge(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a gauge metric."""
        ...

    def histogram(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a histogram value."""
        ...

    def timing(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a timing metric."""
        ...
