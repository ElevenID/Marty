"""Type definitions for gRPC services and protobuf messages."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    import grpc
    from sqlalchemy.ext.asyncio import AsyncSession

# Type variables for generic handlers
T = TypeVar("T")
HandlerResult = TypeVar("HandlerResult")


@runtime_checkable
class GrpcMessage(Protocol):
    """Protocol for protobuf message types."""

    def SerializeToString(self) -> bytes:
        """Serialize message to bytes."""
        ...

    def ParseFromString(self, data: bytes) -> None:
        """Parse message from bytes."""
        ...


@runtime_checkable
class GrpcServicerContext(Protocol):
    """Protocol for gRPC servicer context."""

    async def abort(self, code: grpc.StatusCode, details: str) -> None:  # type: ignore[name-defined]
        """Abort the RPC with given status code and details."""
        ...

    def set_code(self, code: grpc.StatusCode) -> None:  # type: ignore[name-defined]
        """Set the status code for the RPC."""
        ...

    def set_details(self, details: str) -> None:
        """Set the status details for the RPC."""
        ...


# Transaction handler type
TransactionHandler = Callable[[AsyncSession], HandlerResult]


@runtime_checkable
class DatabaseManager(Protocol):
    """Protocol for database manager."""

    async def run_within_transaction(self, handler: TransactionHandler[T]) -> T:
        """Run function within a database transaction."""
        ...


@runtime_checkable
class RuntimeConfig(Protocol):
    """Protocol for runtime configuration."""

    def get_service(self, name: str) -> dict[str, str]:
        """Get service configuration."""
        ...


@runtime_checkable
class ServiceDependencies(Protocol):
    """Protocol for service dependencies container."""

    @property
    def database(self) -> DatabaseManager:
        """Database manager instance."""
        ...

    @property
    def runtime_config(self) -> RuntimeConfig:
        """Runtime configuration instance."""
        ...

    @property
    def object_storage(self) -> Any:
        """Object storage client instance."""
        ...


# Specific protocol types for trust anchor service
@runtime_checkable
class TrustRequest(Protocol):
    """Protocol for trust verification request."""

    @property
    def entity(self) -> str:
        """Entity identifier to verify."""
        ...


@runtime_checkable
class TrustResponse(Protocol):
    """Protocol for trust verification response."""

    def __init__(self, is_trusted: bool) -> None:
        """Initialize trust response."""
        ...
