"""
Database Access Layer for Trust Services

SQLAlchemy async database operations for trust management.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg
from sqlalchemy import create_engine, delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import QueuePool

from .config import TrustServiceConfig
from .models import (
    CRLCache,
    DSCCertificate,
    IacaCertificate,
    JobExecution,
    RevocationStatus,
    RevokedCertificate,
    TrustAnchor,
    TrustSnapshot,
)

logger = logging.getLogger(__name__)

Base = declarative_base()


class DatabaseManager:
    """Async database manager for trust services."""

    def __init__(self, config: TrustServiceConfig):
        self.config = config
        self.engine = None
        self.session_factory = None

    async def initialize(self) -> None:
        """Initialize database connection and session factory."""
        try:
            self.engine = create_async_engine(
                self.config.database.connection_url,
                poolclass=QueuePool,
                pool_size=self.config.database.pool_size,
                max_overflow=self.config.database.max_overflow,
                echo=self.config.service.log_level == "DEBUG",
            )

            self.session_factory = async_sessionmaker(
                self.engine, class_=AsyncSession, expire_on_commit=False
            )

            # Test connection
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))

            logger.info("Database connection initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    async def close(self) -> None:
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connections closed")

    async def get_session(self) -> AsyncSession:
        """Get async database session."""
        if not self.session_factory:
            raise RuntimeError("Database not initialized")
        return self.session_factory()

    # Trust Anchor Operations
    async def get_trust_anchors(
        self, country_code: str | None = None, active_only: bool = True
    ) -> list[dict[str, Any]]:
        """Get trust anchors, optionally filtered by country."""
        async with self.get_session() as session:
            query = text(
                """
                SELECT * FROM trust_svc.trust_anchors
                WHERE (:country_code IS NULL OR country_code = :country_code)
                AND (:active_only = false OR status = 'active')
                AND (:active_only = false OR NOW() BETWEEN valid_from AND valid_to)
                ORDER BY country_code, created_at DESC
            """
            )

            result = await session.execute(
                query, {"country_code": country_code, "active_only": active_only}
            )
            return [dict(row) for row in result.fetchall()]

    async def add_trust_anchor(self, trust_anchor_data: dict[str, Any]) -> str:
        """Add a new trust anchor."""
        async with self.get_session() as session:
            query = text(
                """
                INSERT INTO trust_svc.trust_anchors
                (country_code, certificate_hash, certificate_data, subject_dn,
                 issuer_dn, serial_number, valid_from, valid_to, key_usage,
                 signature_algorithm, public_key_algorithm, trust_level, status)
                VALUES
                (:country_code, :certificate_hash, :certificate_data, :subject_dn,
                 :issuer_dn, :serial_number, :valid_from, :valid_to, :key_usage,
                 :signature_algorithm, :public_key_algorithm, :trust_level, :status)
                RETURNING id
            """
            )

            result = await session.execute(query, trust_anchor_data)
            trust_anchor_id = result.scalar()
            await session.commit()

            logger.info(
                f"Added trust anchor {trust_anchor_id} for {trust_anchor_data['country_code']}"
            )
            return trust_anchor_id

    # DSC Certificate Operations
    async def get_dsc_certificates(
        self,
        country_code: str | None = None,
        certificate_hash: str | None = None,
        revocation_status: RevocationStatus | None = None,
    ) -> list[dict[str, Any]]:
        """Get DSC certificates with optional filters."""
        async with self.get_session() as session:
            query = text(
                """
                SELECT dsc.*, ta.subject_dn as issuer_trust_anchor_dn
                FROM trust_svc.dsc_certificates dsc
                LEFT JOIN trust_svc.trust_anchors ta ON dsc.issuer_trust_anchor_id = ta.id
                WHERE (:country_code IS NULL OR dsc.country_code = :country_code)
                AND (:certificate_hash IS NULL OR dsc.certificate_hash = :certificate_hash)
                AND (:revocation_status IS NULL OR dsc.revocation_status = :revocation_status)
                ORDER BY dsc.country_code, dsc.created_at DESC
            """
            )

            result = await session.execute(
                query,
                {
                    "country_code": country_code,
                    "certificate_hash": certificate_hash,
                    "revocation_status": revocation_status.value if revocation_status else None,
                },
            )
            return [dict(row) for row in result.fetchall()]

    async def update_dsc_revocation_status(
        self,
        certificate_hash: str,
        revocation_status: RevocationStatus,
        revocation_date: datetime | None = None,
        reason_code: int | None = None,
        source: str = "CRL",
    ) -> bool:
        """Update DSC revocation status."""
        async with self.get_session() as session:
            query = text(
                """
                UPDATE trust_svc.dsc_certificates
                SET revocation_status = :revocation_status,
                    revocation_checked_at = NOW(),
                    revocation_date = :revocation_date,
                    revocation_reason = :reason_code,
                    crl_source = CASE WHEN :source = 'CRL' THEN :source ELSE crl_source END,
                    ocsp_source = CASE WHEN :source = 'OCSP' THEN :source ELSE ocsp_source END,
                    ocsp_checked_at = CASE WHEN :source = 'OCSP' THEN NOW() ELSE ocsp_checked_at END,
                    updated_at = NOW()
                WHERE certificate_hash = :certificate_hash
            """
            )

            result = await session.execute(
                query,
                {
                    "certificate_hash": certificate_hash,
                    "revocation_status": revocation_status.value,
                    "revocation_date": revocation_date,
                    "reason_code": reason_code,
                    "source": source,
                },
            )

            await session.commit()
            updated = result.rowcount > 0

            if updated:
                logger.info(
                    f"Updated revocation status for {certificate_hash}: {revocation_status.value}"
                )

            return updated

    # CRL Operations
    async def add_crl(self, crl_data: dict[str, Any]) -> str:
        """Add CRL to cache."""
        async with self.get_session() as session:
            query = text(
                """
                INSERT INTO trust_svc.crl_cache
                (issuer_dn, issuer_certificate_hash, crl_url, crl_number,
                 this_update, next_update, crl_data, crl_hash, signature_valid,
                 revoked_count, status)
                VALUES
                (:issuer_dn, :issuer_certificate_hash, :crl_url, :crl_number,
                 :this_update, :next_update, :crl_data, :crl_hash, :signature_valid,
                 :revoked_count, :status)
                RETURNING id
            """
            )

            result = await session.execute(query, crl_data)
            crl_id = result.scalar()
            await session.commit()

            logger.info(f"Added CRL {crl_id} for issuer {crl_data['issuer_dn']}")
            return crl_id

    async def get_active_crls(self, issuer_dn: str | None = None) -> list[dict[str, Any]]:
        """Get active CRLs."""
        async with self.get_session() as session:
            query = text(
                """
                SELECT * FROM trust_svc.crl_cache
                WHERE status = 'active'
                AND (:issuer_dn IS NULL OR issuer_dn = :issuer_dn)
                AND NOW() BETWEEN this_update AND next_update
                ORDER BY this_update DESC
            """
            )

            result = await session.execute(query, {"issuer_dn": issuer_dn})
            return [dict(row) for row in result.fetchall()]

    # Trust Snapshot Operations
    async def create_trust_snapshot(
        self,
        snapshot_hash: str,
        signature: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a new trust snapshot."""
        async with self.get_session() as session:
            # Get current counts
            counts_query = text(
                """
                SELECT
                    (SELECT COUNT(*) FROM trust_svc.trust_anchors WHERE status = 'active') as trust_anchor_count,
                    (SELECT COUNT(*) FROM trust_svc.dsc_certificates WHERE status = 'active') as dsc_count,
                    (SELECT COUNT(*) FROM trust_svc.revoked_certificates) as revoked_count,
                    (SELECT COUNT(*) FROM trust_svc.crl_cache WHERE status = 'active') as crl_count
            """
            )

            counts_result = await session.execute(counts_query)
            counts = counts_result.fetchone()

            query = text(
                """
                INSERT INTO trust_svc.trust_snapshots
                (snapshot_hash, signature, trust_anchor_count, dsc_count,
                 revoked_count, crl_count, metadata, expires_at)
                VALUES
                (:snapshot_hash, :signature, :trust_anchor_count, :dsc_count,
                 :revoked_count, :crl_count, :metadata, :expires_at)
                RETURNING id
            """
            )

            result = await session.execute(
                query,
                {
                    "snapshot_hash": snapshot_hash,
                    "signature": signature,
                    "trust_anchor_count": counts.trust_anchor_count,
                    "dsc_count": counts.dsc_count,
                    "revoked_count": counts.revoked_count,
                    "crl_count": counts.crl_count,
                    "metadata": metadata,
                    "expires_at": datetime.now(timezone.utc).replace(hour=23, minute=59, second=59),
                },
            )

            snapshot_id = result.scalar()
            await session.commit()

            logger.info(f"Created trust snapshot {snapshot_id}")
            return snapshot_id

    async def get_latest_snapshot(self) -> dict[str, Any] | None:
        """Get the latest trust snapshot."""
        async with self.get_session() as session:
            query = text(
                """
                SELECT * FROM trust_svc.trust_snapshots
                ORDER BY snapshot_time DESC
                LIMIT 1
            """
            )

            result = await session.execute(query)
            row = result.fetchone()
            return dict(row) if row else None

    # Job Execution Tracking
    async def start_job(
        self, job_name: str, job_type: str, metadata: dict[str, Any] | None = None
    ) -> str:
        """Start tracking a job execution."""
        async with self.get_session() as session:
            query = text(
                """
                INSERT INTO trust_svc.job_executions
                (job_name, job_type, status, metadata)
                VALUES
                (:job_name, :job_type, 'running', :metadata)
                RETURNING id
            """
            )

            result = await session.execute(
                query, {"job_name": job_name, "job_type": job_type, "metadata": metadata}
            )

            job_id = result.scalar()
            await session.commit()
            return job_id

    async def complete_job(
        self,
        job_id: str,
        status: str,
        records_processed: int = 0,
        errors_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Complete a job execution."""
        async with self.get_session() as session:
            query = text(
                """
                UPDATE trust_svc.job_executions
                SET status = :status,
                    completed_at = NOW(),
                    duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at))::INTEGER,
                    records_processed = :records_processed,
                    errors_count = :errors_count,
                    metadata = COALESCE(:metadata, metadata)
                WHERE id = :job_id
            """
            )

            await session.execute(
                query,
                {
                    "job_id": job_id,
                    "status": status,
                    "records_processed": records_processed,
                    "errors_count": errors_count,
                    "metadata": metadata,
                },
            )

            await session.commit()

    # Certificate Chain Validation
    async def validate_certificate_chain(self, certificate_hash: str) -> dict[str, Any]:
        """Validate certificate chain using database function."""
        async with self.get_session() as session:
            query = text(
                """
                SELECT * FROM trust_svc.check_certificate_chain(:certificate_hash)
            """
            )

            result = await session.execute(query, {"certificate_hash": certificate_hash})
            row = result.fetchone()

            return (
                {
                    "valid": row.valid,
                    "trust_anchor_id": row.trust_anchor_id,
                    "chain_length": row.chain_length,
                    "validation_errors": row.validation_errors,
                }
                if row
                else {"valid": False, "validation_errors": ["Certificate not found"]}
            )

    # IACA Certificate Operations (mDL / ISO 18013-5)
    async def get_iaca_certificates(
        self,
        jurisdiction: str | None = None,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Get IACA certificates, optionally filtered by jurisdiction."""
        async with self.get_session() as session:
            query = text(
                """
                SELECT * FROM trust_svc.iaca_certificates
                WHERE (:jurisdiction IS NULL OR jurisdiction = :jurisdiction)
                AND (:active_only = false OR status = 'active')
                AND (:active_only = false OR NOW() BETWEEN valid_from AND valid_to)
                ORDER BY jurisdiction, created_at DESC
            """
            )

            result = await session.execute(
                query, {"jurisdiction": jurisdiction, "active_only": active_only}
            )
            return [dict(row) for row in result.fetchall()]

    async def add_iaca_certificate(self, iaca_data: dict[str, Any]) -> str:
        """Add a new IACA certificate for mDL verification."""
        async with self.get_session() as session:
            query = text(
                """
                INSERT INTO trust_svc.iaca_certificates
                (jurisdiction, certificate_hash, certificate_data, subject_dn,
                 issuer_dn, serial_number, valid_from, valid_to, key_usage,
                 signature_algorithm, public_key_algorithm, vical_version,
                 vical_sequence, trust_level, status, source)
                VALUES
                (:jurisdiction, :certificate_hash, :certificate_data, :subject_dn,
                 :issuer_dn, :serial_number, :valid_from, :valid_to, :key_usage,
                 :signature_algorithm, :public_key_algorithm, :vical_version,
                 :vical_sequence, :trust_level, :status, :source)
                ON CONFLICT (certificate_hash) DO UPDATE
                SET vical_version = EXCLUDED.vical_version,
                    vical_sequence = EXCLUDED.vical_sequence,
                    status = EXCLUDED.status,
                    updated_at = NOW()
                RETURNING id
            """
            )

            result = await session.execute(query, iaca_data)
            iaca_id = result.scalar()
            await session.commit()

            logger.info(
                f"Added/updated IACA certificate {iaca_id} for {iaca_data['jurisdiction']}"
            )
            return iaca_id

    async def get_iaca_by_hash(self, certificate_hash: str) -> dict[str, Any] | None:
        """Get IACA certificate by hash."""
        async with self.get_session() as session:
            query = text(
                """
                SELECT * FROM trust_svc.iaca_certificates
                WHERE certificate_hash = :certificate_hash
            """
            )

            result = await session.execute(query, {"certificate_hash": certificate_hash})
            row = result.fetchone()
            return dict(row) if row else None

    async def update_iaca_status(
        self,
        certificate_hash: str,
        status: str,
    ) -> bool:
        """Update IACA certificate status."""
        async with self.get_session() as session:
            query = text(
                """
                UPDATE trust_svc.iaca_certificates
                SET status = :status,
                    updated_at = NOW()
                WHERE certificate_hash = :certificate_hash
            """
            )

            result = await session.execute(
                query, {"certificate_hash": certificate_hash, "status": status}
            )
            await session.commit()
            return result.rowcount > 0

    # Health Check
    async def health_check(self) -> bool:
        """Check database connectivity."""
        try:
            async with self.get_session() as session:
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
