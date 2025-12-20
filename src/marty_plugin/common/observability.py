from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

try:
    from prometheus_client import Counter, Gauge, Histogram, Info

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


@dataclass
class MetricDefinition:
    """Definition for a metric with its metadata."""

    name: str
    description: str
    metric_type: str  # counter, histogram, gauge, info
    labels: list[str] = field(default_factory=list)
    buckets: list[float] | None = None  # For histograms


class MetricsCollector:
    """
    Metrics collection for the Consistency Engine.

    Provides unified metrics collection with optional Prometheus integration
    and structured logging fallback.
    """

    def __init__(self, service_name: str, enable_prometheus: bool = True) -> None:
        """Initialize metrics collector."""
        self.service_name = service_name
        self.enable_prometheus = enable_prometheus and PROMETHEUS_AVAILABLE
        self.logger = logging.getLogger(f"{__name__}.{service_name}")

        # Internal metrics storage for fallback
        self._counters: dict[str, int] = defaultdict(int)
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._gauges: dict[str, float] = defaultdict(float)
        self._info: dict[str, dict[str, str]] = defaultdict(dict)

        # Prometheus metrics registry
        self._prometheus_metrics: dict[str, Any] = {}

        # Initialize standard consistency engine metrics
        self._initialize_standard_metrics()

    def _initialize_standard_metrics(self) -> None:
        """Initialize standard metrics for the consistency engine."""
        standard_metrics = [
            MetricDefinition(
                name="consistency_checks_total",
                description="Total number of consistency checks performed",
                metric_type="counter",
                labels=["status", "zone_count"],
            ),
            MetricDefinition(
                name="consistency_check_duration_seconds",
                description="Duration of consistency checks in seconds",
                metric_type="histogram",
                labels=["status"],
                buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            ),
            MetricDefinition(
                name="consistency_rules_executed_total",
                description="Total number of consistency rules executed",
                metric_type="counter",
                labels=["rule_type", "status"],
            ),
            MetricDefinition(
                name="field_mismatches_total",
                description="Total number of field mismatches detected",
                metric_type="counter",
                labels=["field_name", "severity", "zone_a", "zone_b"],
            ),
            MetricDefinition(
                name="confidence_score_distribution",
                description="Distribution of consistency check confidence scores",
                metric_type="histogram",
                buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            ),
            MetricDefinition(
                name="consistency_engine_info",
                description="Information about the consistency engine",
                metric_type="info",
            ),
            MetricDefinition(
                name="audit_entries_total",
                description="Total number of audit entries created",
                metric_type="counter",
                labels=["operation_type"],
            ),
            MetricDefinition(
                name="active_consistency_checks",
                description="Number of currently active consistency checks",
                metric_type="gauge",
            ),
        ]

        for metric_def in standard_metrics:
            self._register_metric(metric_def)

    def _register_metric(self, metric_def: MetricDefinition) -> None:
        """Register a metric with Prometheus if available."""
        if not self.enable_prometheus:
            return

        metric_name = f"{self.service_name}_{metric_def.name}"

        try:
            if metric_def.metric_type == "counter":
                self._prometheus_metrics[metric_def.name] = Counter(
                    metric_name, metric_def.description, metric_def.labels
                )
            elif metric_def.metric_type == "histogram":
                self._prometheus_metrics[metric_def.name] = Histogram(
                    metric_name,
                    metric_def.description,
                    metric_def.labels,
                    buckets=metric_def.buckets,
                )
            elif metric_def.metric_type == "gauge":
                self._prometheus_metrics[metric_def.name] = Gauge(
                    metric_name, metric_def.description, metric_def.labels
                )
            elif metric_def.metric_type == "info":
                self._prometheus_metrics[metric_def.name] = Info(
                    metric_name, metric_def.description
                )
        except Exception as e:
            self.logger.warning(f"Failed to register Prometheus metric {metric_name}: {e}")

    def increment(
        self, metric_name: str, labels: dict[str, str] | None = None, value: float = 1.0
    ) -> None:
        """Increment a counter metric."""
        self._counters[metric_name] += value

        if self.enable_prometheus and metric_name in self._prometheus_metrics:
            try:
                if labels:
                    self._prometheus_metrics[metric_name].labels(**labels).inc(value)
                else:
                    self._prometheus_metrics[metric_name].inc(value)
            except Exception as e:
                self.logger.warning(f"Failed to increment Prometheus metric {metric_name}: {e}")

        # Log metric for observability
        self.logger.debug(
            "Metric incremented",
            extra={
                "metric_name": metric_name,
                "value": value,
                "labels": labels or {},
                "total": self._counters[metric_name],
            },
        )

    def histogram(
        self, metric_name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        """Record a value in a histogram metric."""
        self._histograms[metric_name].append(value)

        if self.enable_prometheus and metric_name in self._prometheus_metrics:
            try:
                if labels:
                    self._prometheus_metrics[metric_name].labels(**labels).observe(value)
                else:
                    self._prometheus_metrics[metric_name].observe(value)
            except Exception as e:
                self.logger.warning(f"Failed to record Prometheus histogram {metric_name}: {e}")

        # Log metric for observability
        self.logger.debug(
            "Histogram value recorded",
            extra={"metric_name": metric_name, "value": value, "labels": labels or {}},
        )

    def gauge(self, metric_name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Set a gauge metric value."""
        self._gauges[metric_name] = value

        if self.enable_prometheus and metric_name in self._prometheus_metrics:
            try:
                if labels:
                    self._prometheus_metrics[metric_name].labels(**labels).set(value)
                else:
                    self._prometheus_metrics[metric_name].set(value)
            except Exception as e:
                self.logger.warning(f"Failed to set Prometheus gauge {metric_name}: {e}")

        # Log metric for observability
        self.logger.debug(
            "Gauge value set",
            extra={"metric_name": metric_name, "value": value, "labels": labels or {}},
        )

    def info(self, metric_name: str, info_dict: dict[str, str]) -> None:
        """Set info metric values."""
        self._info[metric_name] = info_dict

        if self.enable_prometheus and metric_name in self._prometheus_metrics:
            try:
                self._prometheus_metrics[metric_name].info(info_dict)
            except Exception as e:
                self.logger.warning(f"Failed to set Prometheus info {metric_name}: {e}")

        # Log metric for observability
        self.logger.debug("Info metric set", extra={"metric_name": metric_name, "info": info_dict})

    @contextmanager
    def timer(self, metric_name: str, labels: dict[str, str] | None = None):
        """Context manager for timing operations."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.histogram(metric_name, duration, labels)

    def get_metric_summary(self) -> dict[str, Any]:
        """Get a summary of all collected metrics."""
        return {
            "counters": dict(self._counters),
            "histograms": {
                k: {"count": len(v), "sum": sum(v), "values": v[-10:]}
                for k, v in self._histograms.items()
            },
            "gauges": dict(self._gauges),
            "info": dict(self._info),
        }


class StructuredLogger:
    """
    Structured logging for the Consistency Engine.

    Provides structured logging with consistent formatting and
    audit trail capabilities.
    """

    def __init__(self, name: str, enable_audit: bool = True) -> None:
        """Initialize structured logger."""
        self.logger = logging.getLogger(name)
        self.enable_audit = enable_audit
        self.audit_entries: list[dict[str, Any]] = []

        # Set up structured formatter if not already configured
        if not self.logger.handlers:
            self._setup_structured_logging()

    def _setup_structured_logging(self) -> None:
        """Set up structured logging formatter."""
        handler = logging.StreamHandler()
        formatter = StructuredFormatter()
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def info(self, message: str, extra: dict[str, Any] | None = None, **kwargs) -> None:
        """Log info level message with structured data."""
        self._log(logging.INFO, message, extra, **kwargs)

    def warning(self, message: str, extra: dict[str, Any] | None = None, **kwargs) -> None:
        """Log warning level message with structured data."""
        self._log(logging.WARNING, message, extra, **kwargs)

    def error(self, message: str, extra: dict[str, Any] | None = None, **kwargs) -> None:
        """Log error level message with structured data."""
        self._log(logging.ERROR, message, extra, **kwargs)

    def debug(self, message: str, extra: dict[str, Any] | None = None, **kwargs) -> None:
        """Log debug level message with structured data."""
        self._log(logging.DEBUG, message, extra, **kwargs)

    def audit(
        self,
        operation: str,
        details: dict[str, Any],
        request_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        """Log audit entry for compliance and tracking."""
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "operation": operation,
            "details": details,
            "request_id": request_id,
            "user_id": user_id,
            "level": "AUDIT",
        }

        if self.enable_audit:
            self.audit_entries.append(audit_entry)

        # Also log as structured message
        self.info(
            f"AUDIT: {operation}",
            extra={
                "audit_entry": audit_entry,
                "operation_type": "audit",
                "request_id": request_id,
                "user_id": user_id,
            },
        )

    def _log(self, level: int, message: str, extra: dict[str, Any] | None = None, **kwargs) -> None:
        """Internal logging method with structured formatting."""
        # Merge extra and kwargs
        log_extra = extra or {}
        log_extra.update(kwargs)

        # Add standard fields
        log_extra.update(
            {"timestamp": datetime.utcnow().isoformat(), "service": "consistency_engine"}
        )

        self.logger.log(level, message, extra=log_extra)

    def get_audit_trail(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Get audit trail entries."""
        if limit:
            return self.audit_entries[-limit:]
        return self.audit_entries.copy()


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields if present
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in log_entry and not key.startswith("_"):
                    # Skip standard logging fields
                    if key not in [
                        "name",
                        "msg",
                        "args",
                        "levelname",
                        "levelno",
                        "pathname",
                        "filename",
                        "module",
                        "lineno",
                        "funcName",
                        "created",
                        "msecs",
                        "relativeCreated",
                        "thread",
                        "threadName",
                        "processName",
                        "process",
                        "exc_info",
                        "exc_text",
                        "stack_info",
                    ]:
                        try:
                            # Ensure value is JSON serializable
                            json.dumps(value)
                            log_entry[key] = value
                        except (TypeError, ValueError):
                            log_entry[key] = str(value)

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


class ConsistencyAuditTrail:
    """
    Audit trail specifically for consistency engine operations.

    Provides detailed tracking of all consistency checks for compliance
    and debugging purposes.
    """

    def __init__(self, storage_backend: Any | None = None) -> None:
        """Initialize audit trail."""
        self.storage_backend = storage_backend
        self.logger = StructuredLogger(__name__)
        self._local_entries: list[dict[str, Any]] = []

    def record_consistency_check(
        self,
        request_id: str,
        zone_data: list[Any],
        rule_results: list[Any],
        overall_result: dict[str, Any],
        processing_time_ms: int,
        context: dict[str, str],
    ) -> str:
        """Record a consistency check operation."""
        audit_id = str(time.time_ns())

        audit_entry = {
            "audit_id": audit_id,
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat(),
            "operation_type": "consistency_check",
            "input_data": {
                "zones": [
                    {"zone": zone.zone, "fields_count": len(zone.fields)} for zone in zone_data
                ],
                "context": context,
            },
            "processing_details": {
                "rules_executed": len(rule_results),
                "processing_time_ms": processing_time_ms,
                "overall_status": overall_result.get("status"),
                "confidence_score": overall_result.get("confidence"),
            },
            "results": {
                "mismatches_count": len(overall_result.get("mismatches", [])),
                "warnings_count": len(overall_result.get("warnings", [])),
                "critical_issues": [
                    m
                    for m in overall_result.get("mismatches", [])
                    if getattr(m, "severity_score", 0) >= 0.7
                ],
            },
        }

        self._store_audit_entry(audit_entry)

        self.logger.audit("consistency_check", audit_entry, request_id=request_id)

        return audit_id

    def record_rule_execution(
        self, rule_id: str, rule_result: Any, processing_time_ms: int, context: dict[str, str]
    ) -> None:
        """Record individual rule execution."""
        audit_entry = {
            "audit_id": str(time.time_ns()),
            "timestamp": datetime.utcnow().isoformat(),
            "operation_type": "rule_execution",
            "rule_details": {
                "rule_id": rule_id,
                "status": rule_result.status,
                "confidence_score": rule_result.confidence_score,
                "mismatches_count": len(rule_result.mismatches),
                "processing_time_ms": processing_time_ms,
            },
            "context": context,
        }

        self._store_audit_entry(audit_entry)

    def record_field_mismatch(self, mismatch: Any, context: dict[str, str]) -> None:
        """Record field mismatch for detailed tracking."""
        audit_entry = {
            "audit_id": str(time.time_ns()),
            "timestamp": datetime.utcnow().isoformat(),
            "operation_type": "field_mismatch",
            "mismatch_details": {
                "field": mismatch.field_name,
                "zone_a": mismatch.zone_a,
                "value_a": mismatch.value_a,
                "zone_b": mismatch.zone_b,
                "value_b": mismatch.value_b,
                "severity_score": mismatch.severity_score,
                "explanation": mismatch.explanation,
            },
            "context": context,
        }

        self._store_audit_entry(audit_entry)

    def _store_audit_entry(self, entry: dict[str, Any]) -> None:
        """Store audit entry in configured backend."""
        # Store locally
        self._local_entries.append(entry)

        # Store in external backend if configured
        if self.storage_backend:
            try:
                self.storage_backend.store_audit_entry(entry)
            except Exception as e:
                self.logger.error(f"Failed to store audit entry in backend: {e}")

    def query_audit_trail(
        self,
        request_id: str | None = None,
        operation_type: str | None = None,
        from_timestamp: str | None = None,
        to_timestamp: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query audit trail with filters."""
        results = self._local_entries.copy()

        # Apply filters
        if request_id:
            results = [e for e in results if e.get("request_id") == request_id]

        if operation_type:
            results = [e for e in results if e.get("operation_type") == operation_type]

        if from_timestamp:
            results = [e for e in results if e.get("timestamp", "") >= from_timestamp]

        if to_timestamp:
            results = [e for e in results if e.get("timestamp", "") <= to_timestamp]

        # Sort by timestamp descending and limit
        results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return results[:limit]

    def get_statistics(self) -> dict[str, Any]:
        """Get audit trail statistics."""
        total_entries = len(self._local_entries)
        operation_counts = defaultdict(int)

        for entry in self._local_entries:
            operation_counts[entry.get("operation_type", "unknown")] += 1

        return {
            "total_entries": total_entries,
            "operation_counts": dict(operation_counts),
            "oldest_entry": (
                self._local_entries[0].get("timestamp") if self._local_entries else None
            ),
            "newest_entry": (
                self._local_entries[-1].get("timestamp") if self._local_entries else None
            ),
        }
