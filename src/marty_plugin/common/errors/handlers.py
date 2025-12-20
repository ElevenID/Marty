"""
Standardized error handling utilities to eliminate duplicate exception patterns.

This module provides common exception classes and error handling patterns
to reduce code duplication across services.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

logger = logging.getLogger(__name__)


# Base exception classes
class MartyError(Exception):
    """Base exception for all Marty-related errors."""

    def __init__(self, message: str, error_code: str | None = None) -> None:
        """Initialize Marty error."""
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class MartyConfigurationError(MartyError):
    """Exception raised for configuration-related errors."""


class MartyValidationError(MartyError):
    """Exception raised for validation errors."""


class MartyServiceError(MartyError):
    """Exception raised for service-related errors."""


class MartyNetworkError(MartyError):
    """Exception raised for network-related errors."""


class MartyDatabaseError(MartyError):
    """Exception raised for database-related errors."""


class MartyCertificateError(MartyError):
    """Exception raised for certificate-related errors."""


# Error handling decorators and utilities
class ErrorHandler:
    """Centralized error handling utilities."""

    @staticmethod
    def handle_common_exceptions(
        logger_instance: logging.Logger | None = None,
        reraise: bool = True,
        default_message: str = "An error occurred",
    ) -> Callable[[F], F]:
        """
        Decorator to handle common exceptions with consistent logging.

        Args:
            logger_instance: Logger to use for error logging
            reraise: Whether to reraise the exception after logging
            default_message: Default message if none provided

        Returns:
            Decorated function
        """

        def decorator(func: F) -> F:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                log = logger_instance or logger
                try:
                    return func(*args, **kwargs)
                except MartyError:
                    # Marty errors are already well-formed, just log and reraise
                    log.exception("Marty error occurred in %s", func.__name__)
                    if reraise:
                        raise
                except (ConnectionError, TimeoutError) as e:
                    error_msg = f"Network error in {func.__name__}: {e}"
                    log.error(error_msg)
                    if reraise:
                        raise MartyNetworkError(error_msg) from e
                except (ValueError, TypeError) as e:
                    error_msg = f"Validation error in {func.__name__}: {e}"
                    log.error(error_msg)
                    if reraise:
                        raise MartyValidationError(error_msg) from e
                except FileNotFoundError as e:
                    error_msg = f"File not found in {func.__name__}: {e}"
                    log.error(error_msg)
                    if reraise:
                        raise MartyConfigurationError(error_msg) from e
                except PermissionError as e:
                    error_msg = f"Permission denied in {func.__name__}: {e}"
                    log.error(error_msg)
                    if reraise:
                        raise MartyConfigurationError(error_msg) from e
                except Exception as e:
                    error_msg = f"Unexpected error in {func.__name__}: {e}"
                    log.exception(error_msg)
                    if reraise:
                        raise MartyServiceError(error_msg) from e
                    return None

            return wrapper  # type: ignore

        return decorator

    @staticmethod
    def log_and_raise(
        exception_class: type[MartyError],
        message: str,
        logger_instance: logging.Logger | None = None,
        error_code: str | None = None,
        original_exception: Exception | None = None,
    ) -> None:
        """
        Log an error and raise a specific exception.

        Args:
            exception_class: Exception class to raise
            message: Error message
            logger_instance: Logger to use
            error_code: Optional error code
            original_exception: Original exception to chain

        Raises:
            MartyError: The specified exception
        """
        log = logger_instance or logger
        log.error(message)

        if original_exception:
            raise exception_class(message, error_code) from original_exception
        else:
            raise exception_class(message, error_code)

    @staticmethod
    def safe_execute(
        func: Callable[[], Any],
        default_value: Any = None,
        logger_instance: logging.Logger | None = None,
        error_message: str | None = None,
    ) -> Any:
        """
        Safely execute a function, returning default value on error.

        Args:
            func: Function to execute
            default_value: Value to return on error
            logger_instance: Logger to use
            error_message: Custom error message

        Returns:
            Function result or default value
        """
        log = logger_instance or logger
        try:
            return func()
        except Exception as e:
            message = error_message or f"Error executing {func.__name__}: {e}"
            log.warning(message)
            return default_value

    @staticmethod
    def validate_required_fields(data: dict[str, Any], required_fields: list[str]) -> None:
        """
        Validate that all required fields are present and not None.

        Args:
            data: Data dictionary to validate
            required_fields: List of required field names

        Raises:
            MartyValidationError: If any required fields are missing
        """
        missing_fields = []
        for field in required_fields:
            if field not in data or data[field] is None:
                missing_fields.append(field)

        if missing_fields:
            error_msg = f"Missing required fields: {', '.join(missing_fields)}"
            raise MartyValidationError(error_msg, "MISSING_REQUIRED_FIELDS")

    @staticmethod
    def retry_on_failure(
        max_attempts: int = 3,
        delay_seconds: float = 1.0,
        backoff_multiplier: float = 2.0,
        exceptions: tuple[type[Exception], ...] = (Exception,),
        logger_instance: logging.Logger | None = None,
    ) -> Callable[[F], F]:
        """
        Decorator to retry function execution on failure.

        Args:
            max_attempts: Maximum number of attempts
            delay_seconds: Initial delay between attempts
            backoff_multiplier: Multiplier for delay on each retry
            exceptions: Tuple of exceptions to catch and retry
            logger_instance: Logger to use

        Returns:
            Decorated function
        """

        def decorator(func: F) -> F:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                log = logger_instance or logger
                last_exception = None
                current_delay = delay_seconds

                for attempt in range(max_attempts):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if attempt < max_attempts - 1:
                            log.warning(
                                "Attempt %d/%d failed for %s: %s. Retrying in %.2f seconds.",
                                attempt + 1,
                                max_attempts,
                                func.__name__,
                                e,
                                current_delay,
                            )
                            import time

                            time.sleep(current_delay)
                            current_delay *= backoff_multiplier
                        else:
                            log.error(
                                "All %d attempts failed for %s. Final error: %s",
                                max_attempts,
                                func.__name__,
                                e,
                            )

                # If we get here, all attempts failed
                if last_exception:
                    raise MartyServiceError(
                        f"Function {func.__name__} failed after {max_attempts} attempts"
                    ) from last_exception
                else:
                    raise MartyServiceError(f"Function {func.__name__} failed unexpectedly")

            return wrapper  # type: ignore

        return decorator


# Context managers for error handling
class ErrorContext:
    """Context manager for consistent error handling."""

    def __init__(
        self,
        operation_name: str,
        logger_instance: logging.Logger | None = None,
        reraise: bool = True,
    ) -> None:
        """Initialize error context."""
        self.operation_name = operation_name
        self.logger = logger_instance or logger
        self.reraise = reraise

    def __enter__(self) -> ErrorContext:
        """Enter error context."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> bool:
        """Exit error context with exception handling."""
        if exc_type is None:
            return False  # No exception occurred

        if issubclass(exc_type, MartyError):
            # Marty errors are already well-formed
            self.logger.exception("Marty error in %s", self.operation_name)
        elif issubclass(exc_type, (ConnectionError, TimeoutError)):
            self.logger.error("Network error in %s: %s", self.operation_name, exc_value)
            if self.reraise:
                raise MartyNetworkError(
                    f"Network error in {self.operation_name}: {exc_value}"
                ) from exc_value
        elif issubclass(exc_type, (ValueError, TypeError)):
            self.logger.error("Validation error in %s: %s", self.operation_name, exc_value)
            if self.reraise:
                raise MartyValidationError(
                    f"Validation error in {self.operation_name}: {exc_value}"
                ) from exc_value
        elif issubclass(exc_type, (FileNotFoundError, PermissionError)):
            self.logger.error("Configuration error in %s: %s", self.operation_name, exc_value)
            if self.reraise:
                raise MartyConfigurationError(
                    f"Configuration error in {self.operation_name}: {exc_value}"
                ) from exc_value
        else:
            self.logger.exception("Unexpected error in %s", self.operation_name)
            if self.reraise:
                raise MartyServiceError(
                    f"Unexpected error in {self.operation_name}: {exc_value}"
                ) from exc_value

        return not self.reraise  # Suppress exception if not reraising


# Convenience functions
def handle_grpc_errors(func: F) -> F:
    """Decorator specifically for gRPC service error handling."""
    return ErrorHandler.handle_common_exceptions(
        logger_instance=logger, reraise=True, default_message="gRPC service error"
    )(func)


def handle_database_errors(func: F) -> F:
    """Decorator specifically for database operation error handling."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception("Database error in %s", func.__name__)
            raise MartyDatabaseError(f"Database operation failed: {e}") from e

    return wrapper  # type: ignore


def handle_certificate_errors(func: F) -> F:
    """Decorator specifically for certificate operation error handling."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.exception("Certificate error in %s", func.__name__)
            raise MartyCertificateError(f"Certificate operation failed: {e}") from e

    return wrapper  # type: ignore
