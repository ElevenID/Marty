"""
Unified HTTP Error Response Schema for Marty APIs.

This module provides Pydantic models for standardized API error responses.
These models integrate with the existing EnhancedMartyError system and provide
a consistent JSON structure for all HTTP API responses.

Error codes follow a hierarchical naming convention:
- AUTH.INVALID_TOKEN, AUTH.SESSION_EXPIRED
- ORG.INVITE_EXPIRED, ORG.NOT_FOUND
- USER.VALIDATION_FAILED, USER.NOT_FOUND
- API.RATE_LIMITED, API.INVALID_REQUEST
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ErrorSeverity(str, Enum):
    """Error severity levels for client handling."""

    LOW = "low"  # User can easily recover (validation errors)
    MEDIUM = "medium"  # User may need to retry or adjust
    HIGH = "high"  # Significant issue requiring attention
    CRITICAL = "critical"  # System-level failure


class ErrorRecoveryAction(str, Enum):
    """Suggested recovery action for clients."""

    RETRY = "retry"  # Retry immediately
    RETRY_WITH_BACKOFF = "retry_with_backoff"  # Retry with exponential backoff
    REAUTHENTICATE = "reauthenticate"  # User needs to log in again
    CONTACT_SUPPORT = "contact_support"  # Manual intervention needed
    FAIL_FAST = "fail_fast"  # Don't retry, fix the input


# =============================================================================
# Hierarchical Error Codes
# =============================================================================

class ErrorCode:
    """
    Hierarchical error codes for programmatic handling.
    
    Format: CATEGORY.SPECIFIC_ERROR
    
    These codes are stable and can be relied upon by API clients.
    """

    # Authentication errors (AUTH.*)
    AUTH_INVALID_TOKEN = "AUTH.INVALID_TOKEN"
    AUTH_TOKEN_EXPIRED = "AUTH.TOKEN_EXPIRED"
    AUTH_SESSION_EXPIRED = "AUTH.SESSION_EXPIRED"
    AUTH_INVALID_CREDENTIALS = "AUTH.INVALID_CREDENTIALS"
    AUTH_MFA_REQUIRED = "AUTH.MFA_REQUIRED"
    AUTH_ACCOUNT_LOCKED = "AUTH.ACCOUNT_LOCKED"

    # Authorization errors (AUTHZ.*)
    AUTHZ_PERMISSION_DENIED = "AUTHZ.PERMISSION_DENIED"
    AUTHZ_INSUFFICIENT_SCOPE = "AUTHZ.INSUFFICIENT_SCOPE"
    AUTHZ_RESOURCE_FORBIDDEN = "AUTHZ.RESOURCE_FORBIDDEN"

    # Organization errors (ORG.*)
    ORG_NOT_FOUND = "ORG.NOT_FOUND"
    ORG_INVITE_EXPIRED = "ORG.INVITE_EXPIRED"
    ORG_INVITE_INVALID = "ORG.INVITE_INVALID"
    ORG_MEMBERSHIP_EXISTS = "ORG.MEMBERSHIP_EXISTS"
    ORG_NAME_TAKEN = "ORG.NAME_TAKEN"
    ORG_LIMIT_REACHED = "ORG.LIMIT_REACHED"

    # User errors (USER.*)
    USER_NOT_FOUND = "USER.NOT_FOUND"
    USER_ALREADY_EXISTS = "USER.ALREADY_EXISTS"
    USER_VALIDATION_FAILED = "USER.VALIDATION_FAILED"
    USER_ONBOARDING_INCOMPLETE = "USER.ONBOARDING_INCOMPLETE"

    # Application/Applicant errors (APP.*)
    APP_NOT_FOUND = "APP.NOT_FOUND"
    APP_INVALID_STATUS = "APP.INVALID_STATUS"
    APP_DOCUMENT_MISSING = "APP.DOCUMENT_MISSING"
    APP_SUBMISSION_FAILED = "APP.SUBMISSION_FAILED"

    # Credential errors (CRED.*)
    CRED_ISSUANCE_FAILED = "CRED.ISSUANCE_FAILED"
    CRED_VERIFICATION_FAILED = "CRED.VERIFICATION_FAILED"
    CRED_REVOKED = "CRED.REVOKED"
    CRED_EXPIRED = "CRED.EXPIRED"
    CRED_INVALID_FORMAT = "CRED.INVALID_FORMAT"

    # Validation errors (VAL.*)
    VAL_REQUIRED_FIELD = "VAL.REQUIRED_FIELD"
    VAL_INVALID_FORMAT = "VAL.INVALID_FORMAT"
    VAL_OUT_OF_RANGE = "VAL.OUT_OF_RANGE"
    VAL_CONSTRAINT_VIOLATED = "VAL.CONSTRAINT_VIOLATED"

    # API errors (API.*)
    API_RATE_LIMITED = "API.RATE_LIMITED"
    API_INVALID_REQUEST = "API.INVALID_REQUEST"
    API_METHOD_NOT_ALLOWED = "API.METHOD_NOT_ALLOWED"
    API_NOT_FOUND = "API.NOT_FOUND"
    API_VERSION_UNSUPPORTED = "API.VERSION_UNSUPPORTED"

    # Server errors (SRV.*)
    SRV_INTERNAL_ERROR = "SRV.INTERNAL_ERROR"
    SRV_DATABASE_ERROR = "SRV.DATABASE_ERROR"
    SRV_EXTERNAL_SERVICE = "SRV.EXTERNAL_SERVICE"
    SRV_TEMPORARILY_UNAVAILABLE = "SRV.TEMPORARILY_UNAVAILABLE"
    SRV_TIMEOUT = "SRV.TIMEOUT"

    # Client errors (CLIENT.*)
    CLIENT_ERROR_REPORTED = "CLIENT.ERROR_REPORTED"
    CLIENT_RATE_LIMITED = "CLIENT.RATE_LIMITED"


# =============================================================================
# Error Response Models
# =============================================================================

class ErrorDetail(BaseModel):
    """
    Detailed error information for a single error.
    
    This structure provides both machine-readable codes for programmatic
    handling and human-readable messages for display.
    """

    code: str = Field(
        ...,
        description="Hierarchical error code (e.g., 'AUTH.INVALID_TOKEN')",
        json_schema_extra={"example": "ORG.INVITE_EXPIRED"},
    )
    message: str = Field(
        ...,
        description="Technical error message for developers/logs",
        json_schema_extra={"example": "Invite code 'ABC123' expired at 2025-12-15T00:00:00Z"},
    )
    user_message: str = Field(
        ...,
        description="User-friendly message safe to display in UI",
        json_schema_extra={"example": "This invite code has expired. Please request a new one."},
    )
    severity: ErrorSeverity = Field(
        default=ErrorSeverity.MEDIUM,
        description="Error severity level",
    )
    recovery_action: ErrorRecoveryAction = Field(
        default=ErrorRecoveryAction.FAIL_FAST,
        description="Suggested recovery action for the client",
    )
    field: str | None = Field(
        default=None,
        description="Field name for validation errors",
        json_schema_extra={"example": "invite_code"},
    )
    details: dict[str, Any] | None = Field(
        default=None,
        description="Additional error-specific details",
        json_schema_extra={"example": {"expired_at": "2025-12-15T00:00:00Z"}},
    )
    documentation_url: str | None = Field(
        default=None,
        description="URL to error documentation",
        json_schema_extra={"example": "https://docs.marty.io/errors/ORG.INVITE_EXPIRED"},
    )


class ErrorResponse(BaseModel):
    """
    Standard API error response structure.
    
    All API errors should return this structure for consistent client handling.
    """

    error: ErrorDetail = Field(
        ...,
        description="Primary error information",
    )
    request_id: str = Field(
        ...,
        description="Unique request identifier for tracing/debugging",
        json_schema_extra={"example": "550e8400-e29b-41d4-a716-446655440000"},
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp when error occurred",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "error": {
                    "code": "ORG.INVITE_EXPIRED",
                    "message": "Invite code 'ABC123' expired at 2025-12-15T00:00:00Z",
                    "user_message": "This invite code has expired. Please request a new one.",
                    "severity": "low",
                    "recovery_action": "fail_fast",
                    "field": "invite_code",
                    "details": {"expired_at": "2025-12-15T00:00:00Z"},
                    "documentation_url": "https://docs.marty.io/errors/ORG.INVITE_EXPIRED",
                },
                "request_id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": 1734355200.0,
            }
        }


class ValidationErrorResponse(BaseModel):
    """
    Validation error response with multiple field errors.
    
    Used when multiple validation errors occur simultaneously.
    """

    errors: list[ErrorDetail] = Field(
        ...,
        description="List of validation errors",
    )
    request_id: str = Field(
        ...,
        description="Unique request identifier for tracing/debugging",
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp when error occurred",
    )


class ClientErrorReport(BaseModel):
    """
    Client-side error report submitted to /api/client-errors.
    
    Used by the UI to report JavaScript errors, component crashes,
    and other client-side issues for monitoring.
    """

    error_code: str = Field(
        ...,
        description="Error code or type (e.g., 'TypeError', 'ChunkLoadError')",
    )
    message: str = Field(
        ...,
        description="Error message",
        max_length=2000,
    )
    stack_trace: str | None = Field(
        default=None,
        description="JavaScript stack trace",
        max_length=10000,
    )
    component_stack: str | None = Field(
        default=None,
        description="React component stack (from ErrorBoundary)",
        max_length=5000,
    )
    url: str = Field(
        ...,
        description="Page URL where error occurred",
        max_length=500,
    )
    user_agent: str | None = Field(
        default=None,
        description="Browser user agent",
        max_length=500,
    )
    user_id: str | None = Field(
        default=None,
        description="Authenticated user ID if available",
    )
    session_id: str | None = Field(
        default=None,
        description="Session ID for correlation",
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Client-side timestamp when error occurred",
    )
    context: dict[str, Any] | None = Field(
        default=None,
        description="Additional context (route, props, state)",
    )


class ClientErrorAcknowledgment(BaseModel):
    """Response returned after accepting a client error report."""

    received: bool = True
    error_id: str = Field(
        ...,
        description="Server-generated ID for the reported error",
    )


# =============================================================================
# HTTP Status Code Mapping
# =============================================================================

ERROR_CODE_TO_HTTP_STATUS: dict[str, int] = {
    # 400 Bad Request
    ErrorCode.VAL_REQUIRED_FIELD: 400,
    ErrorCode.VAL_INVALID_FORMAT: 400,
    ErrorCode.VAL_OUT_OF_RANGE: 400,
    ErrorCode.VAL_CONSTRAINT_VIOLATED: 400,
    ErrorCode.API_INVALID_REQUEST: 400,
    # 401 Unauthorized
    ErrorCode.AUTH_INVALID_TOKEN: 401,
    ErrorCode.AUTH_TOKEN_EXPIRED: 401,
    ErrorCode.AUTH_SESSION_EXPIRED: 401,
    ErrorCode.AUTH_INVALID_CREDENTIALS: 401,
    ErrorCode.AUTH_MFA_REQUIRED: 401,
    # 403 Forbidden
    ErrorCode.AUTHZ_PERMISSION_DENIED: 403,
    ErrorCode.AUTHZ_INSUFFICIENT_SCOPE: 403,
    ErrorCode.AUTHZ_RESOURCE_FORBIDDEN: 403,
    ErrorCode.AUTH_ACCOUNT_LOCKED: 403,
    # 404 Not Found
    ErrorCode.ORG_NOT_FOUND: 404,
    ErrorCode.USER_NOT_FOUND: 404,
    ErrorCode.APP_NOT_FOUND: 404,
    ErrorCode.API_NOT_FOUND: 404,
    # 409 Conflict
    ErrorCode.ORG_MEMBERSHIP_EXISTS: 409,
    ErrorCode.ORG_NAME_TAKEN: 409,
    ErrorCode.USER_ALREADY_EXISTS: 409,
    # 410 Gone
    ErrorCode.ORG_INVITE_EXPIRED: 410,
    ErrorCode.ORG_INVITE_INVALID: 410,
    # 422 Unprocessable Entity
    ErrorCode.APP_INVALID_STATUS: 422,
    ErrorCode.APP_DOCUMENT_MISSING: 422,
    ErrorCode.CRED_INVALID_FORMAT: 422,
    # 429 Too Many Requests
    ErrorCode.API_RATE_LIMITED: 429,
    ErrorCode.CLIENT_RATE_LIMITED: 429,
    ErrorCode.ORG_LIMIT_REACHED: 429,
    # 500 Internal Server Error
    ErrorCode.SRV_INTERNAL_ERROR: 500,
    ErrorCode.SRV_DATABASE_ERROR: 500,
    ErrorCode.CRED_ISSUANCE_FAILED: 500,
    # 502 Bad Gateway
    ErrorCode.SRV_EXTERNAL_SERVICE: 502,
    # 503 Service Unavailable
    ErrorCode.SRV_TEMPORARILY_UNAVAILABLE: 503,
    # 504 Gateway Timeout
    ErrorCode.SRV_TIMEOUT: 504,
}


def get_http_status_for_error_code(code: str) -> int:
    """Get the appropriate HTTP status code for an error code."""
    return ERROR_CODE_TO_HTTP_STATUS.get(code, 500)


# =============================================================================
# Documentation URL Builder
# =============================================================================

DOCS_BASE_URL = "https://docs.marty.io/errors"


def get_documentation_url(code: str) -> str:
    """Generate documentation URL for an error code."""
    return f"{DOCS_BASE_URL}/{code.replace('.', '/')}"
