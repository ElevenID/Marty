"""
Standardized error handling system for Marty services.

Provides consistent error handling patterns, logging, monitoring, and recovery
mechanisms across all services in the Marty microservices architecture.
"""

from __future__ import annotations

import functools
import logging
import traceback
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import grpc


class ErrorSeverity(Enum):
    """Error severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    FATAL = "fatal"


class ErrorCategory(Enum):
    """Error categories for classification."""

    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    NETWORK = "network"
    DATABASE = "database"
    EXTERNAL_SERVICE = "external_service"
    CERTIFICATE = "certificate"
    CRYPTOGRAPHY = "cryptography"
    PROTOCOL = "protocol"
    CONFIGURATION = "configuration"
    RESOURCE = "resource"
    BUSINESS_LOGIC = "business_logic"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class RecoveryAction(Enum):
    """Possible recovery actions."""

    RETRY = "retry"
    FALLBACK = "fallback"
    CIRCUIT_BREAK = "circuit_break"
    ESCALATE = "escalate"
    IGNORE = "ignore"
    FAIL_FAST = "fail_fast"


@dataclass
class ErrorContext:
    """Context information for error handling."""

    error_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    service_name: str = ""
    operation_name: str = ""
    user_id: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    additional_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorDetails:
    """Detailed error information."""

    exception_type: str
    message: str
    severity: ErrorSeverity
    category: ErrorCategory
    context: ErrorContext
    traceback_info: str | None = None
    cause_chain: list[str] = field(default_factory=list)
    recovery_actions: list[RecoveryAction] = field(default_factory=list)
    is_retryable: bool = False
    is_user_error: bool = False
    sensitive_data: bool = False


class MartyException(Exception):
    """Base exception class for Marty services."""

    def __init__(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        context: ErrorContext | None = None,
        cause: Exception | None = None,
        is_retryable: bool = False,
        is_user_error: bool = False,
        recovery_actions: list[RecoveryAction] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.severity = severity
        self.category = category
        self.context = context or ErrorContext()
        self.cause = cause
        self.is_retryable = is_retryable
        self.is_user_error = is_user_error
        self.recovery_actions = recovery_actions or []


# Specific exception types
class ValidationError(MartyException):
    """Validation-related errors."""

    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.WARNING,
            category=ErrorCategory.VALIDATION,
            is_user_error=True,
            **kwargs,
        )


class AuthenticationError(MartyException):
    """Authentication-related errors."""

    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.AUTHENTICATION,
            recovery_actions=[RecoveryAction.FAIL_FAST],
            **kwargs,
        )


class AuthorizationError(MartyException):
    """Authorization-related errors."""

    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.AUTHORIZATION,
            recovery_actions=[RecoveryAction.FAIL_FAST],
            **kwargs,
        )


class NetworkError(MartyException):
    """Network-related errors."""

    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.NETWORK,
            is_retryable=True,
            recovery_actions=[RecoveryAction.RETRY, RecoveryAction.CIRCUIT_BREAK],
            **kwargs,
        )


class ExternalServiceError(MartyException):
    """External service-related errors."""

    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.EXTERNAL_SERVICE,
            is_retryable=True,
            recovery_actions=[RecoveryAction.RETRY, RecoveryAction.FALLBACK],
            **kwargs,
        )


class CertificateError(MartyException):
    """Certificate-related errors."""

    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.CRITICAL,
            category=ErrorCategory.CERTIFICATE,
            recovery_actions=[RecoveryAction.ESCALATE],
            **kwargs,
        )


class CryptographyError(MartyException):
    """Cryptography-related errors."""

    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.CRITICAL,
            category=ErrorCategory.CRYPTOGRAPHY,
            recovery_actions=[RecoveryAction.ESCALATE],
            **kwargs,
        )


class ConfigurationError(MartyException):
    """Configuration-related errors."""

    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.FATAL,
            category=ErrorCategory.CONFIGURATION,
            recovery_actions=[RecoveryAction.FAIL_FAST],
            **kwargs,
        )


class ResourceError(MartyException):
    """Resource-related errors (memory, disk, etc.)."""

    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(
            message,
            severity=ErrorSeverity.CRITICAL,
            category=ErrorCategory.RESOURCE,
            recovery_actions=[RecoveryAction.CIRCUIT_BREAK, RecoveryAction.ESCALATE],
            **kwargs,
        )


class ErrorHandler:
    """Standardized error handler for Marty services."""

    def __init__(
        self,
        service_name: str,
        logger: logging.Logger | None = None,
        error_callbacks: list[Callable[[ErrorDetails], None]] | None = None,
    ) -> None:
        self.service_name = service_name
        self.logger = logger or logging.getLogger(f"marty.{service_name}")
        self.error_callbacks = error_callbacks or []

        # Error statistics
        self.error_counts: dict[str, int] = {}
        self.last_errors: dict[str, datetime] = {}

    def handle_error(
        self,
        exception: Exception,
        context: ErrorContext | None = None,
        suppress_logging: bool = False,
    ) -> ErrorDetails:
        """Handle an exception and return error details."""

        # Create or update context
        if context is None:
            context = ErrorContext()
        context.service_name = self.service_name

        # Determine error details
        if isinstance(exception, MartyException):
            error_details = self._handle_marty_exception(exception, context)
        else:
            error_details = self._handle_generic_exception(exception, context)

        # Update statistics
        self._update_error_statistics(error_details)

        # Log the error
        if not suppress_logging:
            self._log_error(error_details)

        # Notify callbacks
        for callback in self.error_callbacks:
            try:
                callback(error_details)
            except Exception:
                self.logger.exception("Error callback failed")

        return error_details

    def _handle_marty_exception(
        self, exception: MartyException, context: ErrorContext
    ) -> ErrorDetails:
        """Handle a Marty-specific exception."""

        # Build cause chain
        cause_chain = []
        current_cause = exception.cause
        while current_cause:
            cause_chain.append(f"{type(current_cause).__name__}: {current_cause!s}")
            if hasattr(current_cause, "__cause__"):
                current_cause = current_cause.__cause__
            else:
                break

        return ErrorDetails(
            exception_type=type(exception).__name__,
            message=exception.message,
            severity=exception.severity,
            category=exception.category,
            context=context,
            traceback_info=self._get_traceback(),
            cause_chain=cause_chain,
            recovery_actions=exception.recovery_actions,
            is_retryable=exception.is_retryable,
            is_user_error=exception.is_user_error,
        )

    def _handle_generic_exception(
        self, exception: Exception, context: ErrorContext
    ) -> ErrorDetails:
        """Handle a generic Python exception."""

        # Classify the exception
        category, severity, is_retryable = self._classify_exception(exception)

        return ErrorDetails(
            exception_type=type(exception).__name__,
            message=str(exception),
            severity=severity,
            category=category,
            context=context,
            traceback_info=self._get_traceback(),
            is_retryable=is_retryable,
            recovery_actions=self._suggest_recovery_actions(category, severity),
        )

    def _classify_exception(
        self, exception: Exception
    ) -> tuple[ErrorCategory, ErrorSeverity, bool]:
        """Classify a generic exception."""

        exception_type = type(exception).__name__.lower()
        exception_message = str(exception).lower()

        # Network-related errors
        if any(
            keyword in exception_type for keyword in ["connection", "network", "timeout", "socket"]
        ):
            return ErrorCategory.NETWORK, ErrorSeverity.ERROR, True

        # Validation errors
        if any(keyword in exception_type for keyword in ["value", "type", "attribute", "key"]):
            return ErrorCategory.VALIDATION, ErrorSeverity.WARNING, False

        # Certificate/crypto errors
        if any(keyword in exception_message for keyword in ["certificate", "crypto", "ssl", "tls"]):
            return ErrorCategory.CERTIFICATE, ErrorSeverity.CRITICAL, False

        # Database errors
        if any(keyword in exception_type for keyword in ["database", "sql", "connection"]):
            return ErrorCategory.DATABASE, ErrorSeverity.ERROR, True

        # Permission errors
        if "permission" in exception_type or "access" in exception_type:
            return ErrorCategory.AUTHORIZATION, ErrorSeverity.ERROR, False

        # Resource errors
        if any(keyword in exception_type for keyword in ["memory", "resource", "limit"]):
            return ErrorCategory.RESOURCE, ErrorSeverity.CRITICAL, False

        # Default classification
        return ErrorCategory.UNKNOWN, ErrorSeverity.ERROR, False

    def _suggest_recovery_actions(
        self, category: ErrorCategory, severity: ErrorSeverity
    ) -> list[RecoveryAction]:
        """Suggest recovery actions based on error category and severity."""

        if severity == ErrorSeverity.FATAL:
            return [RecoveryAction.FAIL_FAST]

        if category == ErrorCategory.NETWORK:
            return [RecoveryAction.RETRY, RecoveryAction.CIRCUIT_BREAK]
        if category == ErrorCategory.EXTERNAL_SERVICE:
            return [RecoveryAction.RETRY, RecoveryAction.FALLBACK]
        if category == ErrorCategory.VALIDATION or category in [
            ErrorCategory.AUTHENTICATION,
            ErrorCategory.AUTHORIZATION,
        ]:
            return [RecoveryAction.FAIL_FAST]
        if category in [ErrorCategory.CERTIFICATE, ErrorCategory.CRYPTOGRAPHY]:
            return [RecoveryAction.ESCALATE]
        if category == ErrorCategory.RESOURCE:
            return [RecoveryAction.CIRCUIT_BREAK, RecoveryAction.ESCALATE]
        return [RecoveryAction.RETRY]

    def _get_traceback(self) -> str:
        """Get current traceback information."""
        return traceback.format_exc()

    def _update_error_statistics(self, error_details: ErrorDetails) -> None:
        """Update error statistics."""
        error_key = f"{error_details.category.value}:{error_details.exception_type}"

        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
        self.last_errors[error_key] = error_details.context.timestamp

    def _log_error(self, error_details: ErrorDetails) -> None:
        """Log error details with appropriate level."""

        log_message = self._format_log_message(error_details)

        if error_details.severity == ErrorSeverity.DEBUG:
            self.logger.debug(log_message)
        elif error_details.severity == ErrorSeverity.INFO:
            self.logger.info(log_message)
        elif error_details.severity == ErrorSeverity.WARNING:
            self.logger.warning(log_message)
        elif error_details.severity == ErrorSeverity.ERROR:
            self.logger.error(log_message)
        elif error_details.severity == ErrorSeverity.CRITICAL:
            self.logger.critical(log_message)
        elif error_details.severity == ErrorSeverity.FATAL:
            self.logger.critical(f"FATAL ERROR: {log_message}")

    def _format_log_message(self, error_details: ErrorDetails) -> str:
        """Format error message for logging."""

        context = error_details.context
        message_parts = [
            f"[{error_details.error_id[:8]}]",
            f"{error_details.exception_type}: {error_details.message}",
            f"Category: {error_details.category.value}",
        ]

        if context.operation_name:
            message_parts.append(f"Operation: {context.operation_name}")

        if context.user_id and not error_details.sensitive_data:
            message_parts.append(f"User: {context.user_id}")

        if context.request_id:
            message_parts.append(f"Request: {context.request_id}")

        if error_details.is_retryable:
            message_parts.append("(Retryable)")

        if error_details.recovery_actions:
            actions = ", ".join([action.value for action in error_details.recovery_actions])
            message_parts.append(f"Recovery: [{actions}]")

        return " | ".join(message_parts)


class GrpcErrorHandler(ErrorHandler):
    """Specialized error handler for gRPC services."""

    def handle_grpc_error(
        self,
        exception: Exception,
        context: grpc.ServicerContext,
        operation_name: str = "",
        user_id: str | None = None,
    ) -> None:
        """Handle error in gRPC context."""

        # Create error context
        error_context = ErrorContext(
            operation_name=operation_name,
            user_id=user_id,
            request_id=self._get_grpc_request_id(context),
            additional_context=self._get_grpc_metadata(context),
        )

        # Handle the error
        error_details = self.handle_error(exception, error_context)

        # Set gRPC context
        self._set_grpc_context(context, error_details)

    def _get_grpc_request_id(self, context: grpc.ServicerContext) -> str | None:
        """Extract request ID from gRPC metadata."""
        try:
            metadata = dict(context.invocation_metadata())
            return metadata.get("request-id") or metadata.get("x-request-id")
        except:
            return None

    def _get_grpc_metadata(self, context: grpc.ServicerContext) -> dict[str, str]:
        """Extract relevant metadata from gRPC context."""
        try:
            return dict(context.invocation_metadata())
        except:
            return {}

    def _set_grpc_context(self, context: grpc.ServicerContext, error_details: ErrorDetails) -> None:
        """Set appropriate gRPC error context."""

        # Map Marty error categories to gRPC status codes
        status_code_map = {
            ErrorCategory.VALIDATION: grpc.StatusCode.INVALID_ARGUMENT,
            ErrorCategory.AUTHENTICATION: grpc.StatusCode.UNAUTHENTICATED,
            ErrorCategory.AUTHORIZATION: grpc.StatusCode.PERMISSION_DENIED,
            ErrorCategory.NETWORK: grpc.StatusCode.UNAVAILABLE,
            ErrorCategory.EXTERNAL_SERVICE: grpc.StatusCode.UNAVAILABLE,
            ErrorCategory.CERTIFICATE: grpc.StatusCode.INTERNAL,
            ErrorCategory.CRYPTOGRAPHY: grpc.StatusCode.INTERNAL,
            ErrorCategory.CONFIGURATION: grpc.StatusCode.FAILED_PRECONDITION,
            ErrorCategory.RESOURCE: grpc.StatusCode.RESOURCE_EXHAUSTED,
            ErrorCategory.BUSINESS_LOGIC: grpc.StatusCode.FAILED_PRECONDITION,
            ErrorCategory.UNKNOWN: grpc.StatusCode.INTERNAL,
        }

        status_code = status_code_map.get(error_details.category, grpc.StatusCode.INTERNAL)

        # Create user-friendly error message
        if error_details.is_user_error:
            details = error_details.message
        else:
            details = f"Internal error occurred. Error ID: {error_details.context.error_id[:8]}"

        context.set_code(status_code)
        context.set_details(details)

        # Add error ID as trailing metadata
        context.set_trailing_metadata(
            [
                ("error-id", error_details.context.error_id),
                ("error-category", error_details.category.value),
            ]
        )


# Decorator for error handling
def handle_errors(
    handler: ErrorHandler | None = None,
    operation_name: str = "",
    suppress_logging: bool = False,
    reraise: bool = True,
):
    """Decorator for standardized error handling."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Use provided handler or create a default one
                error_handler = handler or ErrorHandler("unknown")

                # Create context
                context = ErrorContext(operation_name=operation_name or func.__name__)

                # Handle the error
                error_details = error_handler.handle_error(e, context, suppress_logging)

                if reraise:
                    raise
                return error_details

        return wrapper

    return decorator


@contextmanager
def error_context(
    handler: ErrorHandler,
    operation_name: str = "",
    user_id: str | None = None,
    additional_context: dict[str, Any] | None = None,
):
    """Context manager for error handling."""

    context = ErrorContext(
        operation_name=operation_name, user_id=user_id, additional_context=additional_context or {}
    )

    try:
        yield context
    except Exception as e:
        handler.handle_error(e, context)
        raise


def create_error_handler(service_name: str, logger: logging.Logger | None = None) -> ErrorHandler:
    """Create a standardized error handler for a service."""
    return ErrorHandler(service_name, logger)


def create_grpc_error_handler(
    service_name: str, logger: logging.Logger | None = None
) -> GrpcErrorHandler:
    """Create a gRPC-specific error handler for a service."""
    return GrpcErrorHandler(service_name, logger)


# Utility functions for common error patterns
def require_not_none(value: Any, message: str = "Value cannot be None") -> Any:
    """Require that a value is not None."""
    if value is None:
        raise ValidationError(message)
    return value


def require_not_empty(value: str, message: str = "Value cannot be empty") -> str:
    """Require that a string value is not empty."""
    if not value or not value.strip():
        raise ValidationError(message)
    return value


def require_valid_uuid(value: str, message: str = "Invalid UUID format") -> str:
    """Require that a string is a valid UUID."""
    try:
        uuid.UUID(value)
    except ValueError:
        raise ValidationError(message)
    else:
        return value


def safe_execute(
    func: Callable,
    handler: ErrorHandler,
    operation_name: str = "",
    default_return: Any = None,
    suppress_errors: bool = False,
) -> Any:
    """Safely execute a function with error handling."""

    try:
        return func()
    except Exception as e:
        context = ErrorContext(operation_name=operation_name)
        handler.handle_error(e, context, suppress_logging=suppress_errors)

        if suppress_errors:
            return default_return
        raise
