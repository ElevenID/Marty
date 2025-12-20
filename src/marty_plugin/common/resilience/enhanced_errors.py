"""Enhanced error codes with comprehensive structured error responses."""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import grpc

logger = logging.getLogger(__name__)


class ErrorSeverity(str, Enum):
    """Error severity levels for better error classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorRecoveryAction(str, Enum):
    """Suggested recovery actions for different error types."""

    RETRY = "retry"
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    FAIL_FAST = "fail_fast"
    CIRCUIT_BREAK = "circuit_break"
    GRACEFUL_DEGRADATION = "graceful_degradation"
    MANUAL_INTERVENTION = "manual_intervention"


@dataclass
class ErrorContext:
    """Rich context information for errors."""

    timestamp: float = field(default_factory=time.time)
    request_id: str | None = None
    user_id: str | None = None
    service_name: str | None = None
    method_name: str | None = None
    operation_name: str | None = None
    additional_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "service_name": self.service_name,
            "method_name": self.method_name,
            "operation_name": self.operation_name,
            "additional_context": self.additional_context,
        }


@dataclass
class ErrorDetails:
    """Comprehensive error details with recovery information."""

    code: str
    message: str
    category: str
    severity: ErrorSeverity
    recovery_action: ErrorRecoveryAction
    context: ErrorContext
    stack_trace: str | None = None
    inner_error: ErrorDetails | None = None
    user_facing_message: str | None = None
    documentation_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        result = {
            "code": self.code,
            "message": self.message,
            "category": self.category,
            "severity": self.severity.value,
            "recovery_action": self.recovery_action.value,
            "context": self.context.to_dict(),
        }

        if self.user_facing_message:
            result["user_message"] = self.user_facing_message
        if self.documentation_url:
            result["documentation_url"] = self.documentation_url
        if self.inner_error:
            result["inner_error"] = self.inner_error.to_dict()
        if self.stack_trace:
            result["stack_trace"] = self.stack_trace

        return result


class EnhancedErrorCategory(str, Enum):
    """Extended error categories with more granular classification."""

    # Client errors (4xx equivalent)
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"

    # Server errors (5xx equivalent)
    INTERNAL = "internal"
    TRANSIENT = "transient"
    EXTERNAL_SERVICE = "external_service"
    DATABASE = "database"
    NETWORK = "network"
    CONFIGURATION = "configuration"
    RESOURCE_EXHAUSTED = "resource_exhausted"

    # Business logic errors
    BUSINESS_RULE = "business_rule"
    WORKFLOW = "workflow"

    # Infrastructure errors
    INFRASTRUCTURE = "infrastructure"
    SECURITY = "security"


@dataclass
class EnhancedMartyError(Exception):
    """Enhanced structured application error with rich context."""

    code: str
    message: str
    category: EnhancedErrorCategory = EnhancedErrorCategory.INTERNAL
    severity: ErrorSeverity = ErrorSeverity.MEDIUM
    recovery_action: ErrorRecoveryAction = ErrorRecoveryAction.RETRY
    context: ErrorContext = field(default_factory=ErrorContext)
    user_facing_message: str | None = None
    documentation_url: str | None = None
    inner_exception: Exception | None = None

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

    def to_error_details(self, include_stack_trace: bool = False) -> ErrorDetails:
        """Convert to ErrorDetails for structured responses."""
        stack_trace = None
        if include_stack_trace:
            stack_trace = traceback.format_exc()

        inner_error = None
        if self.inner_exception and isinstance(self.inner_exception, EnhancedMartyError):
            inner_error = self.inner_exception.to_error_details(include_stack_trace)

        return ErrorDetails(
            code=self.code,
            message=self.message,
            category=self.category.value,
            severity=self.severity,
            recovery_action=self.recovery_action,
            context=self.context,
            stack_trace=stack_trace,
            inner_error=inner_error,
            user_facing_message=self.user_facing_message,
            documentation_url=self.documentation_url,
        )


# Specific error types with predefined configurations
class ValidationError(EnhancedMartyError):
    """Client input validation error."""

    def __init__(self, message: str, field_name: str | None = None, **kwargs: Any) -> None:
        context = kwargs.pop("context", ErrorContext())
        if field_name:
            context.additional_context["field_name"] = field_name

        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            category=EnhancedErrorCategory.VALIDATION,
            severity=ErrorSeverity.LOW,
            recovery_action=ErrorRecoveryAction.FAIL_FAST,
            context=context,
            user_facing_message=f"Invalid input: {message}",
            **kwargs,
        )


class AuthenticationError(EnhancedMartyError):
    """Authentication failure error."""

    def __init__(self, message: str = "Authentication failed", **kwargs: Any) -> None:
        super().__init__(
            code="AUTHENTICATION_ERROR",
            message=message,
            category=EnhancedErrorCategory.AUTHENTICATION,
            severity=ErrorSeverity.HIGH,
            recovery_action=ErrorRecoveryAction.FAIL_FAST,
            user_facing_message="Authentication required",
            **kwargs,
        )


class AuthorizationError(EnhancedMartyError):
    """Authorization failure error."""

    def __init__(self, message: str = "Access denied", **kwargs: Any) -> None:
        super().__init__(
            code="AUTHORIZATION_ERROR",
            message=message,
            category=EnhancedErrorCategory.AUTHORIZATION,
            severity=ErrorSeverity.HIGH,
            recovery_action=ErrorRecoveryAction.FAIL_FAST,
            user_facing_message="Insufficient permissions",
            **kwargs,
        )


class NotFoundError(EnhancedMartyError):
    """Resource not found error."""

    def __init__(
        self,
        message: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        context = kwargs.pop("context", ErrorContext())
        if resource_type:
            context.additional_context["resource_type"] = resource_type
        if resource_id:
            context.additional_context["resource_id"] = resource_id

        super().__init__(
            code="NOT_FOUND",
            message=message,
            category=EnhancedErrorCategory.NOT_FOUND,
            severity=ErrorSeverity.LOW,
            recovery_action=ErrorRecoveryAction.FAIL_FAST,
            context=context,
            user_facing_message="Requested resource not found",
            **kwargs,
        )


class ConflictError(EnhancedMartyError):
    """Resource conflict error."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            code="CONFLICT_ERROR",
            message=message,
            category=EnhancedErrorCategory.CONFLICT,
            severity=ErrorSeverity.MEDIUM,
            recovery_action=ErrorRecoveryAction.FAIL_FAST,
            user_facing_message="Conflict with existing resource",
            **kwargs,
        )


class TransientError(EnhancedMartyError):
    """Transient error that should be retried."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            code="TRANSIENT_ERROR",
            message=message,
            category=EnhancedErrorCategory.TRANSIENT,
            severity=ErrorSeverity.MEDIUM,
            recovery_action=ErrorRecoveryAction.RETRY_WITH_BACKOFF,
            user_facing_message="Temporary service issue, please try again",
            **kwargs,
        )


class ExternalServiceError(EnhancedMartyError):
    """External service integration error."""

    def __init__(self, message: str, service_name: str | None = None, **kwargs: Any) -> None:
        context = kwargs.pop("context", ErrorContext())
        if service_name:
            context.additional_context["external_service"] = service_name

        super().__init__(
            code="EXTERNAL_SERVICE_ERROR",
            message=message,
            category=EnhancedErrorCategory.EXTERNAL_SERVICE,
            severity=ErrorSeverity.HIGH,
            recovery_action=ErrorRecoveryAction.CIRCUIT_BREAK,
            context=context,
            user_facing_message="External service temporarily unavailable",
            **kwargs,
        )


class DatabaseError(EnhancedMartyError):
    """Database operation error."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            code="DATABASE_ERROR",
            message=message,
            category=EnhancedErrorCategory.DATABASE,
            severity=ErrorSeverity.HIGH,
            recovery_action=ErrorRecoveryAction.RETRY_WITH_BACKOFF,
            user_facing_message="Database operation failed",
            **kwargs,
        )


class RateLimitError(EnhancedMartyError):
    """Rate limiting error."""

    def __init__(
        self, message: str = "Rate limit exceeded", retry_after: int | None = None, **kwargs: Any
    ) -> None:
        context = kwargs.pop("context", ErrorContext())
        if retry_after:
            context.additional_context["retry_after_seconds"] = retry_after

        super().__init__(
            code="RATE_LIMIT_EXCEEDED",
            message=message,
            category=EnhancedErrorCategory.RATE_LIMITED,
            severity=ErrorSeverity.MEDIUM,
            recovery_action=ErrorRecoveryAction.RETRY_WITH_BACKOFF,
            context=context,
            user_facing_message=f"Rate limit exceeded, try again in {retry_after or 60} seconds",
            **kwargs,
        )


class BusinessRuleError(EnhancedMartyError):
    """Business rule violation error."""

    def __init__(self, message: str, rule_name: str | None = None, **kwargs: Any) -> None:
        context = kwargs.pop("context", ErrorContext())
        if rule_name:
            context.additional_context["rule_name"] = rule_name

        super().__init__(
            code="BUSINESS_RULE_VIOLATION",
            message=message,
            category=EnhancedErrorCategory.BUSINESS_RULE,
            severity=ErrorSeverity.MEDIUM,
            recovery_action=ErrorRecoveryAction.FAIL_FAST,
            context=context,
            **kwargs,
        )


# Enhanced error mapping
ENHANCED_CATEGORY_TO_GRPC_STATUS: dict[EnhancedErrorCategory, grpc.StatusCode] = {
    # Client errors
    EnhancedErrorCategory.VALIDATION: grpc.StatusCode.INVALID_ARGUMENT,
    EnhancedErrorCategory.AUTHENTICATION: grpc.StatusCode.UNAUTHENTICATED,
    EnhancedErrorCategory.AUTHORIZATION: grpc.StatusCode.PERMISSION_DENIED,
    EnhancedErrorCategory.NOT_FOUND: grpc.StatusCode.NOT_FOUND,
    EnhancedErrorCategory.CONFLICT: grpc.StatusCode.ALREADY_EXISTS,
    EnhancedErrorCategory.RATE_LIMITED: grpc.StatusCode.RESOURCE_EXHAUSTED,
    # Server errors
    EnhancedErrorCategory.INTERNAL: grpc.StatusCode.INTERNAL,
    EnhancedErrorCategory.TRANSIENT: grpc.StatusCode.UNAVAILABLE,
    EnhancedErrorCategory.EXTERNAL_SERVICE: grpc.StatusCode.UNAVAILABLE,
    EnhancedErrorCategory.DATABASE: grpc.StatusCode.INTERNAL,
    EnhancedErrorCategory.NETWORK: grpc.StatusCode.UNAVAILABLE,
    EnhancedErrorCategory.CONFIGURATION: grpc.StatusCode.FAILED_PRECONDITION,
    EnhancedErrorCategory.RESOURCE_EXHAUSTED: grpc.StatusCode.RESOURCE_EXHAUSTED,
    # Business logic
    EnhancedErrorCategory.BUSINESS_RULE: grpc.StatusCode.FAILED_PRECONDITION,
    EnhancedErrorCategory.WORKFLOW: grpc.StatusCode.FAILED_PRECONDITION,
    # Infrastructure
    EnhancedErrorCategory.INFRASTRUCTURE: grpc.StatusCode.INTERNAL,
    EnhancedErrorCategory.SECURITY: grpc.StatusCode.PERMISSION_DENIED,
}


def map_enhanced_exception_to_status(
    exc: Exception,
) -> tuple[grpc.StatusCode, str, dict[str, Any] | None]:
    """Map enhanced exceptions to gRPC status with metadata."""
    if isinstance(exc, EnhancedMartyError):
        status_code = ENHANCED_CATEGORY_TO_GRPC_STATUS.get(exc.category, grpc.StatusCode.INTERNAL)
        error_details = exc.to_error_details()
        return status_code, exc.message, error_details.to_dict()

    # Fallback to basic mapping for compatibility
    try:
        from .error_codes import map_exception_to_status

        status_code, message = map_exception_to_status(exc)
        return status_code, message, None
    except ImportError:
        return grpc.StatusCode.INTERNAL, str(exc), None


def create_error_from_grpc_error(grpc_error: grpc.RpcError) -> EnhancedMartyError:
    """Create an enhanced error from a gRPC error."""
    status_code = grpc_error.code()  # type: ignore[attr-defined]
    details = grpc_error.details()  # type: ignore[attr-defined]

    # Map gRPC status to our error categories
    grpc_to_category = {
        grpc.StatusCode.INVALID_ARGUMENT: EnhancedErrorCategory.VALIDATION,
        grpc.StatusCode.UNAUTHENTICATED: EnhancedErrorCategory.AUTHENTICATION,
        grpc.StatusCode.PERMISSION_DENIED: EnhancedErrorCategory.AUTHORIZATION,
        grpc.StatusCode.NOT_FOUND: EnhancedErrorCategory.NOT_FOUND,
        grpc.StatusCode.ALREADY_EXISTS: EnhancedErrorCategory.CONFLICT,
        grpc.StatusCode.RESOURCE_EXHAUSTED: EnhancedErrorCategory.RATE_LIMITED,
        grpc.StatusCode.UNAVAILABLE: EnhancedErrorCategory.TRANSIENT,
        grpc.StatusCode.DEADLINE_EXCEEDED: EnhancedErrorCategory.TRANSIENT,
        grpc.StatusCode.INTERNAL: EnhancedErrorCategory.INTERNAL,
    }

    category = grpc_to_category.get(status_code, EnhancedErrorCategory.INTERNAL)

    return EnhancedMartyError(
        code=f"GRPC_{status_code.name}",
        message=details or f"gRPC error: {status_code.name}",
        category=category,
        severity=(
            ErrorSeverity.HIGH
            if category == EnhancedErrorCategory.INTERNAL
            else ErrorSeverity.MEDIUM
        ),
        recovery_action=(
            ErrorRecoveryAction.RETRY_WITH_BACKOFF
            if category == EnhancedErrorCategory.TRANSIENT
            else ErrorRecoveryAction.FAIL_FAST
        ),
    )


def is_retriable_error(error: EnhancedMartyError) -> bool:
    """Check if an enhanced error should be retried."""
    retriable_categories = {
        EnhancedErrorCategory.TRANSIENT,
        EnhancedErrorCategory.NETWORK,
        EnhancedErrorCategory.EXTERNAL_SERVICE,
        EnhancedErrorCategory.DATABASE,
    }

    return error.category in retriable_categories or error.recovery_action in {
        ErrorRecoveryAction.RETRY,
        ErrorRecoveryAction.RETRY_WITH_BACKOFF,
    }


__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "BusinessRuleError",
    "ConflictError",
    "DatabaseError",
    "EnhancedErrorCategory",
    "EnhancedMartyError",
    "ErrorContext",
    "ErrorDetails",
    "ErrorRecoveryAction",
    "ErrorSeverity",
    "ExternalServiceError",
    "NotFoundError",
    "RateLimitError",
    "TransientError",
    "ValidationError",
    "create_error_from_grpc_error",
    "is_retriable_error",
    "map_enhanced_exception_to_status",
]
