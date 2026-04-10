"""Comprehensive metrics collection and monitoring for resilience patterns."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Optional


class MetricType(str, Enum):
    """Types of metrics that can be collected."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricValue:
    """Single metric value with timestamp."""

    value: float
    timestamp: float
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class HistogramBucket:
    """Histogram bucket configuration."""

    upper_bound: float
    count: int = 0


class MetricsCollector:
    """Centralized metrics collection for resilience patterns."""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self._metrics: dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = defaultdict(float)
        self._histograms: dict[str, list[HistogramBucket]] = {}
        self._lock = Lock()

        # Default histogram buckets for latency metrics (milliseconds)
        self.default_latency_buckets = [
            1,
            2,
            5,
            10,
            25,
            50,
            100,
            250,
            500,
            1000,
            2500,
            5000,
            10000,
            float("inf"),
        ]

        # Initialize common resilience metrics
        self._initialize_resilience_metrics()

    def _initialize_resilience_metrics(self) -> None:
        """Initialize standard resilience metrics."""
        # Circuit breaker metrics
        self.register_counter(
            "circuit_breaker_requests_total", "Total requests through circuit breaker"
        )
        self.register_counter("circuit_breaker_failures_total", "Total failures in circuit breaker")
        self.register_counter(
            "circuit_breaker_successes_total", "Total successes in circuit breaker"
        )
        self.register_counter(
            "circuit_breaker_rejections_total", "Requests rejected by circuit breaker"
        )
        self.register_gauge(
            "circuit_breaker_state", "Current circuit breaker state (0=closed, 1=open, 2=half-open)"
        )
        self.register_histogram(
            "circuit_breaker_request_duration_ms", "Request duration through circuit breaker"
        )

        # Retry metrics
        self.register_counter("retry_attempts_total", "Total retry attempts")
        self.register_counter("retry_successes_total", "Total successful retries")
        self.register_counter("retry_exhausted_total", "Total exhausted retry attempts")
        self.register_histogram("retry_delay_ms", "Delay between retry attempts")
        self.register_histogram("retry_total_duration_ms", "Total duration including all retries")

        # Graceful degradation metrics
        self.register_counter("degradation_fallback_total", "Total fallback invocations")
        self.register_counter(
            "degradation_primary_success_total", "Total primary operation successes"
        )
        self.register_gauge("degradation_level", "Current degradation level")
        self.register_histogram(
            "degradation_response_time_ms", "Response time for degraded operations"
        )

        # Error metrics
        self.register_counter("errors_total", "Total errors by type and service")
        self.register_counter("error_recovery_total", "Total error recoveries")
        self.register_histogram("error_recovery_duration_ms", "Time to recover from errors")

    def register_counter(self, name: str, description: str = "") -> None:
        """Register a counter metric."""
        if name not in self._counters:
            self._counters[name] = 0.0

    def register_gauge(self, name: str, description: str = "") -> None:
        """Register a gauge metric."""
        if name not in self._gauges:
            self._gauges[name] = 0.0

    def register_histogram(
        self, name: str, description: str = "", buckets: list[float] | None = None
    ) -> None:
        """Register a histogram metric."""
        if name not in self._histograms:
            bucket_limits = buckets or self.default_latency_buckets
            self._histograms[name] = [HistogramBucket(upper_bound=limit) for limit in bucket_limits]

    def increment_counter(
        self, name: str, value: float = 1.0, labels: dict[str, str] | None = None
    ) -> None:
        """Increment a counter metric."""
        with self._lock:
            key = self._get_metric_key(name, labels)
            self._counters[key] += value

            metric_value = MetricValue(
                value=self._counters[key], timestamp=time.time(), labels=labels or {}
            )
            self._metrics[key].append(metric_value)

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Set a gauge metric value."""
        with self._lock:
            key = self._get_metric_key(name, labels)
            self._gauges[key] = value

            metric_value = MetricValue(value=value, timestamp=time.time(), labels=labels or {})
            self._metrics[key].append(metric_value)

    def observe_histogram(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        """Observe a value in a histogram metric."""
        with self._lock:
            key = self._get_metric_key(name, labels)

            if key in self._histograms:
                buckets = self._histograms[key]
                for bucket in buckets:
                    if value <= bucket.upper_bound:
                        bucket.count += 1

            metric_value = MetricValue(value=value, timestamp=time.time(), labels=labels or {})
            self._metrics[key].append(metric_value)

    def _get_metric_key(self, name: str, labels: dict[str, str] | None = None) -> str:
        """Generate a unique key for metric with labels."""
        if not labels:
            return name

        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def get_counter_value(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get current counter value."""
        key = self._get_metric_key(name, labels)
        return self._counters.get(key, 0.0)

    def get_gauge_value(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get current gauge value."""
        key = self._get_metric_key(name, labels)
        return self._gauges.get(key, 0.0)

    def get_histogram_stats(
        self, name: str, labels: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Get histogram statistics."""
        key = self._get_metric_key(name, labels)

        if key not in self._metrics:
            return {"count": 0, "sum": 0, "buckets": []}

        values = [m.value for m in self._metrics[key]]
        if not values:
            return {"count": 0, "sum": 0, "buckets": []}

        buckets = []
        if key in self._histograms:
            for bucket in self._histograms[key]:
                buckets.append({"upper_bound": bucket.upper_bound, "count": bucket.count})

        return {
            "count": len(values),
            "sum": sum(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "buckets": buckets,
        }

    def get_metric_history(
        self, name: str, labels: dict[str, str] | None = None, limit: int = 100
    ) -> list[MetricValue]:
        """Get recent history for a metric."""
        key = self._get_metric_key(name, labels)
        history = list(self._metrics.get(key, []))
        return history[-limit:] if limit else history

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all current metric values."""
        with self._lock:
            metrics = {}

            # Counters
            for name, value in self._counters.items():
                metrics[name] = {"type": "counter", "value": value}

            # Gauges
            for name, value in self._gauges.items():
                metrics[name] = {"type": "gauge", "value": value}

            # Histograms
            for name in self._histograms:
                stats = self.get_histogram_stats(name)
                metrics[name] = {"type": "histogram", "stats": stats}

            return metrics

    def reset_metrics(self) -> None:
        """Reset all metrics to initial state."""
        with self._lock:
            self._metrics.clear()
            self._counters.clear()
            self._gauges.clear()
            for histogram_buckets in self._histograms.values():
                for bucket in histogram_buckets:
                    bucket.count = 0


class ResilienceMetrics:
    """High-level interface for resilience pattern metrics."""

    def __init__(self, collector: MetricsCollector | None = None):
        self.collector = collector or MetricsCollector()

    def record_circuit_breaker_request(
        self, circuit_name: str, duration_ms: float, success: bool, state: str
    ) -> None:
        """Record circuit breaker request metrics."""
        labels = {"circuit_name": circuit_name}

        self.collector.increment_counter("circuit_breaker_requests_total", labels=labels)
        self.collector.observe_histogram(
            "circuit_breaker_request_duration_ms", duration_ms, labels=labels
        )

        if success:
            self.collector.increment_counter("circuit_breaker_successes_total", labels=labels)
        else:
            self.collector.increment_counter("circuit_breaker_failures_total", labels=labels)

        # Map state to numeric value for gauge
        state_value = {"closed": 0, "open": 1, "half_open": 2}.get(state, 0)
        self.collector.set_gauge("circuit_breaker_state", state_value, labels=labels)

    def record_circuit_breaker_rejection(self, circuit_name: str) -> None:
        """Record circuit breaker rejection."""
        labels = {"circuit_name": circuit_name}
        self.collector.increment_counter("circuit_breaker_rejections_total", labels=labels)

    def record_retry_attempt(
        self,
        operation_name: str,
        attempt_number: int,
        delay_ms: float,
        success: bool,
        exhausted: bool = False,
    ) -> None:
        """Record retry attempt metrics."""
        labels = {"operation": operation_name}

        self.collector.increment_counter("retry_attempts_total", labels=labels)
        self.collector.observe_histogram("retry_delay_ms", delay_ms, labels=labels)

        if success:
            self.collector.increment_counter("retry_successes_total", labels=labels)
        elif exhausted:
            self.collector.increment_counter("retry_exhausted_total", labels=labels)

    def record_retry_total_duration(self, operation_name: str, total_duration_ms: float) -> None:
        """Record total duration including all retries."""
        labels = {"operation": operation_name}
        self.collector.observe_histogram(
            "retry_total_duration_ms", total_duration_ms, labels=labels
        )

    def record_degradation_event(
        self,
        feature_name: str,
        event_type: str,  # "fallback", "primary_success"
        response_time_ms: float,
        degradation_level: int,
    ) -> None:
        """Record graceful degradation event."""
        labels = {"feature": feature_name}

        if event_type == "fallback":
            self.collector.increment_counter("degradation_fallback_total", labels=labels)
        elif event_type == "primary_success":
            self.collector.increment_counter("degradation_primary_success_total", labels=labels)

        self.collector.observe_histogram(
            "degradation_response_time_ms", response_time_ms, labels=labels
        )
        self.collector.set_gauge("degradation_level", degradation_level, labels=labels)

    def record_error(
        self, service_name: str, error_type: str, recovery_duration_ms: float | None = None
    ) -> None:
        """Record error occurrence and recovery."""
        labels = {"service": service_name, "error_type": error_type}

        self.collector.increment_counter("errors_total", labels=labels)

        if recovery_duration_ms is not None:
            self.collector.increment_counter("error_recovery_total", labels=labels)
            self.collector.observe_histogram(
                "error_recovery_duration_ms", recovery_duration_ms, labels=labels
            )

    def get_circuit_breaker_stats(self, circuit_name: str) -> dict[str, Any]:
        """Get comprehensive circuit breaker statistics."""
        labels = {"circuit_name": circuit_name}

        return {
            "total_requests": self.collector.get_counter_value(
                "circuit_breaker_requests_total", labels
            ),
            "successes": self.collector.get_counter_value(
                "circuit_breaker_successes_total", labels
            ),
            "failures": self.collector.get_counter_value("circuit_breaker_failures_total", labels),
            "rejections": self.collector.get_counter_value(
                "circuit_breaker_rejections_total", labels
            ),
            "current_state": self.collector.get_gauge_value("circuit_breaker_state", labels),
            "duration_stats": self.collector.get_histogram_stats(
                "circuit_breaker_request_duration_ms", labels
            ),
        }

    def get_retry_stats(self, operation_name: str) -> dict[str, Any]:
        """Get comprehensive retry statistics."""
        labels = {"operation": operation_name}

        return {
            "total_attempts": self.collector.get_counter_value("retry_attempts_total", labels),
            "successes": self.collector.get_counter_value("retry_successes_total", labels),
            "exhausted": self.collector.get_counter_value("retry_exhausted_total", labels),
            "delay_stats": self.collector.get_histogram_stats("retry_delay_ms", labels),
            "duration_stats": self.collector.get_histogram_stats("retry_total_duration_ms", labels),
        }

    def get_degradation_stats(self, feature_name: str) -> dict[str, Any]:
        """Get comprehensive degradation statistics."""
        labels = {"feature": feature_name}

        return {
            "fallback_count": self.collector.get_counter_value(
                "degradation_fallback_total", labels
            ),
            "primary_success_count": self.collector.get_counter_value(
                "degradation_primary_success_total", labels
            ),
            "current_level": self.collector.get_gauge_value("degradation_level", labels),
            "response_time_stats": self.collector.get_histogram_stats(
                "degradation_response_time_ms", labels
            ),
        }

    def get_error_stats(self, service_name: str) -> dict[str, Any]:
        """Get comprehensive error statistics."""
        labels = {"service": service_name}

        # Get all error types for this service
        all_metrics = self.collector.get_all_metrics()
        error_types = set()

        for metric_name in all_metrics:
            if "errors_total" in metric_name and f"service={service_name}" in metric_name:
                # Extract error_type from labels
                if "error_type=" in metric_name:
                    start = metric_name.find("error_type=") + len("error_type=")
                    end = metric_name.find(",", start)
                    if end == -1:
                        end = metric_name.find("}", start)
                    error_type = metric_name[start:end]
                    error_types.add(error_type)

        error_breakdown = {}
        for error_type in error_types:
            error_labels = {"service": service_name, "error_type": error_type}
            error_breakdown[error_type] = {
                "count": self.collector.get_counter_value("errors_total", error_labels),
                "recoveries": self.collector.get_counter_value(
                    "error_recovery_total", error_labels
                ),
            }

        return {
            "total_errors": self.collector.get_counter_value("errors_total", labels),
            "total_recoveries": self.collector.get_counter_value("error_recovery_total", labels),
            "recovery_duration_stats": self.collector.get_histogram_stats(
                "error_recovery_duration_ms", labels
            ),
            "error_breakdown": error_breakdown,
        }

    def get_resilience_summary(self) -> dict[str, Any]:
        """Get comprehensive resilience summary across all components."""
        all_metrics = self.collector.get_all_metrics()

        # Extract unique services, circuits, operations, and features
        services = set()
        circuits = set()
        operations = set()
        features = set()

        for metric_name in all_metrics:
            if "service=" in metric_name:
                start = metric_name.find("service=") + len("service=")
                end = metric_name.find(",", start)
                if end == -1:
                    end = metric_name.find("}", start)
                services.add(metric_name[start:end])

            if "circuit_name=" in metric_name:
                start = metric_name.find("circuit_name=") + len("circuit_name=")
                end = metric_name.find(",", start)
                if end == -1:
                    end = metric_name.find("}", start)
                circuits.add(metric_name[start:end])

            if "operation=" in metric_name:
                start = metric_name.find("operation=") + len("operation=")
                end = metric_name.find(",", start)
                if end == -1:
                    end = metric_name.find("}", start)
                operations.add(metric_name[start:end])

            if "feature=" in metric_name:
                start = metric_name.find("feature=") + len("feature=")
                end = metric_name.find(",", start)
                if end == -1:
                    end = metric_name.find("}", start)
                features.add(metric_name[start:end])

        return {
            "timestamp": time.time(),
            "summary": {
                "total_services": len(services),
                "total_circuits": len(circuits),
                "total_operations": len(operations),
                "total_features": len(features),
            },
            "circuit_breakers": {name: self.get_circuit_breaker_stats(name) for name in circuits},
            "retries": {name: self.get_retry_stats(name) for name in operations},
            "degradation": {name: self.get_degradation_stats(name) for name in features},
            "errors": {name: self.get_error_stats(name) for name in services},
        }


# Global instance for easy access
global_resilience_metrics = ResilienceMetrics()


def get_resilience_metrics() -> ResilienceMetrics:
    """Get the global resilience metrics instance."""
    return global_resilience_metrics


def reset_resilience_metrics() -> None:
    """Reset all resilience metrics."""
    global_resilience_metrics.collector.reset_metrics()


__all__ = [
    "MetricsCollector",
    "ResilienceMetrics",
    "MetricType",
    "MetricValue",
    "HistogramBucket",
    "get_resilience_metrics",
    "reset_resilience_metrics",
]
