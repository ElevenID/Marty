"""
Consolidated logging utilities for DRY logging patterns across services
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from typing import Any

from marty_common.logging_config import get_logger, setup_logging


class ServiceLogger:
    """
    Standardized logger wrapper for services with consistent patterns.

    Provides structured logging with service context, performance tracking,
    and standardized log formats across all services.
    """

    def __init__(
        self,
        service_name: str,
        module_name: str | None = None,
        enable_performance_logging: bool = True,
    ) -> None:
        """
        Initialize service logger with consistent patterns.

        Args:
            service_name: Name of the service for context
            module_name: Module name (typically __name__)
            enable_performance_logging: Whether to enable performance tracking
        """
        self.service_name = service_name
        self.module_name = module_name or service_name
        self.enable_performance_logging = enable_performance_logging

        # Create the underlying logger
        self._logger = get_logger(self.module_name)

        # Add service context to all log messages
        self._service_context = {"service": service_name}

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log debug message with service context."""
        self._log_with_context(logging.DEBUG, msg, args, kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log info message with service context."""
        self._log_with_context(logging.INFO, msg, args, kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log warning message with service context."""
        self._log_with_context(logging.WARNING, msg, args, kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log error message with service context."""
        self._log_with_context(logging.ERROR, msg, args, kwargs)

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log critical message with service context."""
        self._log_with_context(logging.CRITICAL, msg, args, kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log exception with service context and stack trace."""
        kwargs.setdefault("exc_info", True)
        self.error(msg, *args, **kwargs)

    def _log_with_context(
        self, level: int, msg: str, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> None:
        """Log message with service context."""
        # Add service context to extra fields
        extra = kwargs.setdefault("extra", {})
        extra.update(self._service_context)

        self._logger.log(level, msg, *args, **kwargs)

    def log_service_startup(self, additional_info: dict[str, Any] | None = None) -> None:
        """Log standardized service startup message."""
        info = {"status": "starting", **self._service_context}
        if additional_info:
            info.update(additional_info)

        self.info("Service starting up", extra=info)

    def log_service_ready(
        self,
        port: int | None = None,
        additional_info: dict[str, Any] | None = None,
    ) -> None:
        """Log standardized service ready message."""
        info = {"status": "ready", **self._service_context}
        if port:
            info["port"] = port
        if additional_info:
            info.update(additional_info)

        self.info("Service ready", extra=info)

    def log_service_shutdown(self, reason: str | None = None) -> None:
        """Log standardized service shutdown message."""
        info = {"status": "shutting_down", **self._service_context}
        if reason:
            info["reason"] = reason

        self.info("Service shutting down", extra=info)

    def log_request_start(self, request_id: str, operation: str, **context: Any) -> None:
        """Log start of request processing."""
        info = {
            "request_id": request_id,
            "operation": operation,
            "phase": "start",
            **self._service_context,
            **context,
        }
        self.info("Request started", extra=info)

    def log_request_end(
        self,
        request_id: str,
        operation: str,
        success: bool = True,
        duration_ms: float | None = None,
        **context: Any,
    ) -> None:
        """Log end of request processing."""
        info = {
            "request_id": request_id,
            "operation": operation,
            "phase": "end",
            "success": success,
            **self._service_context,
            **context,
        }

        if duration_ms is not None:
            info["duration_ms"] = duration_ms

        if success:
            self.info("Request completed", extra=info)
        else:
            self.error("Request failed", extra=info)

    def log_performance_metric(self, metric_name: str, value: float, unit: str = "ms") -> None:
        """Log performance metrics if enabled."""
        if not self.enable_performance_logging:
            return

        info = {
            "metric_name": metric_name,
            "metric_value": value,
            "metric_unit": unit,
            "metric_type": "performance",
            **self._service_context,
        }

        self.info("Performance metric", extra=info)


class LoggingMixin:
    """
    Mixin class to add standardized logging capabilities to any service class.

    Usage:
        class MyService(BaseService, LoggingMixin):
            def __init__(self):
                self.init_logging("my-service")
    """

    def init_logging(
        self,
        service_name: str,
        module_name: str | None = None,
        enable_performance_logging: bool = True,
    ) -> None:
        """
        Initialize logging for the service.

        Args:
            service_name: Name of the service
            module_name: Module name (typically __name__)
            enable_performance_logging: Whether to enable performance tracking
        """
        self.logger = ServiceLogger(
            service_name=service_name,
            module_name=module_name or self.__class__.__module__,
            enable_performance_logging=enable_performance_logging,
        )


def configure_service_logging(
    service_name: str,
    log_level: str | None = None,
    enable_grpc_logging: bool = True,
    enable_structured_logging: bool = True,
) -> ServiceLogger:
    """
    Configure logging for a service with standard patterns.

    Args:
        service_name: Name of the service
        log_level: Log level override
        enable_grpc_logging: Whether to enable gRPC logging
        enable_structured_logging: Whether to use structured logging

    Returns:
        Configured service logger
    """
    # Set log level if provided
    if log_level:
        os.environ["LOG_LEVEL"] = log_level.upper()

    # Configure the underlying logging system
    setup_logging(
        service_name=service_name,
        enable_grpc_logging=enable_grpc_logging,
    )

    # Create and return service logger
    return ServiceLogger(
        service_name=service_name,
        module_name=service_name,
        enable_performance_logging=enable_structured_logging,
    )


def get_service_logger(service_name: str, module_name: str | None = None) -> ServiceLogger:
    """
    Get a service logger instance.

    Args:
        service_name: Name of the service
        module_name: Module name (typically __name__)

    Returns:
        Service logger instance
    """
    return ServiceLogger(
        service_name=service_name,
        module_name=module_name,
    )


# Convenience functions for common logging patterns
def log_service_event(logger: ServiceLogger, event_type: str, message: str, **context: Any) -> None:
    """Log a service event with standardized format."""
    info = {"event_type": event_type, **context}
    logger.info(message, extra=info)


def log_error_with_context(
    logger: ServiceLogger, error: Exception, operation: str, **context: Any
) -> None:
    """Log an error with full context."""
    info = {
        "operation": operation,
        "error_type": type(error).__name__,
        "error_message": str(error),
        **context,
    }
    logger.exception("Operation failed", extra=info)


# Performance tracking utilities
class PerformanceTimer:
    """Context manager for tracking operation performance."""

    def __init__(self, logger: ServiceLogger, operation: str) -> None:
        """
        Initialize performance timer.

        Args:
            logger: Service logger to log metrics to
            operation: Name of the operation being timed
        """
        self.logger = logger
        self.operation = operation
        self.start_time: float | None = None
        self.end_time: float | None = None

    def __enter__(self) -> PerformanceTimer:
        """Start timing."""
        self.start_time = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """End timing and log performance metric."""
        self.end_time = time.perf_counter()

        if self.start_time is not None:
            duration_ms = (self.end_time - self.start_time) * 1000
            self.logger.log_performance_metric(
                metric_name=f"{self.operation}_duration",
                value=duration_ms,
                unit="ms",
            )

    def get_duration_ms(self) -> float | None:
        """Get duration in milliseconds if timing is complete."""
        if self.start_time is not None and self.end_time is not None:
            return (self.end_time - self.start_time) * 1000
        return None


def log_with_performance(
    logger: ServiceLogger, operation: str
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator to log function execution with performance timing.

    Args:
        logger: Service logger to use
        operation: Name of the operation for logging
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with PerformanceTimer(logger, operation):
                logger.debug(f"Starting {operation}")
                try:
                    result = func(*args, **kwargs)
                except Exception as e:
                    log_error_with_context(logger, e, operation)
                    raise
                else:
                    logger.debug(f"Completed {operation}")
                    return result

        return wrapper

    return decorator
