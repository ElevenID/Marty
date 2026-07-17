"""Standardized application error categories and mapping to gRPC status codes.

Existing codebase already uses MartyServiceException; we introduce a more granular
hierarchy that can wrap or co-exist with existing exceptions. The mapping layer
is additive and does not break existing ExceptionToStatusInterceptor behavior.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

import grpc


class ErrorCategory(str, Enum):
    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    UNAUTHORIZED = "unauthorized"
    TRANSIENT = "transient"
    INTERNAL = "internal"


@dataclass
class MartyError(Exception):
    """Base structured application error for resilience mapping."""

    message: str
    category: ErrorCategory = ErrorCategory.INTERNAL
    details: dict | None = None

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class ValidationError(MartyError):
    def __init__(self, message: str, details: dict | None = None) -> None:  # noqa: D401
        super().__init__(message, ErrorCategory.VALIDATION, details)


class NotFoundError(MartyError):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, ErrorCategory.NOT_FOUND, details)


class ConflictError(MartyError):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, ErrorCategory.CONFLICT, details)


class UnauthorizedError(MartyError):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, ErrorCategory.UNAUTHORIZED, details)


class TransientBackendError(MartyError):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, ErrorCategory.TRANSIENT, details)


CATEGORY_TO_STATUS: dict[ErrorCategory, grpc.StatusCode] = {
    ErrorCategory.VALIDATION: grpc.StatusCode.INVALID_ARGUMENT,
    ErrorCategory.NOT_FOUND: grpc.StatusCode.NOT_FOUND,
    ErrorCategory.CONFLICT: grpc.StatusCode.ALREADY_EXISTS,
    ErrorCategory.UNAUTHORIZED: grpc.StatusCode.PERMISSION_DENIED,
    ErrorCategory.TRANSIENT: grpc.StatusCode.UNAVAILABLE,
    ErrorCategory.INTERNAL: grpc.StatusCode.INTERNAL,
}


def map_exception_to_status(exc: Exception) -> tuple[grpc.StatusCode, str]:
    """Map known exception types to canonical gRPC status codes.

    Falls back to INTERNAL for unknown types.
    """
    if isinstance(exc, MartyError):
        return CATEGORY_TO_STATUS.get(exc.category, grpc.StatusCode.INTERNAL), exc.message
    # Allow integration with existing MartyServiceException without import cycle
    try:  # pragma: no cover - best effort mapping
        from marty_common.exceptions import MartyServiceException  # noqa: WPS433 (local import)

        if isinstance(exc, MartyServiceException):  # type: ignore[attr-defined]
            status = exc.status_code or grpc.StatusCode.INTERNAL  # type: ignore[attr-defined]
            return status, getattr(exc, "message", str(exc))
    except Exception as import_exc:  # noqa: BLE001
        logging.debug("Optional import failed for MartyServiceException: %s", import_exc)
    return grpc.StatusCode.INTERNAL, str(exc)


def exception_is_transient(exc: Exception) -> bool:
    return isinstance(exc, TransientBackendError) or (
        isinstance(exc, MartyError) and exc.category == ErrorCategory.TRANSIENT
    )


TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (TransientBackendError,)
