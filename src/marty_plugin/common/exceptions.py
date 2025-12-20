"""
Custom exceptions for Marty services.
"""

import grpc


class MartyServiceException(Exception):
    """Base exception class for Marty services."""

    def __init__(self, message, status_code=None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code if status_code is not None else grpc.StatusCode.INTERNAL


class InvalidInputError(MartyServiceException):
    """Exception raised for errors in the input provided by the user."""

    def __init__(self, message) -> None:
        super().__init__(message, grpc.StatusCode.INVALID_ARGUMENT)


class ResourceNotFoundError(MartyServiceException):
    """Exception raised when a requested resource is not found."""

    def __init__(self, message) -> None:
        super().__init__(message, grpc.StatusCode.NOT_FOUND)


class OperationFailedError(MartyServiceException):
    """Exception raised when an operation fails for an internal reason."""

    def __init__(self, message) -> None:
        super().__init__(message, grpc.StatusCode.INTERNAL)


class ConfigurationError(MartyServiceException):
    """Exception raised for configuration-related errors."""

    def __init__(self, message) -> None:
        super().__init__(message, grpc.StatusCode.FAILED_PRECONDITION)


class AuthenticationError(MartyServiceException):
    """Exception raised for authentication failures."""

    def __init__(self, message="Authentication failed.") -> None:
        super().__init__(message, grpc.StatusCode.UNAUTHENTICATED)


class PermissionDeniedError(MartyServiceException):
    """Exception raised when an action is denied due to insufficient permissions."""

    def __init__(self, message="Permission denied.") -> None:
        super().__init__(message, grpc.StatusCode.PERMISSION_DENIED)


class ServiceUnavailableError(MartyServiceException):
    """Exception raised when a dependent service is unavailable."""

    def __init__(self, message="A dependent service is currently unavailable.") -> None:
        super().__init__(message, grpc.StatusCode.UNAVAILABLE)


class MartyTimeoutError(MartyServiceException):
    """Exception raised when an operation times out."""

    def __init__(self, message="The operation timed out.") -> None:
        super().__init__(message, grpc.StatusCode.DEADLINE_EXCEEDED)


class ServiceCommunicationError(MartyServiceException):
    """Exception raised for errors in communication between services."""

    def __init__(self, message="Error communicating with a dependent service.") -> None:
        super().__init__(message, grpc.StatusCode.UNAVAILABLE)


# Example of a more specific error
class CertificateGenerationError(OperationFailedError):
    """Raised when certificate generation fails."""

    def __init__(self, reason) -> None:
        super().__init__(f"Certificate generation failed: {reason}")
