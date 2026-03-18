"""Vetting Check Service — applicant verification checks."""
from __future__ import annotations
import logging
from digital_identity.domain.entities import VettingCheck

logger = logging.getLogger(__name__)

class VettingCheckService:
    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(self, applicant_id: str, organization_id: str,
                     check_type: str = "MANUAL_REVIEW", **kwargs) -> VettingCheck:
        vc = VettingCheck(applicant_id=applicant_id, organization_id=organization_id,
                          check_type=check_type, **kwargs)
        saved = await self._repository.save(vc)
        logger.info(f"Created VettingCheck: {saved.id} ({saved.check_type})")
        return saved

    async def get(self, check_id: str) -> VettingCheck | None:
        return await self._repository.get(check_id)

    async def list(self, applicant_id: str, status: str | None = None,
                   skip: int = 0, limit: int = 100) -> list[VettingCheck]:
        return await self._repository.list(applicant_id=applicant_id, status=status, skip=skip, limit=limit)

    async def update(self, check_id: str, **kwargs) -> VettingCheck | None:
        vc = await self._repository.get(check_id)
        if not vc:
            return None
        for attr in ("status", "score", "threshold", "failure_reason",
                     "evidence_refs", "performed_by", "started_at",
                     "completed_at", "expires_at", "raw_result"):
            if attr in kwargs:
                setattr(vc, attr, kwargs[attr])
        vc.touch()
        return await self._repository.save(vc)

    async def delete(self, check_id: str) -> bool:
        return await self._repository.delete(check_id)
