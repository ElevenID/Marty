"""
Service health monitoring and metrics collection infrastructure for Marty services.

Provides comprehensive monitoring capabilities including health checks, metrics collection,
centralized logging, and alerting for all microservices in the Marty architecture.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import grpc
import psutil


class HealthStatus(Enum):
    """Service health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class MetricType(Enum):
    """Types of metrics."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class HealthCheck:
    """Health check definition."""

    name: str
    description: str
    check_function: Callable[[], bool]
    timeout_seconds: float = 5.0
    critical: bool = True  # If False, failure won't mark service as unhealthy
    interval_seconds: float = 30.0
    last_check: datetime | None = None
    last_result: bool | None = None
    last_error: str | None = None


@dataclass
class Metric:
    """Metric data point."""

    name: str
    metric_type: MetricType
    value: int | float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    help_text: str = ""


@dataclass
class ServiceInfo:
    """Service information for monitoring."""

    service_name: str
    service_version: str
    instance_id: str
    host: str
    port: int
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class Alert:
    """Alert definition and state."""

    alert_id: str
    name: str
    description: str
    severity: AlertSeverity
    condition: Callable[[dict[str, Any]], bool]
    triggered_at: datetime | None = None
    resolved_at: datetime | None = None
    is_active: bool = False
    cooldown_seconds: float = 300.0  # 5 minutes
    last_triggered: datetime | None = None


class MetricsCollector:
    """Collects and manages metrics."""

    def __init__(self) -> None:
        self.metrics: dict[str, list[Metric]] = defaultdict(list)
        self.metric_definitions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

        # Built-in metrics
        self._register_system_metrics()

    def _register_system_metrics(self) -> None:
        """Register built-in system metrics."""
        self.register_metric("system.cpu.percent", MetricType.GAUGE, "CPU usage percentage")
        self.register_metric("system.memory.percent", MetricType.GAUGE, "Memory usage percentage")
        self.register_metric("system.disk.percent", MetricType.GAUGE, "Disk usage percentage")
        self.register_metric("grpc.requests.total", MetricType.COUNTER, "Total gRPC requests")
        self.register_metric(
            "grpc.requests.duration", MetricType.HISTOGRAM, "gRPC request duration"
        )
        self.register_metric("grpc.errors.total", MetricType.COUNTER, "Total gRPC errors")

    def register_metric(self, name: str, metric_type: MetricType, help_text: str = "") -> None:
        """Register a metric definition."""
        with self._lock:
            self.metric_definitions[name] = {
                "type": metric_type,
                "help": help_text,
                "created_at": datetime.now(timezone.utc),
            }

    def record_metric(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Record a metric value."""
        if name not in self.metric_definitions:
            logging.warning(f"Recording metric '{name}' that hasn't been registered")

        metric = Metric(
            name=name,
            metric_type=self.metric_definitions.get(name, {}).get("type", MetricType.GAUGE),
            value=value,
            labels=labels or {},
            help_text=self.metric_definitions.get(name, {}).get("help", ""),
        )

        with self._lock:
            # Keep only recent metrics (last 1000 per metric)
            if len(self.metrics[name]) >= 1000:
                self.metrics[name] = self.metrics[name][-500:]  # Keep latest 500
            self.metrics[name].append(metric)

    def increment_counter(self, name: str, labels: dict[str, str] | None = None) -> None:
        """Increment a counter metric."""
        self.record_metric(name, 1, labels)

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Set a gauge metric value."""
        self.record_metric(name, value, labels)

    def record_histogram(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        """Record a histogram metric value."""
        self.record_metric(name, value, labels)

    def get_metrics(self, name_filter: str | None = None) -> list[Metric]:
        """Get metrics, optionally filtered by name pattern."""
        with self._lock:
            if name_filter:
                return [
                    metric
                    for metrics_list in self.metrics.values()
                    for metric in metrics_list
                    if name_filter in metric.name
                ]
            return [metric for metrics_list in self.metrics.values() for metric in metrics_list]

    def get_latest_metric(self, name: str) -> Metric | None:
        """Get the latest value for a specific metric."""
        with self._lock:
            if self.metrics.get(name):
                return self.metrics[name][-1]
            return None

    def collect_system_metrics(self) -> None:
        """Collect system-level metrics."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            self.set_gauge("system.cpu.percent", cpu_percent)

            # Memory usage
            memory = psutil.virtual_memory()
            self.set_gauge("system.memory.percent", memory.percent)
            self.set_gauge("system.memory.used", memory.used)
            self.set_gauge("system.memory.available", memory.available)

            # Disk usage
            disk = psutil.disk_usage("/")
            self.set_gauge("system.disk.percent", disk.percent)
            self.set_gauge("system.disk.used", disk.used)
            self.set_gauge("system.disk.free", disk.free)

            # Process info
            process = psutil.Process()
            self.set_gauge("process.memory.rss", process.memory_info().rss)
            self.set_gauge("process.cpu.percent", process.cpu_percent())
            self.set_gauge("process.num.threads", process.num_threads())

        except Exception:
            logging.exception("Error collecting system metrics")


class HealthMonitor:
    """Monitors service health through various checks."""

    def __init__(self, service_info: ServiceInfo) -> None:
        self.service_info = service_info
        self.health_checks: dict[str, HealthCheck] = {}
        self.current_status = HealthStatus.UNKNOWN
        self.status_history: deque = deque(maxlen=100)
        self._lock = threading.Lock()

        # Register built-in health checks
        self._register_builtin_checks()

    def _register_builtin_checks(self) -> None:
        """Register built-in health checks."""
        self.add_health_check(
            name="memory_usage",
            description="Check if memory usage is within acceptable limits",
            check_function=self._check_memory_usage,
            critical=True,
        )

        self.add_health_check(
            name="disk_usage",
            description="Check if disk usage is within acceptable limits",
            check_function=self._check_disk_usage,
            critical=True,
        )

        self.add_health_check(
            name="cpu_usage",
            description="Check if CPU usage is within acceptable limits",
            check_function=self._check_cpu_usage,
            critical=False,  # High CPU doesn't necessarily mean unhealthy
        )

    def _check_memory_usage(self) -> bool:
        """Check if memory usage is acceptable."""
        try:
            memory = psutil.virtual_memory()
        except Exception:
            return False
        else:
            return memory.percent < 90  # Less than 90% memory usage

    def _check_disk_usage(self) -> bool:
        """Check if disk usage is acceptable."""
        try:
            disk = psutil.disk_usage("/")
        except Exception:
            return False
        else:
            return disk.percent < 85  # Less than 85% disk usage

    def _check_cpu_usage(self) -> bool:
        """Check if CPU usage is acceptable."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
        except Exception:
            return False
        else:
            return cpu_percent < 95  # Less than 95% CPU usage

    def add_health_check(
        self,
        name: str,
        description: str,
        check_function: Callable[[], bool],
        critical: bool = True,
        timeout_seconds: float = 5.0,
        interval_seconds: float = 30.0,
    ) -> None:
        """Add a health check."""
        health_check = HealthCheck(
            name=name,
            description=description,
            check_function=check_function,
            critical=critical,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        )

        with self._lock:
            self.health_checks[name] = health_check

    def run_health_check(self, name: str) -> bool:
        """Run a specific health check."""
        with self._lock:
            if name not in self.health_checks:
                return False

            check = self.health_checks[name]

        try:
            # Run check with timeout
            start_time = time.time()
            result = check.check_function()
            duration = time.time() - start_time

            if duration > check.timeout_seconds:
                result = False
                error = f"Health check timed out ({duration:.2f}s > {check.timeout_seconds}s)"
            else:
                error = None

            # Update check result
            check.last_check = datetime.now(timezone.utc)
            check.last_result = result
            check.last_error = error

        except Exception as e:
            check.last_check = datetime.now(timezone.utc)
            check.last_result = False
            check.last_error = str(e)
            return False
        else:
            return result

    def run_all_health_checks(self) -> dict[str, bool]:
        """Run all health checks and return results."""
        results = {}

        for name in list(self.health_checks.keys()):
            results[name] = self.run_health_check(name)

        # Update overall health status
        self._update_health_status(results)

        return results

    def _update_health_status(self, check_results: dict[str, bool]) -> None:
        """Update overall health status based on check results."""
        critical_failures = 0
        non_critical_failures = 0

        for name, result in check_results.items():
            if not result:
                check = self.health_checks.get(name)
                if check and check.critical:
                    critical_failures += 1
                else:
                    non_critical_failures += 1

        # Determine status
        if critical_failures > 0:
            new_status = HealthStatus.UNHEALTHY
        elif non_critical_failures > 0:
            new_status = HealthStatus.DEGRADED
        else:
            new_status = HealthStatus.HEALTHY

        if new_status != self.current_status:
            self.current_status = new_status
            self.status_history.append(
                {
                    "status": new_status.value,
                    "timestamp": datetime.now(timezone.utc),
                    "details": check_results,
                }
            )

    def get_health_status(self) -> dict[str, Any]:
        """Get current health status."""
        with self._lock:
            checks_info = {}
            for name, check in self.health_checks.items():
                checks_info[name] = {
                    "description": check.description,
                    "last_check": check.last_check.isoformat() if check.last_check else None,
                    "last_result": check.last_result,
                    "last_error": check.last_error,
                    "critical": check.critical,
                }

        return {
            "service": self.service_info.service_name,
            "status": self.current_status.value,
            "instance_id": self.service_info.instance_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": checks_info,
        }


class AlertManager:
    """Manages alerts and notifications."""

    def __init__(self, metrics_collector: MetricsCollector) -> None:
        self.metrics_collector = metrics_collector
        self.alerts: dict[str, Alert] = {}
        self.alert_callbacks: list[Callable[[Alert], None]] = []
        self._lock = threading.Lock()

        # Register built-in alerts
        self._register_builtin_alerts()

    def _register_builtin_alerts(self) -> None:
        """Register built-in alerts."""
        self.add_alert(
            name="high_memory_usage",
            description="Memory usage is critically high",
            severity=AlertSeverity.CRITICAL,
            condition=lambda metrics: self._check_high_memory(metrics),
        )

        self.add_alert(
            name="high_error_rate",
            description="Error rate is unusually high",
            severity=AlertSeverity.ERROR,
            condition=lambda metrics: self._check_high_error_rate(metrics),
        )

        self.add_alert(
            name="service_unresponsive",
            description="Service appears to be unresponsive",
            severity=AlertSeverity.CRITICAL,
            condition=lambda metrics: self._check_service_unresponsive(metrics),
        )

    def _check_high_memory(self, metrics: dict[str, Any]) -> bool:
        """Check for high memory usage."""
        memory_metric = self.metrics_collector.get_latest_metric("system.memory.percent")
        if memory_metric:
            return memory_metric.value > 90
        return False

    def _check_high_error_rate(self, metrics: dict[str, Any]) -> bool:
        """Check for high error rate."""
        # Simple implementation - check if errors in last 5 minutes > 10
        recent_errors = [
            m
            for m in self.metrics_collector.get_metrics("grpc.errors.total")
            if (datetime.now(timezone.utc) - m.timestamp).seconds < 300
        ]
        return len(recent_errors) > 10

    def _check_service_unresponsive(self, metrics: dict[str, Any]) -> bool:
        """Check if service appears unresponsive."""
        # Check if no requests in last 10 minutes (for active services)
        recent_requests = [
            m
            for m in self.metrics_collector.get_metrics("grpc.requests.total")
            if (datetime.now(timezone.utc) - m.timestamp).seconds < 600
        ]
        # Only alert if service was previously active
        if len(recent_requests) == 0:
            historical_requests = self.metrics_collector.get_metrics("grpc.requests.total")
            return len(historical_requests) > 0  # Had requests before, now none
        return False

    def add_alert(
        self,
        name: str,
        description: str,
        severity: AlertSeverity,
        condition: Callable[[dict[str, Any]], bool],
        cooldown_seconds: float = 300.0,
    ) -> None:
        """Add an alert definition."""
        alert = Alert(
            alert_id=str(uuid.uuid4()),
            name=name,
            description=description,
            severity=severity,
            condition=condition,
            cooldown_seconds=cooldown_seconds,
        )

        with self._lock:
            self.alerts[name] = alert

    def add_alert_callback(self, callback: Callable[[Alert], None]) -> None:
        """Add callback for alert notifications."""
        self.alert_callbacks.append(callback)

    def check_alerts(self) -> list[Alert]:
        """Check all alerts and return any that are triggered."""
        triggered_alerts = []
        current_metrics = {}  # Could be enhanced to pass actual metrics

        with self._lock:
            for alert in self.alerts.values():
                try:
                    should_trigger = alert.condition(current_metrics)
                    now = datetime.now(timezone.utc)

                    if should_trigger and not alert.is_active:
                        # Check cooldown
                        if (
                            alert.last_triggered is None
                            or (now - alert.last_triggered).total_seconds() > alert.cooldown_seconds
                        ):
                            alert.is_active = True
                            alert.triggered_at = now
                            alert.last_triggered = now
                            alert.resolved_at = None

                            triggered_alerts.append(alert)

                            # Notify callbacks
                            for callback in self.alert_callbacks:
                                try:
                                    callback(alert)
                                except Exception:
                                    logging.exception("Error in alert callback")

                    elif not should_trigger and alert.is_active:
                        # Resolve alert
                        alert.is_active = False
                        alert.resolved_at = now

                except Exception:
                    logging.exception(f"Error checking alert '{alert.name}'")

        return triggered_alerts

    def get_active_alerts(self) -> list[Alert]:
        """Get all currently active alerts."""
        with self._lock:
            return [alert for alert in self.alerts.values() if alert.is_active]


class ServiceMonitor:
    """Main service monitoring coordinator."""

    def __init__(
        self,
        service_info: ServiceInfo,
        metrics_collection_interval: float = 30.0,
        health_check_interval: float = 30.0,
        alert_check_interval: float = 60.0,
    ) -> None:
        self.service_info = service_info
        self.metrics_collection_interval = metrics_collection_interval
        self.health_check_interval = health_check_interval
        self.alert_check_interval = alert_check_interval

        self.metrics_collector = MetricsCollector()
        self.health_monitor = HealthMonitor(service_info)
        self.alert_manager = AlertManager(self.metrics_collector)

        self._monitor_threads: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self._running = False

    def start_monitoring(self) -> None:
        """Start all monitoring processes."""
        if self._running:
            logging.warning("Monitoring is already running")
            return

        self._running = True
        self._stop_event.clear()

        # Start monitoring threads
        self._monitor_threads = [
            threading.Thread(target=self._metrics_collection_loop, daemon=True),
            threading.Thread(target=self._health_check_loop, daemon=True),
            threading.Thread(target=self._alert_check_loop, daemon=True),
        ]

        for thread in self._monitor_threads:
            thread.start()

        logging.info(f"Started monitoring for service {self.service_info.service_name}")

    def stop_monitoring(self) -> None:
        """Stop all monitoring processes."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        # Wait for threads to finish
        for thread in self._monitor_threads:
            if thread.is_alive():
                thread.join(timeout=5)

        logging.info(f"Stopped monitoring for service {self.service_info.service_name}")

    def _metrics_collection_loop(self) -> None:
        """Background loop for collecting metrics."""
        while not self._stop_event.is_set():
            try:
                self.metrics_collector.collect_system_metrics()
                self._stop_event.wait(self.metrics_collection_interval)
            except Exception:
                logging.exception("Error in metrics collection loop")
                self._stop_event.wait(5)  # Wait a bit before retrying

    def _health_check_loop(self) -> None:
        """Background loop for running health checks."""
        while not self._stop_event.is_set():
            try:
                self.health_monitor.run_all_health_checks()
                self._stop_event.wait(self.health_check_interval)
            except Exception:
                logging.exception("Error in health check loop")
                self._stop_event.wait(5)  # Wait a bit before retrying

    def _alert_check_loop(self) -> None:
        """Background loop for checking alerts."""
        while not self._stop_event.is_set():
            try:
                self.alert_manager.check_alerts()
                self._stop_event.wait(self.alert_check_interval)
            except Exception:
                logging.exception("Error in alert check loop")
                self._stop_event.wait(5)  # Wait a bit before retrying

    def get_monitoring_status(self) -> dict[str, Any]:
        """Get comprehensive monitoring status."""
        return {
            "service": self.service_info.__dict__,
            "health": self.health_monitor.get_health_status(),
            "metrics_summary": {
                "total_metrics": len(self.metrics_collector.get_metrics()),
                "registered_metrics": len(self.metrics_collector.metric_definitions),
            },
            "active_alerts": [
                {
                    "name": alert.name,
                    "severity": alert.severity.value,
                    "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
                    "description": alert.description,
                }
                for alert in self.alert_manager.get_active_alerts()
            ],
            "monitoring_status": {
                "running": self._running,
                "uptime_seconds": (
                    datetime.now(timezone.utc) - self.service_info.start_time
                ).total_seconds(),
            },
        }


# gRPC interceptor for metrics collection
class MetricsInterceptor(grpc.ServerInterceptor):
    """gRPC server interceptor for collecting metrics."""

    def __init__(self, metrics_collector: MetricsCollector) -> None:
        self.metrics_collector = metrics_collector

    def intercept_service(self, continuation, handler_call_details):
        def wrapper(request, context):
            start_time = time.time()
            method_name = handler_call_details.method

            # Increment request counter
            self.metrics_collector.increment_counter("grpc.requests.total", {"method": method_name})

            try:
                response = continuation(request, context)

                # Record success
                self.metrics_collector.increment_counter(
                    "grpc.requests.success.total", {"method": method_name}
                )

            except Exception as e:
                # Record error
                self.metrics_collector.increment_counter(
                    "grpc.errors.total", {"method": method_name, "error_type": type(e).__name__}
                )
                raise
            else:
                return response

            finally:
                # Record duration
                duration = time.time() - start_time
                self.metrics_collector.record_histogram(
                    "grpc.requests.duration", duration, {"method": method_name}
                )

        return wrapper


@contextmanager
def monitor_operation(metrics_collector: MetricsCollector, operation_name: str):
    """Context manager for monitoring operations."""
    start_time = time.time()

    try:
        yield

        # Record success
        metrics_collector.increment_counter(f"operations.{operation_name}.success.total")

    except Exception as e:
        # Record error
        metrics_collector.increment_counter(
            f"operations.{operation_name}.errors.total", {"error_type": type(e).__name__}
        )
        raise

    finally:
        # Record duration
        duration = time.time() - start_time
        metrics_collector.record_histogram(f"operations.{operation_name}.duration", duration)


def create_service_monitor(
    service_name: str,
    service_version: str = "1.0.0",
    host: str | None = None,
    port: int | None = None,
    **kwargs,
) -> ServiceMonitor:
    """Create a service monitor with default configuration."""

    if host is None:
        host = socket.gethostname()

    service_info = ServiceInfo(
        service_name=service_name,
        service_version=service_version,
        instance_id=str(uuid.uuid4()),
        host=host,
        port=port or 0,
        metadata=kwargs,
    )

    return ServiceMonitor(service_info)


def create_metrics_interceptor(service_monitor: ServiceMonitor) -> MetricsInterceptor:
    """Create a gRPC metrics interceptor."""
    return MetricsInterceptor(service_monitor.metrics_collector)
