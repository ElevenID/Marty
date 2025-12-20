"""
Comprehensive health monitoring system for Marty services.

Provides health checks, metrics collection, alerting, and monitoring
dashboard capabilities for all Marty microservices.
"""

from __future__ import annotations

import json
import logging
import statistics
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    name: str
    status: HealthStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class Metric:
    """A single metric measurement."""

    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    unit: str = ""


@dataclass
class Alert:
    """An alert notification."""

    id: str
    severity: AlertSeverity
    title: str
    message: str
    service_name: str
    metric_name: str = ""
    threshold_value: float = 0.0
    current_value: float = 0.0
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False


class HealthCheck(ABC):
    """Abstract base class for health checks."""

    def __init__(self, name: str, timeout: float = 5.0) -> None:
        self.name = name
        self.timeout = timeout

    @abstractmethod
    def check(self) -> HealthCheckResult:
        """Perform the health check."""


class DatabaseHealthCheck(HealthCheck):
    """Health check for database connectivity."""

    def __init__(self, db_connector, name: str = "database") -> None:
        super().__init__(name)
        self.db_connector = db_connector

    def check(self) -> HealthCheckResult:
        start_time = time.time()
        try:
            # Simple query to test connectivity
            self.db_connector.execute("SELECT 1")
            duration = (time.time() - start_time) * 1000

            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.HEALTHY,
                message="Database connection successful",
                details={"response_time_ms": duration},
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection failed: {e!s}",
                details={"error": str(e)},
                duration_ms=duration,
            )


class ServiceHealthCheck(HealthCheck):
    """Health check for external service connectivity."""

    def __init__(self, service_url: str, name: str, expected_status: int = 200) -> None:
        super().__init__(name)
        self.service_url = service_url
        self.expected_status = expected_status

    def check(self) -> HealthCheckResult:
        import requests

        start_time = time.time()
        try:
            response = requests.get(f"{self.service_url}/health", timeout=self.timeout)
            duration = (time.time() - start_time) * 1000

            if response.status_code == self.expected_status:
                return HealthCheckResult(
                    name=self.name,
                    status=HealthStatus.HEALTHY,
                    message=f"Service {self.name} is healthy",
                    details={"status_code": response.status_code, "response_time_ms": duration},
                    duration_ms=duration,
                )
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.DEGRADED,
                message=f"Service returned unexpected status: {response.status_code}",
                details={"status_code": response.status_code},
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Service {self.name} unreachable: {e!s}",
                details={"error": str(e)},
                duration_ms=duration,
            )


class ResourceHealthCheck(HealthCheck):
    """Health check for system resources."""

    def __init__(self, name: str = "resources") -> None:
        super().__init__(name)

    def check(self) -> HealthCheckResult:
        import psutil

        start_time = time.time()
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            duration = (time.time() - start_time) * 1000

            # Determine status based on resource usage
            status = HealthStatus.HEALTHY
            messages = []

            if cpu_percent > 90:
                status = HealthStatus.UNHEALTHY
                messages.append(f"High CPU usage: {cpu_percent}%")
            elif cpu_percent > 75:
                status = HealthStatus.DEGRADED
                messages.append(f"Elevated CPU usage: {cpu_percent}%")

            if memory.percent > 90:
                status = HealthStatus.UNHEALTHY
                messages.append(f"High memory usage: {memory.percent}%")
            elif memory.percent > 75:
                status = HealthStatus.DEGRADED
                messages.append(f"Elevated memory usage: {memory.percent}%")

            if disk.percent > 90:
                status = HealthStatus.UNHEALTHY
                messages.append(f"High disk usage: {disk.percent}%")
            elif disk.percent > 80:
                status = HealthStatus.DEGRADED
                messages.append(f"Elevated disk usage: {disk.percent}%")

            message = "; ".join(messages) if messages else "All resources within normal limits"

            return HealthCheckResult(
                name=self.name,
                status=status,
                message=message,
                details={
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_available_gb": memory.available / (1024**3),
                    "disk_percent": disk.percent,
                    "disk_free_gb": disk.free / (1024**3),
                },
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNKNOWN,
                message=f"Failed to check resources: {e!s}",
                details={"error": str(e)},
                duration_ms=duration,
            )


class MetricsCollector:
    """Collects and stores metrics."""

    def __init__(self, max_datapoints: int = 1000) -> None:
        self.max_datapoints = max_datapoints
        self._metrics: dict[str, deque] = defaultdict(lambda: deque(maxlen=max_datapoints))
        self._lock = threading.RLock()

    def record_metric(self, metric: Metric) -> None:
        """Record a metric value."""
        with self._lock:
            metric_key = f"{metric.name}:{json.dumps(metric.labels, sort_keys=True)}"
            self._metrics[metric_key].append(metric)

    def get_metric_history(
        self, name: str, labels: dict[str, str] | None = None, since: float | None = None
    ) -> list[Metric]:
        """Get metric history."""
        with self._lock:
            labels = labels or {}
            metric_key = f"{name}:{json.dumps(labels, sort_keys=True)}"

            metrics = list(self._metrics.get(metric_key, []))
            if since:
                metrics = [m for m in metrics if m.timestamp >= since]

            return metrics

    def get_current_value(self, name: str, labels: dict[str, str] | None = None) -> float | None:
        """Get the most recent value for a metric."""
        history = self.get_metric_history(name, labels)
        return history[-1].value if history else None

    def get_statistics(
        self, name: str, labels: dict[str, str] | None = None, since: float | None = None
    ) -> dict[str, float]:
        """Get statistical summary of a metric."""
        history = self.get_metric_history(name, labels, since)
        if not history:
            return {}

        values = [m.value for m in history]
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "stddev": statistics.stdev(values) if len(values) > 1 else 0.0,
        }


class AlertManager:
    """Manages alerts and notifications."""

    def __init__(self) -> None:
        self._alerts: dict[str, Alert] = {}
        self._alert_handlers: list[Callable[[Alert], None]] = []
        self._lock = threading.RLock()

    def add_alert_handler(self, handler: Callable[[Alert], None]) -> None:
        """Add an alert handler."""
        with self._lock:
            self._alert_handlers.append(handler)

    def raise_alert(self, alert: Alert) -> None:
        """Raise a new alert."""
        with self._lock:
            existing = self._alerts.get(alert.id)
            if existing and existing.acknowledged:
                return  # Don't re-raise acknowledged alerts

            self._alerts[alert.id] = alert

            # Notify handlers
            for handler in self._alert_handlers:
                try:
                    handler(alert)
                except Exception:
                    logger.exception("Alert handler failed")

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        with self._lock:
            if alert_id in self._alerts:
                self._alerts[alert_id].acknowledged = True
                return True
            return False

    def get_active_alerts(self) -> list[Alert]:
        """Get all active (unacknowledged) alerts."""
        with self._lock:
            return [alert for alert in self._alerts.values() if not alert.acknowledged]

    def clear_old_alerts(self, max_age_seconds: float = 86400) -> None:
        """Clear old alerts."""
        cutoff_time = time.time() - max_age_seconds
        with self._lock:
            to_remove = [
                alert_id
                for alert_id, alert in self._alerts.items()
                if alert.timestamp < cutoff_time and alert.acknowledged
            ]
            for alert_id in to_remove:
                del self._alerts[alert_id]


class HealthMonitor:
    """Main health monitoring service."""

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        self.health_checks: list[HealthCheck] = []
        self.metrics_collector = MetricsCollector()
        self.alert_manager = AlertManager()
        self._running = False
        self._check_interval = 30.0  # seconds
        self._monitor_thread: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(max_workers=10)

    def add_health_check(self, health_check: HealthCheck) -> None:
        """Add a health check."""
        self.health_checks.append(health_check)

    def start(self, check_interval: float = 30.0) -> None:
        """Start the health monitoring service."""
        self._check_interval = check_interval
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info(f"Health monitor started for {self.service_name}")

    def stop(self) -> None:
        """Stop the health monitoring service."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        self._executor.shutdown(wait=True)
        logger.info(f"Health monitor stopped for {self.service_name}")

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                self._run_health_checks()
                self._collect_system_metrics()
                self._check_alert_conditions()
                time.sleep(self._check_interval)
            except Exception:
                logger.exception("Error in monitoring loop")
                time.sleep(5.0)  # Brief pause before retry

    def _run_health_checks(self) -> None:
        """Run all health checks."""
        futures = []
        for check in self.health_checks:
            future = self._executor.submit(self._run_single_check, check)
            futures.append(future)

        # Wait for all checks to complete
        for future in futures:
            try:
                result = future.result(timeout=30.0)
                # Record health check metrics
                self.metrics_collector.record_metric(
                    Metric(
                        name="health_check_duration_ms",
                        value=result.duration_ms,
                        labels={"check_name": result.name},
                    )
                )
                self.metrics_collector.record_metric(
                    Metric(
                        name="health_check_status",
                        value=1 if result.status == HealthStatus.HEALTHY else 0,
                        labels={"check_name": result.name, "status": result.status.value},
                    )
                )
            except Exception:
                logger.exception("Health check failed")

    def _run_single_check(self, check: HealthCheck) -> HealthCheckResult:
        """Run a single health check with timeout."""
        try:
            return check.check()
        except Exception as e:
            return HealthCheckResult(
                name=check.name,
                status=HealthStatus.UNKNOWN,
                message=f"Health check exception: {e!s}",
                details={"error": str(e)},
            )

    def _collect_system_metrics(self) -> None:
        """Collect system-level metrics."""
        try:
            import psutil

            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            self.metrics_collector.record_metric(
                Metric(
                    name="cpu_usage_percent",
                    value=cpu_percent,
                    labels={"service": self.service_name},
                )
            )

            # Memory metrics
            memory = psutil.virtual_memory()
            self.metrics_collector.record_metric(
                Metric(
                    name="memory_usage_percent",
                    value=memory.percent,
                    labels={"service": self.service_name},
                )
            )
            self.metrics_collector.record_metric(
                Metric(
                    name="memory_available_bytes",
                    value=memory.available,
                    labels={"service": self.service_name},
                )
            )

            # Disk metrics
            disk = psutil.disk_usage("/")
            self.metrics_collector.record_metric(
                Metric(
                    name="disk_usage_percent",
                    value=disk.percent,
                    labels={"service": self.service_name},
                )
            )

        except Exception:
            logger.exception("Failed to collect system metrics")

    def _check_alert_conditions(self) -> None:
        """Check for alert conditions."""
        # CPU usage alert
        cpu_usage = self.metrics_collector.get_current_value("cpu_usage_percent")
        if cpu_usage and cpu_usage > 90:
            alert = Alert(
                id=f"{self.service_name}_high_cpu",
                severity=AlertSeverity.CRITICAL,
                title="High CPU Usage",
                message=f"CPU usage is {cpu_usage:.1f}%",
                service_name=self.service_name,
                metric_name="cpu_usage_percent",
                current_value=cpu_usage,
                threshold_value=90.0,
            )
            self.alert_manager.raise_alert(alert)

        # Memory usage alert
        memory_usage = self.metrics_collector.get_current_value("memory_usage_percent")
        if memory_usage and memory_usage > 90:
            alert = Alert(
                id=f"{self.service_name}_high_memory",
                severity=AlertSeverity.CRITICAL,
                title="High Memory Usage",
                message=f"Memory usage is {memory_usage:.1f}%",
                service_name=self.service_name,
                metric_name="memory_usage_percent",
                current_value=memory_usage,
                threshold_value=90.0,
            )
            self.alert_manager.raise_alert(alert)

    def get_service_health(self) -> dict[str, Any]:
        """Get overall service health status."""
        health_results = []
        for check in self.health_checks:
            try:
                result = check.check()
                health_results.append(result)
            except Exception as e:
                health_results.append(
                    HealthCheckResult(
                        name=check.name, status=HealthStatus.UNKNOWN, message=f"Check failed: {e!s}"
                    )
                )

        # Determine overall status
        if not health_results:
            overall_status = HealthStatus.UNKNOWN
        elif any(r.status == HealthStatus.UNHEALTHY for r in health_results):
            overall_status = HealthStatus.UNHEALTHY
        elif any(r.status == HealthStatus.DEGRADED for r in health_results):
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        return {
            "service": self.service_name,
            "status": overall_status.value,
            "timestamp": time.time(),
            "checks": [
                {
                    "name": r.name,
                    "status": r.status.value,
                    "message": r.message,
                    "duration_ms": r.duration_ms,
                    "details": r.details,
                }
                for r in health_results
            ],
            "active_alerts": len(self.alert_manager.get_active_alerts()),
        }

    def get_metrics_summary(self, since_minutes: int = 60) -> dict[str, Any]:
        """Get metrics summary for the service."""
        since_timestamp = time.time() - (since_minutes * 60)

        metrics = {
            "cpu_usage": self.metrics_collector.get_statistics(
                "cpu_usage_percent", {"service": self.service_name}, since_timestamp
            ),
            "memory_usage": self.metrics_collector.get_statistics(
                "memory_usage_percent", {"service": self.service_name}, since_timestamp
            ),
            "disk_usage": self.metrics_collector.get_statistics(
                "disk_usage_percent", {"service": self.service_name}, since_timestamp
            ),
        }

        return {
            "service": self.service_name,
            "period_minutes": since_minutes,
            "metrics": metrics,
            "timestamp": time.time(),
        }


def create_default_monitor(service_name: str, db_connector=None) -> HealthMonitor:
    """Create a health monitor with standard checks."""
    monitor = HealthMonitor(service_name)

    # Add resource check
    monitor.add_health_check(ResourceHealthCheck())

    # Add database check if connector provided
    if db_connector:
        monitor.add_health_check(DatabaseHealthCheck(db_connector))

    return monitor
