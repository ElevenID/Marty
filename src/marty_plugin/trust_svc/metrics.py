"""
Prometheus Metrics for Trust Services

Exposes key metrics for monitoring trust service health and operations.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)

from .database import DatabaseManager


class TrustMetrics:
    """Prometheus metrics collector for trust services."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.registry = CollectorRegistry()

        # Service info
        self.service_info = Info(
            "trust_service_info", "Trust service information", registry=self.registry
        )

        # Master list metrics
        self.master_list_age_seconds = Gauge(
            "trust_master_list_age_seconds",
            "Age of master list in seconds",
            ["country"],
            registry=self.registry,
        )

        self.master_list_certificate_count = Gauge(
            "trust_master_list_certificate_count",
            "Number of certificates in master list",
            ["country"],
            registry=self.registry,
        )

        # CRL metrics
        self.crl_age_seconds = Gauge(
            "trust_crl_age_seconds", "Age of CRL in seconds", ["issuer"], registry=self.registry
        )

        self.crl_revoked_count = Gauge(
            "trust_crl_revoked_count",
            "Number of revoked certificates in CRL",
            ["issuer"],
            registry=self.registry,
        )

        # Certificate metrics
        self.trusted_dsc_total = Gauge(
            "trust_dsc_total",
            "Total number of DSC certificates",
            ["country", "status"],
            registry=self.registry,
        )

        self.trust_anchor_total = Gauge(
            "trust_anchor_total",
            "Total number of trust anchors",
            ["country", "status"],
            registry=self.registry,
        )

        # Trust snapshot metrics
        self.trust_snapshot_count = Gauge(
            "trust_snapshot_count", "Total number of trust snapshots", registry=self.registry
        )

        self.trust_snapshot_age_seconds = Gauge(
            "trust_snapshot_age_seconds",
            "Age of latest trust snapshot in seconds",
            registry=self.registry,
        )

        # Job execution metrics
        self.job_execution_duration_seconds = Histogram(
            "trust_job_execution_duration_seconds",
            "Job execution duration in seconds",
            ["job_name", "job_type"],
            registry=self.registry,
        )

        self.job_last_success_timestamp = Gauge(
            "trust_job_last_success_timestamp",
            "Timestamp of last successful job execution",
            ["job_name", "job_type"],
            registry=self.registry,
        )

        self.job_execution_total = Counter(
            "trust_job_execution_total",
            "Total number of job executions",
            ["job_name", "job_type", "status"],
            registry=self.registry,
        )

        # API metrics
        self.api_requests_total = Counter(
            "trust_api_requests_total",
            "Total number of API requests",
            ["method", "endpoint", "status_code"],
            registry=self.registry,
        )

        self.api_request_duration_seconds = Histogram(
            "trust_api_request_duration_seconds",
            "API request duration in seconds",
            ["method", "endpoint"],
            registry=self.registry,
        )

        # Database metrics
        self.database_connections = Gauge(
            "trust_database_connections",
            "Number of active database connections",
            registry=self.registry,
        )

        self.database_query_duration_seconds = Histogram(
            "trust_database_query_duration_seconds",
            "Database query duration in seconds",
            ["operation"],
            registry=self.registry,
        )

        # Set service info
        self.service_info.info(
            {
                "version": "1.0.0",
                "service": "trust-svc",
                "build_date": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def update_metrics(self) -> None:
        """Update all metrics from database."""
        try:
            await self._update_master_list_metrics()
            await self._update_crl_metrics()
            await self._update_certificate_metrics()
            await self._update_snapshot_metrics()
            await self._update_job_metrics()

        except Exception as e:
            # Log error but don't raise to avoid breaking metrics collection
            import logging

            logging.error(f"Failed to update metrics: {e}")

    async def _update_master_list_metrics(self) -> None:
        """Update master list related metrics."""
        async with self.db_manager.get_session() as session:
            from sqlalchemy import text

            query = text(
                """
                SELECT
                    country_code,
                    certificate_count,
                    EXTRACT(EPOCH FROM (NOW() - issue_date))::INTEGER as age_seconds
                FROM trust_svc.master_lists
                WHERE status = 'active'
                ORDER BY country_code, issue_date DESC
            """
            )

            result = await session.execute(query)

            # Clear existing metrics
            self.master_list_age_seconds.clear()
            self.master_list_certificate_count.clear()

            for row in result.fetchall():
                country = row.country_code or "GLOBAL"
                self.master_list_age_seconds.labels(country=country).set(row.age_seconds)
                self.master_list_certificate_count.labels(country=country).set(
                    row.certificate_count
                )

    async def _update_crl_metrics(self) -> None:
        """Update CRL related metrics."""
        async with self.db_manager.get_session() as session:
            from sqlalchemy import text

            query = text(
                """
                SELECT
                    issuer_dn,
                    revoked_count,
                    EXTRACT(EPOCH FROM (NOW() - this_update))::INTEGER as age_seconds
                FROM trust_svc.crl_cache
                WHERE status = 'active'
                AND NOW() BETWEEN this_update AND next_update
            """
            )

            result = await session.execute(query)

            # Clear existing metrics
            self.crl_age_seconds.clear()
            self.crl_revoked_count.clear()

            for row in result.fetchall():
                issuer = self._sanitize_label(row.issuer_dn)
                self.crl_age_seconds.labels(issuer=issuer).set(row.age_seconds)
                self.crl_revoked_count.labels(issuer=issuer).set(row.revoked_count)

    async def _update_certificate_metrics(self) -> None:
        """Update certificate related metrics."""
        async with self.db_manager.get_session() as session:
            from sqlalchemy import text

            # DSC metrics
            dsc_query = text(
                """
                SELECT
                    country_code,
                    revocation_status,
                    COUNT(*) as count
                FROM trust_svc.dsc_certificates
                WHERE status = 'active'
                GROUP BY country_code, revocation_status
            """
            )

            result = await session.execute(dsc_query)

            # Clear existing DSC metrics
            self.trusted_dsc_total.clear()

            for row in result.fetchall():
                self.trusted_dsc_total.labels(
                    country=row.country_code, status=row.revocation_status
                ).set(row.count)

            # Trust anchor metrics
            ta_query = text(
                """
                SELECT
                    country_code,
                    CASE
                        WHEN NOW() BETWEEN valid_from AND valid_to THEN 'valid'
                        WHEN NOW() > valid_to THEN 'expired'
                        ELSE 'not_yet_valid'
                    END as validity_status,
                    COUNT(*) as count
                FROM trust_svc.trust_anchors
                WHERE status = 'active'
                GROUP BY country_code, validity_status
            """
            )

            result = await session.execute(ta_query)

            # Clear existing trust anchor metrics
            self.trust_anchor_total.clear()

            for row in result.fetchall():
                self.trust_anchor_total.labels(
                    country=row.country_code, status=row.validity_status
                ).set(row.count)

    async def _update_snapshot_metrics(self) -> None:
        """Update trust snapshot metrics."""
        async with self.db_manager.get_session() as session:
            from sqlalchemy import text

            # Snapshot count
            count_query = text("SELECT COUNT(*) FROM trust_svc.trust_snapshots")
            result = await session.execute(count_query)
            snapshot_count = result.scalar()
            self.trust_snapshot_count.set(snapshot_count)

            # Latest snapshot age
            latest_query = text(
                """
                SELECT EXTRACT(EPOCH FROM (NOW() - snapshot_time))::INTEGER as age_seconds
                FROM trust_svc.trust_snapshots
                ORDER BY snapshot_time DESC
                LIMIT 1
            """
            )

            result = await session.execute(latest_query)
            row = result.fetchone()

            if row:
                self.trust_snapshot_age_seconds.set(row.age_seconds)
            else:
                self.trust_snapshot_age_seconds.set(-1)  # No snapshots

    async def _update_job_metrics(self) -> None:
        """Update job execution metrics."""
        async with self.db_manager.get_session() as session:
            from sqlalchemy import text

            # Latest successful job times
            latest_query = text(
                """
                SELECT
                    job_name,
                    job_type,
                    EXTRACT(EPOCH FROM MAX(completed_at))::INTEGER as last_success
                FROM trust_svc.job_executions
                WHERE status = 'completed'
                GROUP BY job_name, job_type
            """
            )

            result = await session.execute(latest_query)

            for row in result.fetchall():
                self.job_last_success_timestamp.labels(
                    job_name=row.job_name, job_type=row.job_type
                ).set(row.last_success)

    def record_api_request(
        self, method: str, endpoint: str, status_code: int, duration: float
    ) -> None:
        """Record API request metrics."""
        self.api_requests_total.labels(
            method=method, endpoint=endpoint, status_code=str(status_code)
        ).inc()

        self.api_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)

    def record_job_execution(
        self, job_name: str, job_type: str, status: str, duration: float | None = None
    ) -> None:
        """Record job execution metrics."""
        self.job_execution_total.labels(job_name=job_name, job_type=job_type, status=status).inc()

        if duration is not None:
            self.job_execution_duration_seconds.labels(
                job_name=job_name, job_type=job_type
            ).observe(duration)

    def record_database_query(self, operation: str, duration: float) -> None:
        """Record database query metrics."""
        self.database_query_duration_seconds.labels(operation=operation).observe(duration)

    def set_database_connections(self, count: int) -> None:
        """Set current database connection count."""
        self.database_connections.set(count)

    def get_metrics_text(self) -> str:
        """Get metrics in Prometheus text format."""
        return generate_latest(self.registry).decode("utf-8")

    def get_content_type(self) -> str:
        """Get content type for metrics endpoint."""
        return CONTENT_TYPE_LATEST

    @staticmethod
    def _sanitize_label(value: str) -> str:
        """Sanitize label value for Prometheus."""
        # Replace problematic characters
        sanitized = value.replace('"', "").replace("\n", " ").replace("\r", " ")
        # Truncate if too long
        if len(sanitized) > 100:
            sanitized = sanitized[:97] + "..."
        return sanitized


# Global metrics instance
metrics: TrustMetrics | None = None


def initialize_metrics(db_manager: DatabaseManager) -> TrustMetrics:
    """Initialize global metrics instance."""
    global metrics
    metrics = TrustMetrics(db_manager)
    return metrics


def get_metrics() -> TrustMetrics | None:
    """Get global metrics instance."""
    return metrics
