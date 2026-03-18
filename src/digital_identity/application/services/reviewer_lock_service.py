"""Reviewer Lock Service — exclusive applicant review locks."""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from digital_identity.domain.entities import ReviewerLock

logger = logging.getLogger(__name__)

class ReviewerLockService:
    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def acquire(self, applicant_id: str, organization_id: str,
                      holder_user_id: str, ttl_seconds: int = 1800) -> ReviewerLock:
        existing = await self._repository.get_active_for_applicant(applicant_id)
        if existing:
            raise ValueError(f"Applicant '{applicant_id}' already locked by user '{existing.holder_user_id}'")
        now = datetime.now(timezone.utc)
        lock = ReviewerLock(
            applicant_id=applicant_id, organization_id=organization_id,
            holder_user_id=holder_user_id, ttl_seconds=ttl_seconds,
            expires_at=now + timedelta(seconds=ttl_seconds),
            status="ACTIVE",
        )
        saved = await self._repository.save(lock)
        logger.info(f"Acquired ReviewerLock: {saved.id} for applicant {applicant_id}")
        return saved

    async def get(self, lock_id: str) -> ReviewerLock | None:
        return await self._repository.get(lock_id)

    async def release(self, lock_id: str) -> ReviewerLock | None:
        lock = await self._repository.get(lock_id)
        if not lock or lock.status != "ACTIVE":
            return None
        lock.status = "RELEASED"
        lock.released_at = datetime.now(timezone.utc)
        return await self._repository.save(lock)

    async def delete(self, lock_id: str) -> bool:
        return await self._repository.delete(lock_id)
