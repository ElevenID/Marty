"""
Applicant Service Database Layer

Production-grade async database management for applicant vetting.
Supports both PostgreSQL (production) and SQLite (development/testing).
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import select, update, delete, and_, or_, func, desc
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .models import (
    Base,
    ApplicantRecord,
    ApplicationRecord,
    VettingCheckRecord,
    BiometricEnrollmentRecord,
    KYCSubmissionRecord,
    ApplicationAuditLog,
    ApplicationStatus,
    VettingCheckStatus,
    VettingCheckType,
    BiometricType,
    AuditEventType,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(slots=True)
class ApplicantDatabaseConfig:
    """Configuration for applicant service database connection."""

    url: str
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30

    @classmethod
    def from_env(cls) -> ApplicantDatabaseConfig:
        """Create configuration from environment variables."""
        db_url = os.environ.get(
            "APPLICANT_DB_URL",
            os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///data/applicants/applicants.db"),
        )
        
        # Convert postgres:// to postgresql+asyncpg://
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
        return cls(
            url=db_url,
            echo=bool(os.environ.get("DB_ECHO", "false").lower() == "true"),
            pool_size=int(os.environ.get("DB_POOL_SIZE", "10")),
            max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "20")),
            pool_timeout=int(os.environ.get("DB_POOL_TIMEOUT", "30")),
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ApplicantDatabaseConfig:
        """Create configuration from dictionary."""
        if "url" in raw:
            url = raw["url"]
        else:
            host = raw.get("host", "localhost")
            port = raw.get("port", 5432)
            name = raw.get("name", "marty_applicants")
            user = raw.get("user", "marty")
            password = raw.get("password", "marty")
            url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"
        return cls(
            url=url,
            echo=bool(raw.get("echo", False)),
            pool_size=int(raw.get("pool_size", 10)),
            max_overflow=int(raw.get("max_overflow", 20)),
            pool_timeout=int(raw.get("pool_timeout", 30)),
        )


class ApplicantDatabaseManager:
    """
    Async database session manager for applicant service.
    
    Provides:
    - Connection pooling with configurable parameters
    - Transaction management via session_scope
    - Schema initialization
    """

    def __init__(self, config: ApplicantDatabaseConfig | None = None) -> None:
        self._config = config or ApplicantDatabaseConfig.from_env()
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def create_engine(self) -> AsyncEngine:
        """Create or return cached async engine."""
        if self._engine is None:
            # Determine engine options based on driver
            connect_args = {}
            engine_kwargs: dict[str, Any] = {
                "echo": self._config.echo,
                "future": True,
            }
            
            # SQLite-specific settings
            if "sqlite" in self._config.url:
                # Ensure directory exists for SQLite
                if ":///" in self._config.url:
                    db_path = self._config.url.split(":///")[-1]
                    if db_path != ":memory:":
                        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
            else:
                # PostgreSQL pool settings
                engine_kwargs.update({
                    "pool_size": self._config.pool_size,
                    "max_overflow": self._config.max_overflow,
                    "pool_timeout": self._config.pool_timeout,
                })
            
            self._engine = create_async_engine(
                self._config.url,
                **engine_kwargs,
            )
        return self._engine

    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Create or return cached session factory."""
        if self._session_factory is None:
            engine = self.create_engine()
            self._session_factory = async_sessionmaker(
                engine,
                expire_on_commit=False,
                autoflush=False,
            )
        return self._session_factory

    async def create_all(self) -> None:
        """Create all database tables."""
        engine = self.create_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Applicant service database tables created")

    async def drop_all(self) -> None:
        """Drop all database tables. Use with caution!"""
        engine = self.create_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        logger.info("Applicant service database tables dropped")

    async def dispose(self) -> None:
        """Dispose of engine and close all connections."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    @asynccontextmanager
    async def session_scope(self) -> AsyncIterator[AsyncSession]:
        """
        Context manager for database sessions with automatic commit/rollback.
        
        Usage:
            async with db_manager.session_scope() as session:
                # perform database operations
                session.add(record)
        """
        session = self.session_factory()()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def run_within_transaction(
        self, handler: Callable[[AsyncSession], Awaitable[T]]
    ) -> T:
        """Run a function within a database transaction."""
        async with self.session_scope() as session:
            return await handler(session)


# Repository classes for each entity
class ApplicantRepository:
    """Repository for ApplicantRecord CRUD operations."""

    def __init__(self, db_manager: ApplicantDatabaseManager) -> None:
        self._db = db_manager

    async def create(self, applicant: ApplicantRecord) -> ApplicantRecord:
        """Create a new applicant record."""
        async with self._db.session_scope() as session:
            session.add(applicant)
            await session.flush()
            await session.refresh(applicant)
            return applicant

    async def get_by_id(self, applicant_id: UUID) -> ApplicantRecord | None:
        """Get applicant by ID."""
        async with self._db.session_scope() as session:
            return await session.get(ApplicantRecord, applicant_id)

    async def get_by_user_id(self, user_id: str) -> ApplicantRecord | None:
        """Get applicant by user account ID."""
        async with self._db.session_scope() as session:
            result = await session.execute(
                select(ApplicantRecord).where(ApplicantRecord.user_id == user_id)
            )
            return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> ApplicantRecord | None:
        """Get applicant by email address."""
        async with self._db.session_scope() as session:
            result = await session.execute(
                select(ApplicantRecord).where(ApplicantRecord.email == email)
            )
            return result.scalar_one_or_none()

    async def update(
        self, applicant_id: UUID, updates: dict[str, Any]
    ) -> ApplicantRecord | None:
        """Update an applicant record."""
        async with self._db.session_scope() as session:
            applicant = await session.get(ApplicantRecord, applicant_id)
            if applicant:
                for key, value in updates.items():
                    if hasattr(applicant, key):
                        setattr(applicant, key, value)
                applicant.updated_at = datetime.utcnow()
                await session.flush()
                await session.refresh(applicant)
            return applicant

    async def list_all(
        self,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ApplicantRecord], int]:
        """List applicants with optional filters."""
        async with self._db.session_scope() as session:
            query = select(ApplicantRecord)
            count_query = select(func.count(ApplicantRecord.id))
            
            if is_active is not None:
                query = query.where(ApplicantRecord.is_active == is_active)
                count_query = count_query.where(ApplicantRecord.is_active == is_active)
            
            # Get total count
            count_result = await session.execute(count_query)
            total = count_result.scalar() or 0
            
            # Get paginated results
            query = query.order_by(desc(ApplicantRecord.created_at))
            query = query.offset(offset).limit(limit)
            result = await session.execute(query)
            
            return list(result.scalars().all()), total


class ApplicationRepository:
    """Repository for ApplicationRecord CRUD operations."""

    def __init__(self, db_manager: ApplicantDatabaseManager) -> None:
        self._db = db_manager

    async def create(self, application: ApplicationRecord) -> ApplicationRecord:
        """Create a new application."""
        async with self._db.session_scope() as session:
            session.add(application)
            await session.flush()
            await session.refresh(application)
            return application

    async def get_by_id(self, application_id: UUID) -> ApplicationRecord | None:
        """Get application by ID."""
        async with self._db.session_scope() as session:
            return await session.get(ApplicationRecord, application_id)

    async def get_by_reference(self, reference_number: str) -> ApplicationRecord | None:
        """Get application by reference number."""
        async with self._db.session_scope() as session:
            result = await session.execute(
                select(ApplicationRecord).where(
                    ApplicationRecord.reference_number == reference_number
                )
            )
            return result.scalar_one_or_none()

    async def get_for_applicant(
        self,
        applicant_id: UUID,
        status: ApplicationStatus | None = None,
    ) -> list[ApplicationRecord]:
        """Get all applications for an applicant."""
        async with self._db.session_scope() as session:
            query = select(ApplicationRecord).where(
                ApplicationRecord.applicant_id == applicant_id
            )
            if status:
                query = query.where(ApplicationRecord.status == status)
            query = query.order_by(desc(ApplicationRecord.created_at))
            result = await session.execute(query)
            return list(result.scalars().all())

    async def update_status(
        self,
        application_id: UUID,
        new_status: ApplicationStatus,
        updated_by: str | None = None,
        rejection_reason: str | None = None,
    ) -> ApplicationRecord | None:
        """Update application status."""
        async with self._db.session_scope() as session:
            application = await session.get(ApplicationRecord, application_id)
            if application:
                application.status = new_status
                application.updated_at = datetime.utcnow()
                
                if new_status == ApplicationStatus.APPROVED:
                    application.approved_at = datetime.utcnow()
                    application.approved_by = updated_by
                elif new_status == ApplicationStatus.REJECTED:
                    application.rejection_reason = rejection_reason
                elif new_status == ApplicationStatus.ISSUED:
                    application.issued_at = datetime.utcnow()
                
                await session.flush()
                await session.refresh(application)
            return application

    async def list_all(
        self,
        status: ApplicationStatus | None = None,
        document_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ApplicationRecord], int]:
        """List applications with optional filters."""
        async with self._db.session_scope() as session:
            query = select(ApplicationRecord)
            count_query = select(func.count(ApplicationRecord.id))
            
            conditions = []
            if status:
                conditions.append(ApplicationRecord.status == status)
            if document_type:
                conditions.append(ApplicationRecord.document_type == document_type)
            
            if conditions:
                query = query.where(and_(*conditions))
                count_query = count_query.where(and_(*conditions))
            
            count_result = await session.execute(count_query)
            total = count_result.scalar() or 0
            
            query = query.order_by(desc(ApplicationRecord.created_at))
            query = query.offset(offset).limit(limit)
            result = await session.execute(query)
            
            return list(result.scalars().all()), total

    async def get_pending_review(self, limit: int = 50) -> list[ApplicationRecord]:
        """Get applications pending review."""
        async with self._db.session_scope() as session:
            result = await session.execute(
                select(ApplicationRecord)
                .where(
                    ApplicationRecord.status.in_([
                        ApplicationStatus.SUBMITTED,
                        ApplicationStatus.UNDER_REVIEW,
                        ApplicationStatus.PENDING_APPROVAL,
                    ])
                )
                .order_by(ApplicationRecord.submitted_at)
                .limit(limit)
            )
            return list(result.scalars().all())


class VettingCheckRepository:
    """Repository for VettingCheckRecord CRUD operations."""

    def __init__(self, db_manager: ApplicantDatabaseManager) -> None:
        self._db = db_manager

    async def create(self, check: VettingCheckRecord) -> VettingCheckRecord:
        """Create a new vetting check."""
        async with self._db.session_scope() as session:
            session.add(check)
            await session.flush()
            await session.refresh(check)
            return check

    async def create_many(self, checks: list[VettingCheckRecord]) -> list[VettingCheckRecord]:
        """Create multiple vetting checks."""
        async with self._db.session_scope() as session:
            session.add_all(checks)
            await session.flush()
            for check in checks:
                await session.refresh(check)
            return checks

    async def get_by_id(self, check_id: UUID) -> VettingCheckRecord | None:
        """Get vetting check by ID."""
        async with self._db.session_scope() as session:
            return await session.get(VettingCheckRecord, check_id)

    async def get_for_application(
        self, application_id: UUID
    ) -> list[VettingCheckRecord]:
        """Get all vetting checks for an application."""
        async with self._db.session_scope() as session:
            result = await session.execute(
                select(VettingCheckRecord)
                .where(VettingCheckRecord.application_id == application_id)
                .order_by(VettingCheckRecord.order)
            )
            return list(result.scalars().all())

    async def update_status(
        self,
        check_id: UUID,
        new_status: VettingCheckStatus,
        result: dict[str, Any] | None = None,
        notes: str | None = None,
        performed_by: str | None = None,
    ) -> VettingCheckRecord | None:
        """Update vetting check status."""
        async with self._db.session_scope() as session:
            check = await session.get(VettingCheckRecord, check_id)
            if check:
                check.status = new_status
                check.updated_at = datetime.utcnow()
                
                if new_status == VettingCheckStatus.IN_PROGRESS:
                    check.started_at = datetime.utcnow()
                elif new_status in [
                    VettingCheckStatus.PASSED,
                    VettingCheckStatus.FAILED,
                    VettingCheckStatus.REQUIRES_MANUAL_REVIEW,
                ]:
                    check.completed_at = datetime.utcnow()
                    check.performed_by = performed_by
                
                if result:
                    check.result = result
                if notes:
                    check.notes = notes
                
                await session.flush()
                await session.refresh(check)
            return check

    async def get_pending_checks(
        self, check_type: VettingCheckType | None = None, limit: int = 50
    ) -> list[VettingCheckRecord]:
        """Get pending vetting checks."""
        async with self._db.session_scope() as session:
            query = select(VettingCheckRecord).where(
                VettingCheckRecord.status == VettingCheckStatus.PENDING
            )
            if check_type:
                query = query.where(VettingCheckRecord.check_type == check_type)
            query = query.order_by(VettingCheckRecord.created_at).limit(limit)
            result = await session.execute(query)
            return list(result.scalars().all())


class BiometricEnrollmentRepository:
    """Repository for BiometricEnrollmentRecord CRUD operations."""

    def __init__(self, db_manager: ApplicantDatabaseManager) -> None:
        self._db = db_manager

    async def create(
        self, enrollment: BiometricEnrollmentRecord
    ) -> BiometricEnrollmentRecord:
        """Create a new biometric enrollment."""
        async with self._db.session_scope() as session:
            session.add(enrollment)
            await session.flush()
            await session.refresh(enrollment)
            return enrollment

    async def get_by_id(self, enrollment_id: UUID) -> BiometricEnrollmentRecord | None:
        """Get biometric enrollment by ID."""
        async with self._db.session_scope() as session:
            return await session.get(BiometricEnrollmentRecord, enrollment_id)

    async def get_for_applicant(
        self,
        applicant_id: UUID,
        biometric_type: BiometricType | None = None,
        is_active: bool = True,
    ) -> list[BiometricEnrollmentRecord]:
        """Get biometric enrollments for an applicant."""
        async with self._db.session_scope() as session:
            query = select(BiometricEnrollmentRecord).where(
                and_(
                    BiometricEnrollmentRecord.applicant_id == applicant_id,
                    BiometricEnrollmentRecord.is_active == is_active,
                )
            )
            if biometric_type:
                query = query.where(
                    BiometricEnrollmentRecord.biometric_type == biometric_type
                )
            query = query.order_by(desc(BiometricEnrollmentRecord.captured_at))
            result = await session.execute(query)
            return list(result.scalars().all())

    async def deactivate(self, enrollment_id: UUID) -> BiometricEnrollmentRecord | None:
        """Deactivate a biometric enrollment."""
        async with self._db.session_scope() as session:
            enrollment = await session.get(BiometricEnrollmentRecord, enrollment_id)
            if enrollment:
                enrollment.is_active = False
                enrollment.updated_at = datetime.utcnow()
                await session.flush()
                await session.refresh(enrollment)
            return enrollment

    async def update_verification(
        self,
        enrollment_id: UUID,
        verified: bool,
        score: float | None = None,
    ) -> BiometricEnrollmentRecord | None:
        """Update biometric verification status."""
        async with self._db.session_scope() as session:
            enrollment = await session.get(BiometricEnrollmentRecord, enrollment_id)
            if enrollment:
                enrollment.is_verified = verified
                enrollment.verification_score = score
                enrollment.last_verified_at = datetime.utcnow()
                enrollment.updated_at = datetime.utcnow()
                await session.flush()
                await session.refresh(enrollment)
            return enrollment


class KYCSubmissionRepository:
    """Repository for KYCSubmissionRecord CRUD operations."""

    def __init__(self, db_manager: ApplicantDatabaseManager) -> None:
        self._db = db_manager

    async def create(self, submission: KYCSubmissionRecord) -> KYCSubmissionRecord:
        """Create a new KYC submission."""
        async with self._db.session_scope() as session:
            session.add(submission)
            await session.flush()
            await session.refresh(submission)
            return submission

    async def get_by_id(self, submission_id: UUID) -> KYCSubmissionRecord | None:
        """Get KYC submission by ID."""
        async with self._db.session_scope() as session:
            return await session.get(KYCSubmissionRecord, submission_id)

    async def get_for_application(
        self, application_id: UUID
    ) -> list[KYCSubmissionRecord]:
        """Get all KYC submissions for an application."""
        async with self._db.session_scope() as session:
            result = await session.execute(
                select(KYCSubmissionRecord)
                .where(KYCSubmissionRecord.application_id == application_id)
                .order_by(desc(KYCSubmissionRecord.submitted_at))
            )
            return list(result.scalars().all())

    async def update_verification(
        self,
        submission_id: UUID,
        verified: bool,
        verified_by: str | None = None,
        notes: str | None = None,
    ) -> KYCSubmissionRecord | None:
        """Update KYC verification status."""
        async with self._db.session_scope() as session:
            submission = await session.get(KYCSubmissionRecord, submission_id)
            if submission:
                submission.is_verified = verified
                submission.verified_by = verified_by
                submission.verified_at = datetime.utcnow()
                if notes:
                    submission.verification_notes = notes
                submission.updated_at = datetime.utcnow()
                await session.flush()
                await session.refresh(submission)
            return submission


class ApplicationAuditRepository:
    """Repository for ApplicationAuditLog operations."""

    def __init__(self, db_manager: ApplicantDatabaseManager) -> None:
        self._db = db_manager

    async def create(self, audit_log: ApplicationAuditLog) -> ApplicationAuditLog:
        """Create a new audit log entry."""
        async with self._db.session_scope() as session:
            session.add(audit_log)
            await session.flush()
            await session.refresh(audit_log)
            return audit_log

    async def log_event(
        self,
        application_id: UUID,
        event_type: AuditEventType,
        actor_id: str,
        actor_type: str = "user",
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ApplicationAuditLog:
        """Create an audit log entry with simplified interface."""
        from uuid import uuid4
        
        audit_log = ApplicationAuditLog(
            id=uuid4(),
            application_id=application_id,
            event_type=event_type,
            actor_id=actor_id,
            actor_type=actor_type,
            timestamp=datetime.utcnow(),
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return await self.create(audit_log)

    async def get_for_application(
        self, application_id: UUID, limit: int = 100
    ) -> list[ApplicationAuditLog]:
        """Get audit logs for an application."""
        async with self._db.session_scope() as session:
            result = await session.execute(
                select(ApplicationAuditLog)
                .where(ApplicationAuditLog.application_id == application_id)
                .order_by(desc(ApplicationAuditLog.timestamp))
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_by_actor(
        self,
        actor_id: str,
        event_type: AuditEventType | None = None,
        limit: int = 100,
    ) -> list[ApplicationAuditLog]:
        """Get audit logs by actor."""
        async with self._db.session_scope() as session:
            query = select(ApplicationAuditLog).where(
                ApplicationAuditLog.actor_id == actor_id
            )
            if event_type:
                query = query.where(ApplicationAuditLog.event_type == event_type)
            query = query.order_by(desc(ApplicationAuditLog.timestamp)).limit(limit)
            result = await session.execute(query)
            return list(result.scalars().all())


# Global database manager instance (lazy initialization)
_db_manager: ApplicantDatabaseManager | None = None


def get_db_manager() -> ApplicantDatabaseManager:
    """Get or create the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = ApplicantDatabaseManager()
    return _db_manager


async def init_database(config: ApplicantDatabaseConfig | None = None) -> ApplicantDatabaseManager:
    """Initialize the applicant database."""
    global _db_manager
    _db_manager = ApplicantDatabaseManager(config)
    await _db_manager.create_all()
    logger.info("Applicant service database initialized")
    return _db_manager


async def close_database() -> None:
    """Close the database connection."""
    global _db_manager
    if _db_manager:
        await _db_manager.dispose()
        _db_manager = None
    logger.info("Applicant service database closed")
