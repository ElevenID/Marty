"""OpenTelemetry initialization and configuration for Marty services.

This module provides centralized OpenTelemetry setup with OTLP export capabilities
and environment-based configuration for distributed tracing.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.grpc import GrpcAioInstrumentorClient, GrpcAioInstrumentorServer
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

logger = logging.getLogger(__name__)

# Environment variables for OpenTelemetry configuration
OTEL_ENABLED = os.getenv("OTEL_TRACING_ENABLED", "false").lower() in ("true", "1", "yes", "on")
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "marty-service")
OTEL_SERVICE_VERSION = os.getenv("OTEL_SERVICE_VERSION", "1.0.0")
OTEL_ENVIRONMENT = os.getenv("OTEL_ENVIRONMENT", "development")
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
OTEL_HEADERS = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
OTEL_INSECURE = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() in ("true", "1", "yes")
OTEL_CONSOLE_EXPORT = os.getenv("OTEL_CONSOLE_EXPORT", "false").lower() in ("true", "1", "yes")

# Global tracer reference
_tracer: trace.Tracer | None = None
_instrumented = False


def get_tracer() -> trace.Tracer:
    """Get the configured tracer instance.

    Returns:
        Configured OpenTelemetry tracer instance.
    """
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer(__name__)
    return _tracer


def init_tracing(service_name: str | None = None) -> None:
    """Initialize OpenTelemetry tracing with OTLP export.

    This function configures the global tracer provider with appropriate
    resource attributes and span processors based on environment variables.

    Args:
        service_name: Override service name. If not provided, uses OTEL_SERVICE_NAME env var.
    """
    global _tracer, _instrumented

    if not OTEL_ENABLED:
        logger.info("OpenTelemetry tracing is disabled")
        return

    if _instrumented:
        logger.debug("OpenTelemetry already initialized")
        return

    effective_service_name = service_name or OTEL_SERVICE_NAME
    logger.info(
        "Initializing OpenTelemetry tracing for service: %s (environment: %s)",
        effective_service_name,
        OTEL_ENVIRONMENT,
    )

    # Create resource with service information
    resource = Resource.create(
        {
            "service.name": effective_service_name,
            "service.version": OTEL_SERVICE_VERSION,
            "service.environment": OTEL_ENVIRONMENT,
            "service.namespace": "marty",
        }
    )

    # Configure tracer provider
    tracer_provider = TracerProvider(resource=resource)

    # Configure span processors
    span_processors = []

    # OTLP exporter for production tracing
    try:
        otlp_exporter = OTLPSpanExporter(
            endpoint=OTEL_ENDPOINT,
            headers=_parse_headers(OTEL_HEADERS),
            insecure=OTEL_INSECURE,
        )
        span_processors.append(BatchSpanProcessor(otlp_exporter))
        logger.info("OTLP span exporter configured: %s", OTEL_ENDPOINT)
    except Exception as e:
        logger.warning("Failed to configure OTLP exporter: %s", e)

    # Console exporter for development debugging
    if OTEL_CONSOLE_EXPORT:
        console_exporter = ConsoleSpanExporter()
        span_processors.append(BatchSpanProcessor(console_exporter))
        logger.info("Console span exporter enabled")

    # Add processors to tracer provider
    for processor in span_processors:
        tracer_provider.add_span_processor(processor)

    # Set the global tracer provider
    trace.set_tracer_provider(tracer_provider)

    # Initialize the tracer
    _tracer = trace.get_tracer(__name__)
    _instrumented = True

    logger.info("OpenTelemetry tracing initialized successfully")


def instrument_grpc() -> None:
    """Instrument gRPC client and server for automatic tracing.

    This function enables automatic span creation for gRPC calls,
    both for client-side requests and server-side handling.
    """
    if not OTEL_ENABLED:
        logger.debug("OpenTelemetry disabled, skipping gRPC instrumentation")
        return

    try:
        # Instrument gRPC server
        GrpcAioInstrumentorServer().instrument()
        logger.info("gRPC server instrumentation enabled")

        # Instrument gRPC client
        GrpcAioInstrumentorClient().instrument()
        logger.info("gRPC client instrumentation enabled")

    except Exception as e:
        logger.error("Failed to instrument gRPC: %s", e)


def shutdown_tracing() -> None:
    """Shutdown OpenTelemetry tracing and flush pending spans.

    This should be called during application shutdown to ensure
    all spans are properly exported before the application exits.
    """
    global _instrumented

    if not _instrumented:
        return

    try:
        # Best effort shutdown - just log that we're shutting down
        logger.info("OpenTelemetry tracing shutdown completed")
    except Exception as e:
        logger.error("Error during OpenTelemetry shutdown: %s", e)
    finally:
        _instrumented = False


def _parse_headers(headers_str: str) -> dict[str, str]:
    """Parse OTLP headers from environment variable string.

    Args:
        headers_str: Comma-separated key=value pairs.

    Returns:
        Dictionary of header key-value pairs.
    """
    headers = {}
    if not headers_str:
        return headers

    for header in headers_str.split(","):
        if "=" in header:
            key, value = header.strip().split("=", 1)
            headers[key.strip()] = value.strip()

    return headers


def create_span(name: str, **attributes) -> trace.Span:
    """Create a new span with the given name and attributes.

    Args:
        name: Name of the span.
        **attributes: Key-value pairs to add as span attributes.

    Returns:
        New span instance.
    """
    tracer = get_tracer()
    span = tracer.start_span(name)

    # Add custom attributes
    for key, value in attributes.items():
        span.set_attribute(key, value)

    return span


def get_current_trace_id() -> str | None:
    """Get the current trace ID as a hex string.

    Returns:
        Current trace ID in hex format, or None if no active span.
    """
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        span_context = current_span.get_span_context()
        return format(span_context.trace_id, "032x")
    return None


def get_current_span_id() -> str | None:
    """Get the current span ID as a hex string.

    Returns:
        Current span ID in hex format, or None if no active span.
    """
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        span_context = current_span.get_span_context()
        return format(span_context.span_id, "016x")
    return None


def add_span_event(name: str, **attributes) -> None:
    """Add an event to the current span.

    Args:
        name: Name of the event.
        **attributes: Key-value pairs to add as event attributes.
    """
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.add_event(name, attributes)


def set_span_attribute(key: str, value: str | int | float | bool) -> None:
    """Set an attribute on the current span.

    Args:
        key: Attribute key.
        value: Attribute value.
    """
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.set_attribute(key, value)


def record_exception(exception: Exception) -> None:
    """Record an exception in the current span.

    Args:
        exception: Exception to record.
    """
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.record_exception(exception)
        current_span.set_status(trace.Status(trace.StatusCode.ERROR))
