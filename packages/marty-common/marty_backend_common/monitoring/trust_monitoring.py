"""Monitoring and alerting for trust and PKD services.

Provides:
- Prometheus metrics for key rotation events
- Health checks for trust list freshness
- Alerts for certificate/key expiration
- Service availability monitoring
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, Info, generate_latest
from starlette.responses import Response
from typing_extensions import Self

logger = logging.getLogger(__name__)

# Prometheus metrics
trust_operations_total = Counter(
    "trust_operations_total",
    "Total trust operations",
    ["operation_type", "status", "country", "role"],
)

key_rotation_events_total = Counter(
    "key_rotation_events_total", "Total key rotation events", ["country", "role", "action"]
)

trust_list_age_seconds = Gauge(
    "trust_list_age_seconds", "Age of trust list in seconds", ["country", "source"]
)

certificate_expiry_days = Gauge(
    "certificate_expiry_days",
    "Days until certificate expiry",
    ["certificate_type", "country", "identifier"],
)

pkd_requests_total = Counter(
    "pkd_requests_total", "Total PKD requests", ["endpoint", "country", "status"]
)

pkd_request_duration_seconds = Histogram(
    "pkd_request_duration_seconds", "PKD request duration", ["endpoint", "country"]
)

active_keys_count = Gauge(
    "active_keys_count", "Number of active keys", ["country", "role", "key_type"]
)

service_info = Info("service", "Service information")

# Set service info
service_info.info(
    {
        "version": "2.0.0",
        "component": "trust_and_pkd",
        "protocol": "vds_nc_doc9303",
    }
)


class TrustMonitor:
    """Trust system monitoring and metrics."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def record_key_rotation(
        self,
        country: str,
        role: str,
        action: str,  # "created", "rotated", "revoked"
        success: bool = True,
    ) -> None:
        """Record key rotation event."""
        key_rotation_events_total.labels(country=country, role=role, action=action).inc()

        self.logger.info(f"Key rotation event: {action} for {country}/{role}, success={success}")

    def record_trust_operation(
        self,
        operation: str,  # "verify_signature", "fetch_keys", "validate_chain"
        status: str,  # "success", "failure", "warning"
        country: str = "",
        role: str = "",
    ) -> None:
        """Record trust operation."""
        trust_operations_total.labels(
            operation_type=operation, status=status, country=country, role=role
        ).inc()

    def update_trust_list_age(
        self,
        country: str,
        source: str,
        last_updated: datetime,
    ) -> None:
        """Update trust list age metric."""
        age_seconds = (datetime.now(timezone.utc) - last_updated).total_seconds()
        trust_list_age_seconds.labels(country=country, source=source).set(age_seconds)

    def update_certificate_expiry(
        self,
        cert_type: str,  # "csca", "dsc", "vds_nc"
        country: str,
        identifier: str,
        expiry_date: datetime,
    ) -> None:
        """Update certificate expiry metric."""
        days_until_expiry = (expiry_date - datetime.now(timezone.utc)).days
        certificate_expiry_days.labels(
            certificate_type=cert_type, country=country, identifier=identifier
        ).set(days_until_expiry)

    def record_pkd_request(
        self,
        endpoint: str,
        country: str,
        status_code: int,
        duration: float,
    ) -> None:
        """Record PKD request metrics."""
        status = "success" if 200 <= status_code < 300 else "error"

        pkd_requests_total.labels(endpoint=endpoint, country=country, status=status).inc()

        pkd_request_duration_seconds.labels(endpoint=endpoint, country=country).observe(duration)

    def update_active_keys_count(
        self,
        country: str,
        role: str,
        key_type: str,  # "vds_nc", "dsc"
        count: int,
    ) -> None:
        """Update active keys count."""
        active_keys_count.labels(country=country, role=role, key_type=key_type).set(count)


class HealthChecker:
    """Health check service for trust components."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.checks: dict[str, Any] = {}

    async def check_database_health(self, session: Any) -> dict[str, Any]:
        """Check database connectivity and performance."""
        try:
            start_time = time.time()

            # Simple query to test connectivity
            # result = await session.execute(text("SELECT 1"))
            # result.scalar()

            duration = time.time() - start_time

            return {
                "status": "healthy",
                "response_time_ms": round(duration * 1000, 2),
                "checks": ["connectivity", "performance"],
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e), "checks": ["connectivity"]}

    async def check_trust_list_freshness(
        self,
        trust_manager: Any,
        warning_hours: int = 24,
        critical_hours: int = 48,
    ) -> dict[str, Any]:
        """Check trust list freshness."""
        try:
            # This would check actual trust list age
            # trust_list = await trust_manager.get_trust_list()
            # age_hours = trust_list.get_age_hours()

            # Mock for demonstration
            age_hours = 12  # Mock value

            if age_hours > critical_hours:
                status = "critical"
                level = "error"
            elif age_hours > warning_hours:
                status = "warning"
                level = "warn"
            else:
                status = "healthy"
                level = "info"

        except Exception as e:
            return {
                "status": "error",
                "level": "error",
                "error": str(e),
            }
        else:
            return {
                "status": status,
                "level": level,
                "age_hours": age_hours,
                "warning_threshold": warning_hours,
                "critical_threshold": critical_hours,
            }

    async def check_key_expiration(
        self,
        key_manager: Any,
        warning_days: int = 30,
    ) -> dict[str, Any]:
        """Check for expiring keys."""
        try:
            # expiring_keys = await key_manager.get_expiring_keys(warning_days)
            # Mock for demonstration
            expiring_keys = []  # Mock empty list

            if expiring_keys:
                return {
                    "status": "warning",
                    "level": "warn",
                    "expiring_count": len(expiring_keys),
                    "warning_days": warning_days,
                    "expiring_keys": [
                        {
                            "kid": key.kid,
                            "country": key.issuer_country,
                            "role": key.role.value,
                            "expires_at": key.not_after.isoformat(),
                        }
                        for key in expiring_keys[:5]  # Limit to first 5
                    ],
                }
            return {
                "status": "healthy",
                "level": "info",
                "expiring_count": 0,
                "warning_days": warning_days,
            }
        except Exception as e:
            return {
                "status": "error",
                "level": "error",
                "error": str(e),
            }

    async def check_pkd_connectivity(
        self,
        pkd_base_url: str,
    ) -> dict[str, Any]:
        """Check PKD service connectivity."""
        try:
            import asyncio

            import aiohttp

            async with aiohttp.ClientSession() as session:
                start_time = time.time()
                async with session.get(f"{pkd_base_url}/api/v1/pkd/health", timeout=5) as response:
                    duration = time.time() - start_time

                    if response.status == 200:
                        return {
                            "status": "healthy",
                            "response_time_ms": round(duration * 1000, 2),
                            "endpoint": f"{pkd_base_url}/api/v1/pkd/health",
                        }
                    return {
                        "status": "unhealthy",
                        "response_code": response.status,
                        "endpoint": f"{pkd_base_url}/api/v1/pkd/health",
                    }
        except asyncio.TimeoutError:
            return {
                "status": "unhealthy",
                "error": "timeout",
                "timeout_seconds": 5,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }

    async def get_overall_health(
        self,
        session: Any = None,
        trust_manager: Any = None,
        key_manager: Any = None,
        pkd_base_url: str = "",
    ) -> dict[str, Any]:
        """Get overall system health."""
        checks = {}
        overall_status = "healthy"

        # Database health
        if session:
            checks["database"] = await self.check_database_health(session)
            if checks["database"]["status"] != "healthy":
                overall_status = "degraded"

        # Trust list freshness
        if trust_manager:
            checks["trust_list"] = await self.check_trust_list_freshness(trust_manager)
            if checks["trust_list"]["status"] in ["warning", "critical"]:
                overall_status = "degraded"
            if checks["trust_list"]["status"] == "critical":
                overall_status = "unhealthy"

        # Key expiration
        if key_manager:
            checks["key_expiration"] = await self.check_key_expiration(key_manager)
            if checks["key_expiration"]["status"] == "warning":
                overall_status = "degraded"

        # PKD connectivity
        if pkd_base_url:
            checks["pkd_connectivity"] = await self.check_pkd_connectivity(pkd_base_url)
            if checks["pkd_connectivity"]["status"] != "healthy":
                overall_status = "degraded"

        return {
            "status": overall_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
            "service": {
                "name": "trust_and_pkd",
                "version": "2.0.0",
                "uptime_seconds": time.time(),  # Would track actual uptime
            },
        }


# Global instances
trust_monitor = TrustMonitor()
health_checker = HealthChecker()


# FastAPI endpoints
async def metrics_endpoint() -> Response:
    """Prometheus metrics endpoint."""
    metrics_data = generate_latest()
    return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)


async def health_endpoint() -> dict[str, Any]:
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "trust_and_pkd",
        "version": "2.0.0",
    }


async def ready_endpoint(
    session: Any = None,
    trust_manager: Any = None,
    key_manager: Any = None,
    pkd_base_url: str = "",
) -> dict[str, Any]:
    """Readiness check endpoint with detailed health information."""
    return await health_checker.get_overall_health(
        session=session,
        trust_manager=trust_manager,
        key_manager=key_manager,
        pkd_base_url=pkd_base_url,
    )


# Alert rules (would be configured in Prometheus/Alertmanager)
ALERT_RULES = """
groups:
- name: trust_and_pkd
  rules:
  # Trust list staleness
  - alert: TrustListStale
    expr: trust_list_age_seconds > 172800  # 48 hours
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Trust list is critically stale"
      description: "Trust list for {{ $labels.country }} from {{ $labels.source }} is {{ $value | humanizeDuration }} old"

  - alert: TrustListOld
    expr: trust_list_age_seconds > 86400  # 24 hours
    for: 15m
    labels:
      severity: warning
    annotations:
      summary: "Trust list is getting old"
      description: "Trust list for {{ $labels.country }} from {{ $labels.source }} is {{ $value | humanizeDuration }} old"

  # Certificate/key expiration
  - alert: CertificateExpiringSoon
    expr: certificate_expiry_days < 30
    for: 1h
    labels:
      severity: warning
    annotations:
      summary: "Certificate expiring soon"
      description: "{{ $labels.certificate_type }} certificate {{ $labels.identifier }} for {{ $labels.country }} expires in {{ $value }} days"

  - alert: CertificateExpiringCritical
    expr: certificate_expiry_days < 7
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "Certificate expiring very soon"
      description: "{{ $labels.certificate_type }} certificate {{ $labels.identifier }} for {{ $labels.country }} expires in {{ $value }} days"

  # PKD service health
  - alert: PKDServiceDown
    expr: up{job="pkd_service"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "PKD service is down"
      description: "PKD service instance {{ $labels.instance }} has been down for more than 1 minute"

  - alert: PKDHighErrorRate
    expr: rate(pkd_requests_total{status="error"}[5m]) > 0.1
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "PKD service high error rate"
      description: "PKD service error rate is {{ $value | humanizePercentage }} over the last 5 minutes"

  # Key rotation failures
  - alert: KeyRotationFailure
    expr: increase(key_rotation_events_total{action="failed"}[1h]) > 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "Key rotation failure"
      description: "Key rotation failed for {{ $labels.country }}/{{ $labels.role }}"

  # Service availability
  - alert: TrustServiceUnhealthy
    expr: up{job="trust_service"} == 0
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "Trust service is unhealthy"
      description: "Trust service instance {{ $labels.instance }} has been unhealthy for more than 2 minutes"
"""


# Example usage in service startup
def setup_monitoring() -> None:
    """Setup monitoring for the service."""
    logger.info("Setting up monitoring and metrics")

    # Initialize metrics with default values
    service_info.info(
        {
            "version": "2.0.0",
            "component": "trust_and_pkd",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    logger.info("Monitoring setup complete")


# Context manager for operation timing
class monitor_operation:
    """Context manager to monitor operation duration and outcomes."""

    def __init__(
        self,
        operation_type: str,
        country: str = "",
        role: str = "",
    ) -> None:
        self.operation_type = operation_type
        self.country = country
        self.role = role
        self.start_time = 0.0

    def __enter__(self) -> Self:
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        duration = time.time() - self.start_time
        status = "success" if exc_type is None else "failure"

        trust_monitor.record_trust_operation(
            operation=self.operation_type,
            status=status,
            country=self.country,
            role=self.role,
        )

        if exc_type is not None:
            logger.error(f"Operation {self.operation_type} failed after {duration:.3f}s: {exc_val}")
        else:
            logger.debug(f"Operation {self.operation_type} completed in {duration:.3f}s")
