"""
Prometheus metrics server for Marty microservices.

This module provides a unified metrics collection and HTTP endpoint serving
system for all Marty gRPC microservices. It includes:
- Common metrics for all services (request/response rates, latencies, etc.)
- Health check endpoints for Kubernetes
- Proper error handling and graceful shutdown
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import uvicorn
from fastapi import FastAPI, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
    multiprocess,
    values,
)
from uvicorn.config import LOGGING_CONFIG

logger = logging.getLogger(__name__)


class ServiceMetrics:
    """Metrics collection for a single microservice."""

    def __init__(self, service_name: str, version: str = "1.0.0") -> None:
        self.service_name = service_name
        self.version = version

        # Service info
        self.service_info = Info("marty_service_info", "Service information", registry=None)
        self.service_info.info(
            {
                "service": service_name,
                "version": version,
            }
        )

        # Request metrics
        self.requests_total = Counter(
            "marty_grpc_requests_total",
            "Total gRPC requests",
            ["service", "method", "status"],
            registry=None,
        )

        self.request_duration = Histogram(
            "marty_grpc_request_duration_seconds",
            "gRPC request duration in seconds",
            ["service", "method"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            registry=None,
        )

        # Connection metrics
        self.active_connections = Gauge(
            "marty_grpc_active_connections",
            "Number of active gRPC connections",
            ["service"],
            registry=None,
        )

        # Error metrics
        self.errors_total = Counter(
            "marty_grpc_errors_total",
            "Total gRPC errors",
            ["service", "method", "error_type"],
            registry=None,
        )

        # Health metrics
        self.health_status = Gauge(
            "marty_service_health_status",
            "Service health status (1=healthy, 0=unhealthy)",
            ["service", "check"],
            registry=None,
        )

        # Resource metrics
        self.cpu_usage = Gauge(
            "marty_service_cpu_usage_percent", "CPU usage percentage", ["service"], registry=None
        )

        self.memory_usage = Gauge(
            "marty_service_memory_usage_bytes", "Memory usage in bytes", ["service"], registry=None
        )

        self.database_connections = Gauge(
            "marty_database_connections_active",
            "Active database connections",
            ["service", "database"],
            registry=None,
        )

        # Last successful operation timestamp
        self.last_successful_operation = Gauge(
            "marty_last_successful_operation_timestamp",
            "Timestamp of last successful operation",
            ["service", "operation"],
            registry=None,
        )

    def record_request(self, method: str, status: str, duration: float) -> None:
        """Record a gRPC request."""
        self.requests_total.labels(service=self.service_name, method=method, status=status).inc()

        self.request_duration.labels(service=self.service_name, method=method).observe(duration)

    def record_error(self, method: str, error_type: str) -> None:
        """Record a gRPC error."""
        self.errors_total.labels(
            service=self.service_name, method=method, error_type=error_type
        ).inc()

    def set_health_status(self, check_name: str, healthy: bool) -> None:
        """Set health status for a specific check."""
        self.health_status.labels(service=self.service_name, check=check_name).set(
            1.0 if healthy else 0.0
        )

    def set_active_connections(self, count: int) -> None:
        """Set number of active connections."""
        self.active_connections.labels(service=self.service_name).set(count)

    def set_cpu_usage(self, percentage: float) -> None:
        """Set CPU usage percentage."""
        self.cpu_usage.labels(service=self.service_name).set(percentage)

    def set_memory_usage(self, bytes_used: int) -> None:
        """Set memory usage in bytes."""
        self.memory_usage.labels(service=self.service_name).set(bytes_used)

    def set_database_connections(self, database: str, count: int) -> None:
        """Set active database connections."""
        self.database_connections.labels(service=self.service_name, database=database).set(count)

    def record_successful_operation(self, operation: str) -> None:
        """Record timestamp of successful operation."""
        self.last_successful_operation.labels(service=self.service_name, operation=operation).set(
            time.time()
        )


class BusinessMetrics:
    """Business-specific metrics for digital identity processing."""

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name

        # Document processing metrics
        self.document_verification_attempts = Counter(
            "marty_document_verification_attempts_total",
            "Total document verification attempts",
            ["service", "document_type"],
            registry=None,
        )

        self.document_verification_failures = Counter(
            "marty_document_verification_failures_total",
            "Total document verification failures",
            ["service", "document_type", "failure_reason"],
            registry=None,
        )

        self.document_processing_duration = Histogram(
            "marty_document_processing_duration_seconds",
            "Document processing time in seconds",
            ["service", "document_type", "operation"],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
            registry=None,
        )

        # Certificate metrics
        self.certificate_validation_attempts = Counter(
            "marty_certificate_validation_attempts_total",
            "Total certificate validation attempts",
            ["service", "certificate_type"],
            registry=None,
        )

        self.certificate_validation_errors = Counter(
            "marty_certificate_validation_errors_total",
            "Total certificate validation errors",
            ["service", "certificate_type", "error_type"],
            registry=None,
        )

        self.certificates_expiring_soon = Gauge(
            "marty_certificates_expiring_soon",
            "Number of certificates expiring within 30 days",
            ["service", "certificate_type"],
            registry=None,
        )

        self.revoked_certificate_usage = Counter(
            "marty_revoked_certificate_usage_total",
            "Attempts to use revoked certificates",
            ["service", "certificate_type"],
            registry=None,
        )

        # PKD/Trust store metrics
        self.pkd_sync_attempts = Counter(
            "marty_pkd_sync_attempts_total",
            "Total PKD synchronization attempts",
            ["service", "source"],
            registry=None,
        )

        self.pkd_sync_failures = Counter(
            "marty_pkd_sync_failures_total",
            "Total PKD synchronization failures",
            ["service", "source", "failure_reason"],
            registry=None,
        )

        self.trust_store_entries = Gauge(
            "marty_trust_store_entries_total",
            "Total entries in trust store",
            ["service", "entry_type"],
            registry=None,
        )

        # Biometric processing metrics
        self.biometric_template_processing = Counter(
            "marty_biometric_template_processing_total",
            "Total biometric template processing operations",
            ["service", "biometric_type", "operation"],
            registry=None,
        )

        self.biometric_match_attempts = Counter(
            "marty_biometric_match_attempts_total",
            "Total biometric matching attempts",
            ["service", "biometric_type"],
            registry=None,
        )

        self.biometric_match_scores = Histogram(
            "marty_biometric_match_scores",
            "Biometric matching scores",
            ["service", "biometric_type"],
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99],
            registry=None,
        )

        # RFID/Chip operations
        self.rfid_read_attempts = Counter(
            "marty_rfid_read_attempts_total",
            "Total RFID/chip read attempts",
            ["service", "chip_type"],
            registry=None,
        )

        self.rfid_read_failures = Counter(
            "marty_rfid_read_failures_total",
            "Total RFID/chip read failures",
            ["service", "chip_type", "failure_reason"],
            registry=None,
        )

        # Queue/Processing metrics
        self.processing_queue_size = Gauge(
            "marty_processing_queue_size",
            "Current size of processing queue",
            ["service", "queue_type"],
            registry=None,
        )

        self.dead_letter_queue_size = Gauge(
            "marty_dead_letter_queue_size",
            "Current size of dead letter queue",
            ["service", "queue_type"],
            registry=None,
        )

    def record_document_verification(
        self, document_type: str, success: bool, duration: float, failure_reason: str | None = None
    ) -> None:
        """Record document verification attempt."""
        self.document_verification_attempts.labels(
            service=self.service_name, document_type=document_type
        ).inc()

        if not success and failure_reason:
            self.document_verification_failures.labels(
                service=self.service_name,
                document_type=document_type,
                failure_reason=failure_reason,
            ).inc()

        self.document_processing_duration.labels(
            service=self.service_name, document_type=document_type, operation="verification"
        ).observe(duration)

    def record_certificate_validation(
        self, certificate_type: str, success: bool, error_type: str | None = None
    ) -> None:
        """Record certificate validation attempt."""
        self.certificate_validation_attempts.labels(
            service=self.service_name, certificate_type=certificate_type
        ).inc()

        if not success and error_type:
            self.certificate_validation_errors.labels(
                service=self.service_name, certificate_type=certificate_type, error_type=error_type
            ).inc()

    def record_pkd_sync(
        self, source: str, success: bool, failure_reason: str | None = None
    ) -> None:
        """Record PKD synchronization attempt."""
        self.pkd_sync_attempts.labels(service=self.service_name, source=source).inc()

        if not success and failure_reason:
            self.pkd_sync_failures.labels(
                service=self.service_name, source=source, failure_reason=failure_reason
            ).inc()

    def record_biometric_operation(
        self, biometric_type: str, operation: str, match_score: float | None = None
    ) -> None:
        """Record biometric processing operation."""
        self.biometric_template_processing.labels(
            service=self.service_name, biometric_type=biometric_type, operation=operation
        ).inc()

        if operation == "match" and match_score is not None:
            self.biometric_match_attempts.labels(
                service=self.service_name, biometric_type=biometric_type
            ).inc()

            self.biometric_match_scores.labels(
                service=self.service_name, biometric_type=biometric_type
            ).observe(match_score)

    def record_rfid_operation(
        self, chip_type: str, success: bool, failure_reason: str | None = None
    ) -> None:
        """Record RFID/chip operation."""
        self.rfid_read_attempts.labels(service=self.service_name, chip_type=chip_type).inc()

        if not success and failure_reason:
            self.rfid_read_failures.labels(
                service=self.service_name, chip_type=chip_type, failure_reason=failure_reason
            ).inc()

    def set_queue_size(self, queue_type: str, size: int, is_dlq: bool = False) -> None:
        """Set current queue size."""
        if is_dlq:
            self.dead_letter_queue_size.labels(
                service=self.service_name, queue_type=queue_type
            ).set(size)
        else:
            self.processing_queue_size.labels(service=self.service_name, queue_type=queue_type).set(
                size
            )

    def set_certificates_expiring(self, certificate_type: str, count: int) -> None:
        """Set number of certificates expiring soon."""
        self.certificates_expiring_soon.labels(
            service=self.service_name, certificate_type=certificate_type
        ).set(count)

    def set_trust_store_entries(self, entry_type: str, count: int) -> None:
        """Set number of trust store entries."""
        self.trust_store_entries.labels(service=self.service_name, entry_type=entry_type).set(count)

    def record_revoked_certificate_usage(self, certificate_type: str) -> None:
        """Record attempt to use revoked certificate."""
        self.revoked_certificate_usage.labels(
            service=self.service_name, certificate_type=certificate_type
        ).inc()


class HealthChecker:
    """Advanced health checker for service readiness and liveness."""

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        self.checks: dict[str, bool] = {}
        self.startup_time = time.time()
        self.dependency_checks: dict[str, Callable[[], bool]] = {}

    def add_check(self, name: str, healthy: bool) -> None:
        """Add or update a health check."""
        self.checks[name] = healthy

    def add_dependency_check(self, name: str, check_func: Callable[[], bool]) -> None:
        """Add a dependency health check function."""
        self.dependency_checks[name] = check_func

    def run_dependency_checks(self) -> None:
        """Run all dependency checks and update health status."""
        for name, check_func in self.dependency_checks.items():
            try:
                is_healthy = check_func()
                self.add_check(name, is_healthy)
            except Exception as e:
                logger.warning(f"Dependency check '{name}' failed: {e}")
                self.add_check(name, False)

    def is_healthy(self) -> bool:
        """Check if service is healthy (all checks pass)."""
        # Run dependency checks first
        self.run_dependency_checks()

        if not self.checks:
            return True  # No checks means healthy by default
        return all(self.checks.values())

    def is_ready(self) -> bool:
        """Check if service is ready (same as healthy for most services)."""
        return self.is_healthy()

    def is_live(self) -> bool:
        """Check if service is alive (basic liveness check)."""
        # Service is live if it's been running for at least 5 seconds
        return time.time() - self.startup_time > 5

    def get_status(self) -> dict[str, Any]:
        """Get detailed health status."""
        return {
            "service": self.service_name,
            "healthy": self.is_healthy(),
            "ready": self.is_ready(),
            "live": self.is_live(),
            "uptime_seconds": int(time.time() - self.startup_time),
            "checks": self.checks.copy(),
            "timestamp": time.time(),
        }


class MetricsServer:
    """HTTP server for Prometheus metrics and health checks."""

    def __init__(
        self,
        service_name: str,
        version: str = "1.0.0",
        host: str = "0.0.0.0",
        port: int = 8080,
    ) -> None:
        self.service_name = service_name
        self.version = version
        self.host = host
        self.port = port

        self.metrics = ServiceMetrics(service_name, version)
        self.business_metrics = BusinessMetrics(service_name)
        self.health = HealthChecker(service_name)

        # FastAPI app for metrics and health endpoints
        self.app = FastAPI(
            title=f"{service_name} Metrics",
            description=f"Prometheus metrics and health endpoints for {service_name}",
            version=version,
        )

        self._setup_routes()
        self._running = False
        self._server_task: asyncio.Task | None = None

    def _setup_routes(self) -> None:
        """Setup HTTP routes for metrics and health checks."""

        @self.app.get("/metrics")
        async def metrics_endpoint() -> Response:
            """Prometheus metrics endpoint."""
            registry = None
            if values.ValueClass._multiproc_file_prefix:
                registry = CollectorRegistry()
                multiprocess.MultiProcessCollector(registry)

            metrics_data = generate_latest(registry)
            return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)

        @self.app.get("/health")
        async def health_endpoint() -> dict[str, Any]:
            """General health endpoint."""
            return self.health.get_status()

        @self.app.get("/health/live")
        async def liveness_endpoint() -> dict[str, Any]:
            """Kubernetes liveness probe endpoint."""
            return {
                "status": "alive" if self.health.is_live() else "not_alive",
                "service": self.service_name,
                "timestamp": time.time(),
            }

        @self.app.get("/health/ready")
        async def readiness_endpoint() -> dict[str, Any]:
            """Kubernetes readiness probe endpoint."""
            return {
                "status": "ready" if self.health.is_ready() else "not_ready",
                "service": self.service_name,
                "checks": self.health.checks.copy(),
                "timestamp": time.time(),
            }

        @self.app.get("/")
        async def root_endpoint() -> dict[str, Any]:
            """Root endpoint."""
            return {
                "service": self.service_name,
                "version": self.version,
                "endpoints": {
                    "metrics": "/metrics",
                    "health": "/health",
                    "liveness": "/health/live",
                    "readiness": "/health/ready",
                },
            }

    async def start(self) -> None:
        """Start the metrics server."""
        if self._running:
            logger.warning("Metrics server already running")
            return

        logger.info(f"Starting metrics server for {self.service_name} on {self.host}:{self.port}")

        # Configure uvicorn to be less verbose
        log_config = LOGGING_CONFIG.copy()
        log_config["loggers"]["uvicorn"]["level"] = "WARNING"
        log_config["loggers"]["uvicorn.access"]["level"] = "WARNING"

        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_config=log_config,
            access_log=False,
        )

        server = uvicorn.Server(config)
        self._server_task = asyncio.create_task(server.serve())
        self._running = True

        # Give the server a moment to start
        await asyncio.sleep(0.1)
        logger.info(f"Metrics server started at http://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the metrics server."""
        if not self._running:
            return

        logger.info(f"Stopping metrics server for {self.service_name}")

        if self._server_task:
            self._server_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._server_task
            self._server_task = None

        self._running = False
        logger.info("Metrics server stopped")

    def start_in_thread(self) -> threading.Thread:
        """Start the metrics server in a separate thread (for use with sync gRPC)."""

        def run_server():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.start())
                loop.run_forever()
            finally:
                loop.close()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

        # Wait a moment for the server to start
        time.sleep(0.2)

        return thread


# Global metrics server instance (can be imported and used)
_metrics_server: MetricsServer | None = None


def get_metrics_server() -> MetricsServer | None:
    """Get the global metrics server instance."""
    return _metrics_server


def init_metrics_server(
    service_name: str,
    version: str = "1.0.0",
    host: str = "0.0.0.0",
    port: int = 8080,
) -> MetricsServer:
    """Initialize the global metrics server."""
    global _metrics_server
    _metrics_server = MetricsServer(service_name, version, host, port)
    return _metrics_server


async def start_metrics_server(
    service_name: str,
    version: str = "1.0.0",
    host: str = "0.0.0.0",
    port: int = 8080,
) -> MetricsServer:
    """Initialize and start the metrics server."""
    server = init_metrics_server(service_name, version, host, port)
    await server.start()
    return server


def start_metrics_server_sync(
    service_name: str,
    version: str = "1.0.0",
    host: str = "0.0.0.0",
    port: int = 8080,
) -> MetricsServer:
    """Initialize and start the metrics server in a thread (for sync gRPC services)."""
    server = init_metrics_server(service_name, version, host, port)
    server.start_in_thread()
    return server
