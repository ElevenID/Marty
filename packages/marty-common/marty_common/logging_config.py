"""Logging configuration for Marty services."""

from __future__ import annotations

import logging
import os
import sys

from opentelemetry import trace

# Custom log format with service name
DEFAULT_LOG_FORMAT = (
    "%(asctime)s - %(levelname)s - [%(service_name)s] - [%(name)s] - "
    "[%(module)s.%(funcName)s:%(lineno)d] - %(message)s"
)

LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}

DEFAULT_LOG_LEVEL = "INFO"
LOG_OFF_LEVEL = "OFF"  # Special string to turn off logging


class ServiceNameFilter(logging.Filter):
    """Filter to inject service name into log records."""

    def __init__(self, service_name: str) -> None:
        """Initialize filter with service name."""
        super().__init__()
        self.service_name = service_name

    def filter(self, record: logging.LogRecord) -> bool:
        """Add service name to log record."""
        record.service_name = self.service_name
        return True


class TraceContextFilter(logging.Filter):
    """Filter to inject trace context into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add trace_id and span_id to log record if available."""
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            span_context = current_span.get_span_context()
            record.trace_id = format(span_context.trace_id, "032x")
            record.span_id = format(span_context.span_id, "016x")
        else:
            record.trace_id = None
            record.span_id = None
        return True


class MartyJSONFormatter(logging.Formatter):
    """JSON formatter for structured logging with trace correlation."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        import json
        from datetime import datetime

        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service_name", "unknown"),
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "file": record.filename,
        }

        # Add trace context if available
        if hasattr(record, "trace_id") and record.trace_id:
            log_entry["trace_id"] = record.trace_id
        if hasattr(record, "span_id") and record.span_id:
            log_entry["span_id"] = record.span_id

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging(
    service_name: str = "MartyService",
    log_level_env_var: str = "LOG_LEVEL",
    log_format_env_var: str = "LOG_FORMAT",
    enable_grpc_logging: bool = True,
) -> None:
    """
    Configure logging for the application.

    Args:
        service_name: Name of the service for log identification
        log_level_env_var: Environment variable to read the log level from
        log_format_env_var: Environment variable to read the log format from
        enable_grpc_logging: Whether to enable gRPC log streaming
    """
    log_level_str = os.environ.get(log_level_env_var, DEFAULT_LOG_LEVEL).upper()
    log_format_str = os.environ.get(log_format_env_var, DEFAULT_LOG_FORMAT)

    root_logger = logging.getLogger()

    # Remove any existing handlers to prevent duplicate messages
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    if log_level_str == LOG_OFF_LEVEL:
        # Turn off logging by setting level high and adding no handlers
        root_logger.setLevel(logging.CRITICAL + 1)
        print(f"Logging is OFF for {service_name}.", file=sys.stderr)
        return

    numeric_log_level = LOG_LEVELS.get(log_level_str, logging.INFO)
    root_logger.setLevel(numeric_log_level)

    console_handler = logging.StreamHandler(sys.stdout)
    if log_format_str.lower() == "json":
        formatter = MartyJSONFormatter()
    else:
        formatter = logging.Formatter(log_format_str)
    console_handler.setFormatter(formatter)

    # Add filters to the handler
    console_handler.addFilter(ServiceNameFilter(service_name))
    console_handler.addFilter(TraceContextFilter())
    root_logger.addHandler(console_handler)

    # Suppress overly verbose third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    # gRPC logging integration
    if enable_grpc_logging:
        _setup_grpc_logging(service_name, numeric_log_level, formatter)

    logger = logging.getLogger(__name__)
    logger.info("Logging configured. Service: %s, Level: %s", service_name, log_level_str)


def _setup_grpc_logging(service_name: str, log_level: int, formatter: logging.Formatter) -> None:
    """Set up gRPC logging integration using proper dependency injection."""
    try:
        import marty_common.grpc_logging as grpc_logging_module

        from .grpc_logging import GrpcLogHandler

        # Check if the global instance needs to be created
        if grpc_logging_module.grpc_log_handler_instance is None:
            new_grpc_handler = GrpcLogHandler(service_name=service_name)
            new_grpc_handler.setLevel(log_level)
            new_grpc_handler.setFormatter(formatter)

            root_logger = logging.getLogger()
            root_logger.addHandler(new_grpc_handler)

            # Update the module-level instance using proper interface
            grpc_logging_module.grpc_log_handler_instance = new_grpc_handler

            logging.getLogger(__name__).info(
                "GrpcLogHandler initialized for service: %s", service_name
            )
        else:
            # Instance already exists, ensure it's properly configured
            existing_handler = grpc_logging_module.grpc_log_handler_instance
            existing_handler.setLevel(log_level)
            root_logger = logging.getLogger()
            if existing_handler not in root_logger.handlers:
                root_logger.addHandler(existing_handler)
            logging.getLogger(__name__).info("GrpcLogHandler reused for service integration")
    except ImportError:
        logging.getLogger(__name__).warning(
            "gRPC logging not available, skipping gRPC log handler setup"
        )


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Get a logger instance for the module.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name or __name__)
