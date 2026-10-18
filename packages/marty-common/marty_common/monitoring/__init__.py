"""Initialize monitoring package."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .service_monitor import (
        MetricsInterceptor,
        MetricType,
        ServiceInfo,
        ServiceMonitor,
        create_metrics_interceptor,
        create_service_monitor,
        monitor_operation,
    )

from .health_monitor import (
    Alert,
    AlertManager,
    AlertSeverity,
    DatabaseHealthCheck,
    HealthCheck,
    HealthCheckResult,
    HealthMonitor,
    HealthStatus,
    Metric,
    MetricsCollector,
    ResourceHealthCheck,
    ServiceHealthCheck,
    create_default_monitor,
)

__all__ = [
    "MetricType",
    "MetricsInterceptor",
    "ServiceInfo",
    "ServiceMonitor",
    "create_metrics_interceptor",
    "create_service_monitor",
    "monitor_operation",
    "Alert",
    "AlertManager",
    "AlertSeverity",
    "DatabaseHealthCheck",
    "HealthCheck",
    "HealthCheckResult",
    "HealthMonitor",
    "HealthStatus",
    "Metric",
    "MetricsCollector",
    "ResourceHealthCheck",
    "ServiceHealthCheck",
    "create_default_monitor",
]


def __getattr__(name: str):
    """Load the service API without replacing existing health-check exports."""
    if name in {
        "MetricType", "MetricsInterceptor", "ServiceInfo", "ServiceMonitor",
        "create_metrics_interceptor", "create_service_monitor", "monitor_operation",
    }:
        value = getattr(import_module(".service_monitor", __name__), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
