"""Error handling utilities for Marty services."""

from .handlers import (
    ErrorContext,
    ErrorHandler,
    MartyCertificateError,
    MartyConfigurationError,
    MartyDatabaseError,
    MartyError,
    MartyNetworkError,
    MartyServiceError,
    MartyValidationError,
    handle_certificate_errors,
    handle_database_errors,
    handle_grpc_errors,
)

from .schema import (
    ClientErrorAcknowledgment,
    ClientErrorReport,
    ErrorCode,
    ErrorDetail,
    ErrorRecoveryAction,
    ErrorResponse,
    ErrorSeverity,
    ValidationErrorResponse,
    get_documentation_url,
    get_http_status_for_error_code,
)

from .fastapi_handlers import (
    get_request_id,
    register_exception_handlers,
    set_request_id,
)

__all__ = [
    # Handler utilities
    "ErrorContext",
    "ErrorHandler",
    "MartyCertificateError",
    "MartyConfigurationError",
    "MartyDatabaseError",
    "MartyError",
    "MartyNetworkError",
    "MartyServiceError",
    "MartyValidationError",
    "handle_certificate_errors",
    "handle_database_errors",
    "handle_grpc_errors",
    # Schema models
    "ClientErrorAcknowledgment",
    "ClientErrorReport",
    "ErrorCode",
    "ErrorDetail",
    "ErrorRecoveryAction",
    "ErrorResponse",
    "ErrorSeverity",
    "ValidationErrorResponse",
    "get_documentation_url",
    "get_http_status_for_error_code",
    # FastAPI handlers
    "get_request_id",
    "register_exception_handlers",
    "set_request_id",
]
