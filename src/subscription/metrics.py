"""
Prometheus Metrics for KMS/HSM Subscription Services.

Exposes counters, histograms, and gauges for monitoring KMS operations,
signing latency, error rates, and active provider configurations.
"""

from __future__ import annotations

import time
from contextlib import contextmanager

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Dedicated registry so metrics don't collide with other subsystems
kms_registry = CollectorRegistry()

# ── Counters ─────────────────────────────────────────────

kms_operations_total = Counter(
    "kms_operations_total",
    "Total KMS operations",
    ["operation", "provider", "status"],
    registry=kms_registry,
)

kms_errors_total = Counter(
    "kms_errors_total",
    "Total KMS errors",
    ["error_type", "provider"],
    registry=kms_registry,
)

kms_auth_failures_total = Counter(
    "kms_auth_failures_total",
    "Total authentication/authorization failures",
    ["reason"],
    registry=kms_registry,
)

# ── Histograms ───────────────────────────────────────────

kms_signing_duration_seconds = Histogram(
    "kms_signing_duration_seconds",
    "Signing operation duration in seconds",
    ["provider"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    registry=kms_registry,
)

kms_operation_duration_seconds = Histogram(
    "kms_operation_duration_seconds",
    "General KMS operation duration in seconds",
    ["operation"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=kms_registry,
)

# ── Gauges ───────────────────────────────────────────────

kms_active_providers = Gauge(
    "kms_active_providers",
    "Number of active KMS provider configurations",
    ["provider"],
    registry=kms_registry,
)

kms_circuit_breaker_state = Gauge(
    "kms_circuit_breaker_state",
    "Circuit breaker state per org (0=closed, 1=half_open, 2=open)",
    ["org_id"],
    registry=kms_registry,
)

kms_cache_size = Gauge(
    "kms_cache_size",
    "Current size of the KMS provider cache",
    registry=kms_registry,
)


# ── Helpers ──────────────────────────────────────────────

@contextmanager
def track_signing(provider: str):
    """Context manager that times a signing operation and records metrics."""
    start = time.monotonic()
    status = "success"
    try:
        yield
    except Exception as exc:
        status = "error"
        kms_errors_total.labels(error_type=type(exc).__name__, provider=provider).inc()
        raise
    finally:
        duration = time.monotonic() - start
        kms_signing_duration_seconds.labels(provider=provider).observe(duration)
        kms_operations_total.labels(
            operation="sign", provider=provider, status=status
        ).inc()


def record_operation(operation: str, provider: str, status: str = "success"):
    """Record a KMS operation result."""
    kms_operations_total.labels(
        operation=operation, provider=provider, status=status
    ).inc()


def record_auth_failure(reason: str):
    """Record an authentication or authorization failure."""
    kms_auth_failures_total.labels(reason=reason).inc()


def get_metrics() -> bytes:
    """Return Prometheus metrics in text exposition format."""
    return generate_latest(kms_registry)
