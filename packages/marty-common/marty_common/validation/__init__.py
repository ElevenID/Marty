"""Runtime validation helpers for Marty gRPC services."""

from .grpc import RequestValidationError, validate_request

__all__ = [
    "RequestValidationError",
    "validate_request",
]
