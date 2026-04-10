"""
Centralized Logging Infrastructure for Marty Platform

Provides structured logging, log aggregation, and monitoring capabilities
across all Marty services with ELK stack integration.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import socket
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from opentelemetry import trace
from pythonjsonlogger import jsonlogger

# Global request context storage
_request_context: dict[str, Any] = {}


class MartyStructuredLogger:
    """
    Centralized structured logging configuration for Marty Platform.

    Features:
    - JSON structured logging
    - Contextual information (service, version, environment)
    - Request tracing
    - Performance metrics
    - ELK stack integration
    """

    def __init__(
        self,
        service_name: str,
        version: str = "1.0.0",
        environment: str = "development",
        log_level: str = "INFO",
        enable_console: bool = True,
        enable_file: bool = True,
        enable_syslog: bool = False,
        log_dir: str = "logs",
    ):
        self.service_name = service_name
        self.version = version
        self.environment = environment
        self.log_level = getattr(logging, log_level.upper())
        self.enable_console = enable_console
        self.enable_file = enable_file
        self.enable_syslog = enable_syslog
        self.log_dir = Path(log_dir)

        # Create logs directory
        self.log_dir.mkdir(exist_ok=True)

        # Get hostname and process info
        self.hostname = socket.gethostname()
        self.pid = os.getpid()

        # Initialize structured logging
        self._setup_structlog()
        self._setup_standard_logging()

    def _setup_structlog(self):
        """Configure structlog for structured logging."""

        # Custom processor to add service context
        def add_service_context(logger, method_name, event_dict):
            event_dict.update(
                {
                    "service": self.service_name,
                    "version": self.version,
                    "environment": self.environment,
                    "hostname": self.hostname,
                    "pid": self.pid,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            return event_dict

        # Custom processor for request tracing
        def add_request_context(logger, method_name, event_dict):
            # Add request context from global storage
            global _request_context
            if _request_context:
                event_dict.update(
                    {
                        "request_id": _request_context.get("request_id"),
                        "user_id": _request_context.get("user_id"),
                        "session_id": _request_context.get("session_id"),
                        "correlation_id": _request_context.get("correlation_id"),
                    }
                )
            return event_dict

        # Configure structlog
        structlog.configure(
            processors=[
                structlog.threadlocal.merge_contextvars,
                add_service_context,
                add_request_context,
                structlog.processors.TimeStamper(fmt="ISO"),
                structlog.processors.add_log_level,
                structlog.processors.StackInfoRenderer(),
                (
                    structlog.dev.ConsoleRenderer()
                    if self.environment == "development"
                    else structlog.processors.JSONRenderer()
                ),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(self.log_level),
            logger_factory=structlog.WriteLoggerFactory(),
            context_class=dict,
            cache_logger_on_first_use=True,
        )

    def _setup_standard_logging(self):
        """Configure standard Python logging with JSON formatting."""

        # Create custom JSON formatter
        class MartyJSONFormatter(jsonlogger.JsonFormatter):
            def add_fields(self, log_record, record, message_dict):
                super().add_fields(log_record, record, message_dict)

                # Add service context
                log_record["service"] = self.service_name
                log_record["version"] = self.version
                log_record["environment"] = self.environment
                log_record["hostname"] = self.hostname
                log_record["pid"] = self.pid

                # Add timestamp in ISO format
                if not log_record.get("timestamp"):
                    log_record["timestamp"] = datetime.now(timezone.utc).isoformat()

                # Add log level
                log_record["level"] = record.levelname
                log_record["logger"] = record.name

                # Add file and line info
                log_record["file"] = record.filename
                log_record["line"] = record.lineno
                log_record["function"] = record.funcName

                # Add request context if available
                global _request_context
                if _request_context:
                    log_record.update(
                        {
                            "request_id": _request_context.get("request_id"),
                            "user_id": _request_context.get("user_id"),
                            "session_id": _request_context.get("session_id"),
                            "correlation_id": _request_context.get("correlation_id"),
                        }
                    )

                # Add OpenTelemetry trace context if available
                current_span = trace.get_current_span()
                if current_span and current_span.is_recording():
                    span_context = current_span.get_span_context()
                    log_record["trace_id"] = format(span_context.trace_id, "032x")
                    log_record["span_id"] = format(span_context.span_id, "016x")

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)

        # Clear existing handlers
        root_logger.handlers.clear()

        # Console handler
        if self.enable_console:
            console_handler = logging.StreamHandler()
            if self.environment == "development":
                # Human-readable format for development
                console_formatter = logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
            else:
                # JSON format for production
                console_formatter = MartyJSONFormatter()
            console_handler.setFormatter(console_formatter)
            root_logger.addHandler(console_handler)

        # File handler
        if self.enable_file:
            file_handler = logging.handlers.RotatingFileHandler(
                self.log_dir / f"{self.service_name}.log",
                maxBytes=50 * 1024 * 1024,  # 50MB
                backupCount=10,
            )
            file_formatter = MartyJSONFormatter()
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)

        # Syslog handler for centralized logging
        if self.enable_syslog:
            try:
                syslog_handler = logging.handlers.SysLogHandler(
                    address=("localhost", 514), facility=logging.handlers.SysLogHandler.LOG_LOCAL0
                )
                syslog_formatter = MartyJSONFormatter()
                syslog_handler.setFormatter(syslog_formatter)
                root_logger.addHandler(syslog_handler)
            except (OSError, ConnectionError) as e:
                print(f"Failed to setup syslog handler: {e}")

    def get_logger(self, name: str | None = None) -> structlog.BoundLogger:
        """Get a structured logger instance."""
        logger_name = name or self.service_name
        return structlog.get_logger(logger_name)

    def set_request_context(self, **context):
        """Set request context for logging."""
        global _request_context
        _request_context.update(context)

    def clear_request_context(self):
        """Clear request context."""
        global _request_context
        _request_context.clear()

    @contextmanager
    def request_context(self, **context):
        """Context manager for request-scoped logging context."""
        self.set_request_context(**context)
        try:
            yield
        finally:
            self.clear_request_context()


class PerformanceLogger:
    """Logger for performance metrics and timing."""

    def __init__(self, logger: structlog.BoundLogger):
        self.logger = logger

    def log_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        response_time: float,
        request_size: int = 0,
        response_size: int = 0,
        **kwargs,
    ):
        """Log HTTP request performance metrics."""
        self.logger.info(
            "http_request",
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            response_time=response_time,
            request_size=request_size,
            response_size=response_size,
            **kwargs,
        )

    def log_database_query(
        self, query_type: str, table: str, execution_time: float, rows_affected: int = 0, **kwargs
    ):
        """Log database query performance."""
        self.logger.info(
            "database_query",
            query_type=query_type,
            table=table,
            execution_time=execution_time,
            rows_affected=rows_affected,
            **kwargs,
        )

    def log_external_api_call(
        self,
        service: str,
        endpoint: str,
        method: str,
        response_time: float,
        status_code: int,
        **kwargs,
    ):
        """Log external API call performance."""
        self.logger.info(
            "external_api_call",
            service=service,
            endpoint=endpoint,
            method=method,
            response_time=response_time,
            status_code=status_code,
            **kwargs,
        )


class SecurityLogger:
    """Logger for security events and audit trails."""

    def __init__(self, logger: structlog.BoundLogger):
        self.logger = logger

    def log_authentication(
        self,
        user_id: str,
        success: bool,
        method: str = "unknown",
        ip_address: str | None = None,
        user_agent: str | None = None,
        **kwargs,
    ):
        """Log authentication attempts."""
        self.logger.info(
            "authentication",
            user_id=user_id,
            success=success,
            method=method,
            ip_address=ip_address,
            user_agent=user_agent,
            event_type="security",
            **kwargs,
        )

    def log_authorization(self, user_id: str, resource: str, action: str, granted: bool, **kwargs):
        """Log authorization decisions."""
        self.logger.info(
            "authorization",
            user_id=user_id,
            resource=resource,
            action=action,
            granted=granted,
            event_type="security",
            **kwargs,
        )

    def log_security_event(self, event_type: str, severity: str, description: str, **kwargs):
        """Log general security events."""
        self.logger.warning(
            "security_event",
            event_type=event_type,
            severity=severity,
            description=description,
            **kwargs,
        )


class BusinessLogger:
    """Logger for business events and workflows."""

    def __init__(self, logger: structlog.BoundLogger):
        self.logger = logger

    def log_document_processed(
        self, document_id: str, document_type: str, processing_time: float, success: bool, **kwargs
    ):
        """Log document processing events."""
        self.logger.info(
            "document_processed",
            document_id=document_id,
            document_type=document_type,
            processing_time=processing_time,
            success=success,
            event_type="business",
            **kwargs,
        )

    def log_certificate_issued(
        self, certificate_id: str, certificate_type: str, issuer: str, subject: str, **kwargs
    ):
        """Log certificate issuance."""
        self.logger.info(
            "certificate_issued",
            certificate_id=certificate_id,
            certificate_type=certificate_type,
            issuer=issuer,
            subject=subject,
            event_type="business",
            **kwargs,
        )

    def log_verification_result(
        self,
        document_id: str,
        verification_type: str,
        result: str,
        confidence_score: float | None = None,
        **kwargs,
    ):
        """Log verification results."""
        self.logger.info(
            "verification_result",
            document_id=document_id,
            verification_type=verification_type,
            result=result,
            confidence_score=confidence_score,
            event_type="business",
            **kwargs,
        )


def setup_logging_for_service(service_name: str, **kwargs) -> MartyStructuredLogger:
    """
    Convenience function to set up logging for a Marty service.

    Args:
        service_name: Name of the service (e.g., 'pkd_service', 'document_processing')
        **kwargs: Additional configuration options

    Returns:
        Configured MartyStructuredLogger instance
    """
    # Get configuration from environment variables
    config = {
        "version": os.getenv("MARTY_VERSION", "1.0.0"),
        "environment": os.getenv("MARTY_ENVIRONMENT", "development"),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
        "enable_console": os.getenv("LOG_CONSOLE", "true").lower() == "true",
        "enable_file": os.getenv("LOG_FILE", "true").lower() == "true",
        "enable_syslog": os.getenv("LOG_SYSLOG", "false").lower() == "true",
        "log_dir": os.getenv("LOG_DIR", "logs"),
    }

    # Override with provided kwargs
    config.update(kwargs)

    return MartyStructuredLogger(service_name, **config)


# Logging middleware for FastAPI
class LoggingMiddleware:
    """FastAPI middleware for request/response logging."""

    def __init__(self, app, logger: structlog.BoundLogger):
        self.app = app
        self.logger = logger
        self.performance_logger = PerformanceLogger(logger)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract request info
        method = scope["method"]
        path = scope["path"]
        client_ip = scope.get("client", ["unknown"])[0]

        # Generate request ID
        request_id = f"{int(time.time() * 1000)}-{id(scope)}"

        # Set request context
        logging_instance = setup_logging_for_service("middleware")
        logging_instance.set_request_context(
            request_id=request_id, client_ip=client_ip, method=method, path=path
        )

        start_time = time.time()

        # Intercept response
        response_status = 500
        response_size = 0

        async def send_wrapper(message):
            nonlocal response_status, response_size
            if message["type"] == "http.response.start":
                response_status = message["status"]
            elif message["type"] == "http.response.body":
                if "body" in message:
                    response_size += len(message["body"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            self.logger.exception("request_error", error=str(e), error_type=type(e).__name__)
            raise
        finally:
            # Log request performance
            response_time = time.time() - start_time
            self.performance_logger.log_request(
                method=method,
                endpoint=path,
                status_code=response_status,
                response_time=response_time,
                response_size=response_size,
                client_ip=client_ip,
            )

            # Clear request context
            logging_instance.clear_request_context()


# Example usage functions
def example_usage():
    """Example of how to use the centralized logging system."""

    # Set up logging for a service
    logging_config = setup_logging_for_service("example_service")
    logger = logging_config.get_logger()

    # Create specialized loggers
    perf_logger = PerformanceLogger(logger)
    security_logger = SecurityLogger(logger)
    business_logger = BusinessLogger(logger)

    # Basic logging
    logger.info("Service started", port=8080, workers=4)
    logger.warning("High memory usage detected", memory_usage="85%")
    logger.error("Database connection failed", error="Connection timeout")

    # Performance logging
    perf_logger.log_request("GET", "/api/documents", 200, 0.145, response_size=1024)
    perf_logger.log_database_query("SELECT", "documents", 0.025, rows_affected=10)

    # Security logging
    security_logger.log_authentication("user123", True, "password", "192.168.1.1")
    security_logger.log_authorization("user123", "/api/admin", "read", False)

    # Business logging
    business_logger.log_document_processed("doc123", "passport", 2.5, True)
    business_logger.log_verification_result("doc123", "mrz", "valid", 0.98)

    # Using request context
    with logging_config.request_context(request_id="req-123", user_id="user456"):
        logger.info("Processing user request")
        business_logger.log_document_processed("doc456", "id_card", 1.8, True)


if __name__ == "__main__":
    example_usage()
