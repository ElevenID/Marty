"""
Global FastAPI Exception Handlers.

This module provides centralized exception handling for all Marty FastAPI applications.
It converts exceptions into the unified ErrorResponse format and ensures consistent
error responses across all API endpoints.

Usage:
    from marty_common.errors.fastapi_handlers import register_exception_handlers
    
    app = FastAPI()
    register_exception_handlers(app)
"""

from __future__ import annotations

import logging
import traceback
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .handlers import (
    MartyConfigurationError,
    MartyCertificateError,
    MartyDatabaseError,
    MartyError,
    MartyNetworkError,
    MartyServiceError,
    MartyValidationError,
)
from .schema import (
    ErrorCode,
    ErrorDetail,
    ErrorRecoveryAction,
    ErrorResponse,
    ErrorSeverity,
    ValidationErrorResponse,
    get_documentation_url,
    get_http_status_for_error_code,
)

if TYPE_CHECKING:
    from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Context variable for request ID (set by middleware)
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Get the current request ID from context."""
    return request_id_ctx.get() or str(uuid4())


def set_request_id(request_id: str) -> None:
    """Set the request ID in context."""
    request_id_ctx.set(request_id)


# =============================================================================
# Exception Handlers
# =============================================================================


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handle Starlette/FastAPI HTTP exceptions."""
    request_id = get_request_id()
    
    # Map HTTP status codes to error codes
    status_to_code = {
        400: ErrorCode.API_INVALID_REQUEST,
        401: ErrorCode.AUTH_INVALID_TOKEN,
        403: ErrorCode.AUTHZ_PERMISSION_DENIED,
        404: ErrorCode.API_NOT_FOUND,
        405: ErrorCode.API_METHOD_NOT_ALLOWED,
        409: ErrorCode.ORG_MEMBERSHIP_EXISTS,
        422: ErrorCode.VAL_CONSTRAINT_VIOLATED,
        429: ErrorCode.API_RATE_LIMITED,
        500: ErrorCode.SRV_INTERNAL_ERROR,
        502: ErrorCode.SRV_EXTERNAL_SERVICE,
        503: ErrorCode.SRV_TEMPORARILY_UNAVAILABLE,
        504: ErrorCode.SRV_TIMEOUT,
    }
    
    error_code = status_to_code.get(exc.status_code, ErrorCode.SRV_INTERNAL_ERROR)
    
    # Determine user message based on status code
    user_messages = {
        400: "The request was invalid. Please check your input and try again.",
        401: "You need to log in to access this resource.",
        403: "You don't have permission to access this resource.",
        404: "The requested resource was not found.",
        405: "This action is not allowed.",
        409: "This action conflicts with an existing resource.",
        422: "The request data could not be processed.",
        429: "Too many requests. Please slow down.",
        500: "An unexpected error occurred. Please try again later.",
        502: "A dependent service is temporarily unavailable.",
        503: "The service is temporarily unavailable. Please try again later.",
        504: "The request timed out. Please try again.",
    }
    
    user_message = user_messages.get(
        exc.status_code,
        "An error occurred. Please try again."
    )
    
    # Determine severity and recovery action
    if exc.status_code < 500:
        severity = ErrorSeverity.LOW
        recovery_action = ErrorRecoveryAction.FAIL_FAST
    elif exc.status_code in (502, 503, 504):
        severity = ErrorSeverity.MEDIUM
        recovery_action = ErrorRecoveryAction.RETRY_WITH_BACKOFF
    else:
        severity = ErrorSeverity.HIGH
        recovery_action = ErrorRecoveryAction.CONTACT_SUPPORT
    
    if exc.status_code == 401:
        recovery_action = ErrorRecoveryAction.REAUTHENTICATE
    elif exc.status_code == 429:
        recovery_action = ErrorRecoveryAction.RETRY_WITH_BACKOFF
    
    error_response = ErrorResponse(
        error=ErrorDetail(
            code=error_code,
            message=str(exc.detail),
            user_message=user_message,
            severity=severity,
            recovery_action=recovery_action,
            documentation_url=get_documentation_url(error_code),
        ),
        request_id=request_id,
    )
    
    logger.warning(
        "HTTP exception: status=%d code=%s request_id=%s path=%s detail=%s",
        exc.status_code,
        error_code,
        request_id,
        request.url.path,
        exc.detail,
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(),
        headers={"X-Request-ID": request_id},
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic/FastAPI validation errors."""
    request_id = get_request_id()
    
    errors: list[ErrorDetail] = []
    for error in exc.errors():
        # Extract field path
        field_path = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        
        # Create user-friendly message
        error_type = error["type"]
        user_message = _get_validation_user_message(error_type, field_path, error)
        
        errors.append(
            ErrorDetail(
                code=ErrorCode.VAL_INVALID_FORMAT,
                message=error["msg"],
                user_message=user_message,
                severity=ErrorSeverity.LOW,
                recovery_action=ErrorRecoveryAction.FAIL_FAST,
                field=field_path,
                details={"type": error_type, "input": error.get("input")},
                documentation_url=get_documentation_url(ErrorCode.VAL_INVALID_FORMAT),
            )
        )
    
    validation_response = ValidationErrorResponse(
        errors=errors,
        request_id=request_id,
    )
    
    logger.info(
        "Validation error: request_id=%s path=%s errors=%d",
        request_id,
        request.url.path,
        len(errors),
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=validation_response.model_dump(),
        headers={"X-Request-ID": request_id},
    )


def _get_validation_user_message(
    error_type: str, field: str, error: dict[str, Any]
) -> str:
    """Generate user-friendly validation error messages."""
    field_display = field.replace("_", " ").title() if field else "This field"
    
    messages = {
        "missing": f"{field_display} is required.",
        "value_error.missing": f"{field_display} is required.",
        "string_too_short": f"{field_display} is too short.",
        "string_too_long": f"{field_display} is too long.",
        "string_pattern_mismatch": f"{field_display} format is invalid.",
        "value_error.email": f"{field_display} must be a valid email address.",
        "type_error.integer": f"{field_display} must be a number.",
        "type_error.string": f"{field_display} must be text.",
        "value_error.number.not_ge": f"{field_display} must be greater than or equal to the minimum value.",
        "value_error.number.not_le": f"{field_display} must be less than or equal to the maximum value.",
        "value_error.url": f"{field_display} must be a valid URL.",
        "value_error.uuid": f"{field_display} must be a valid ID.",
    }
    
    return messages.get(error_type, f"{field_display} is invalid.")


async def marty_error_handler(request: Request, exc: MartyError) -> JSONResponse:
    """Handle Marty-specific exceptions."""
    request_id = get_request_id()
    
    # Map exception types to error codes and status codes
    if isinstance(exc, MartyValidationError):
        error_code = exc.error_code or ErrorCode.VAL_CONSTRAINT_VIOLATED
        status_code = 400
        user_message = "The provided data is invalid."
        severity = ErrorSeverity.LOW
        recovery_action = ErrorRecoveryAction.FAIL_FAST
    elif isinstance(exc, MartyConfigurationError):
        error_code = exc.error_code or ErrorCode.SRV_INTERNAL_ERROR
        status_code = 500
        user_message = "A configuration error occurred. Please contact support."
        severity = ErrorSeverity.HIGH
        recovery_action = ErrorRecoveryAction.CONTACT_SUPPORT
    elif isinstance(exc, MartyNetworkError):
        error_code = exc.error_code or ErrorCode.SRV_EXTERNAL_SERVICE
        status_code = 502
        user_message = "A network error occurred. Please try again."
        severity = ErrorSeverity.MEDIUM
        recovery_action = ErrorRecoveryAction.RETRY_WITH_BACKOFF
    elif isinstance(exc, MartyDatabaseError):
        error_code = exc.error_code or ErrorCode.SRV_DATABASE_ERROR
        status_code = 500
        user_message = "A database error occurred. Please try again."
        severity = ErrorSeverity.HIGH
        recovery_action = ErrorRecoveryAction.RETRY_WITH_BACKOFF
    elif isinstance(exc, MartyCertificateError):
        error_code = exc.error_code or ErrorCode.CRED_ISSUANCE_FAILED
        status_code = 500
        user_message = "A certificate error occurred. Please contact support."
        severity = ErrorSeverity.HIGH
        recovery_action = ErrorRecoveryAction.CONTACT_SUPPORT
    elif isinstance(exc, MartyServiceError):
        error_code = exc.error_code or ErrorCode.SRV_INTERNAL_ERROR
        status_code = 500
        user_message = "An unexpected error occurred. Please try again."
        severity = ErrorSeverity.MEDIUM
        recovery_action = ErrorRecoveryAction.RETRY
    else:
        error_code = exc.error_code or ErrorCode.SRV_INTERNAL_ERROR
        status_code = get_http_status_for_error_code(exc.error_code or "")
        user_message = "An error occurred. Please try again."
        severity = ErrorSeverity.MEDIUM
        recovery_action = ErrorRecoveryAction.RETRY
    
    error_response = ErrorResponse(
        error=ErrorDetail(
            code=error_code,
            message=exc.message,
            user_message=user_message,
            severity=severity,
            recovery_action=recovery_action,
            documentation_url=get_documentation_url(error_code),
        ),
        request_id=request_id,
    )
    
    logger.error(
        "Marty error: code=%s request_id=%s path=%s message=%s",
        error_code,
        request_id,
        request.url.path,
        exc.message,
        exc_info=True,
    )
    
    return JSONResponse(
        status_code=status_code,
        content=error_response.model_dump(),
        headers={"X-Request-ID": request_id},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle any unhandled exceptions."""
    request_id = get_request_id()
    
    # Log the full exception for debugging
    logger.exception(
        "Unhandled exception: request_id=%s path=%s",
        request_id,
        request.url.path,
    )
    
    error_response = ErrorResponse(
        error=ErrorDetail(
            code=ErrorCode.SRV_INTERNAL_ERROR,
            message=str(exc) if logger.isEnabledFor(logging.DEBUG) else "Internal server error",
            user_message="An unexpected error occurred. Our team has been notified.",
            severity=ErrorSeverity.CRITICAL,
            recovery_action=ErrorRecoveryAction.CONTACT_SUPPORT,
            documentation_url=get_documentation_url(ErrorCode.SRV_INTERNAL_ERROR),
        ),
        request_id=request_id,
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.model_dump(),
        headers={"X-Request-ID": request_id},
    )


# =============================================================================
# Request ID Middleware
# =============================================================================


async def request_id_middleware(request: Request, call_next: Callable) -> Any:
    """Middleware to generate and propagate request IDs."""
    # Check for existing request ID header
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    set_request_id(request_id)
    
    # Add request ID to request state for easy access
    request.state.request_id = request_id
    
    response = await call_next(request)
    
    # Add request ID to response headers
    response.headers["X-Request-ID"] = request_id
    
    return response


# =============================================================================
# Registration Function
# =============================================================================


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register all exception handlers on a FastAPI application.
    
    This should be called during application startup:
    
        app = FastAPI()
        register_exception_handlers(app)
    
    Args:
        app: The FastAPI application instance
    """
    # Add request ID middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    app.add_middleware(BaseHTTPMiddleware, dispatch=request_id_middleware)
    
    # Register exception handlers (order matters - most specific first)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(MartyValidationError, marty_error_handler)
    app.add_exception_handler(MartyConfigurationError, marty_error_handler)
    app.add_exception_handler(MartyNetworkError, marty_error_handler)
    app.add_exception_handler(MartyDatabaseError, marty_error_handler)
    app.add_exception_handler(MartyCertificateError, marty_error_handler)
    app.add_exception_handler(MartyServiceError, marty_error_handler)
    app.add_exception_handler(MartyError, marty_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    
    logger.info("Registered global exception handlers")
