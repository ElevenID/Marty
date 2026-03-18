"""Applicant Service — credential application lifecycle."""
from __future__ import annotations
import logging
from digital_identity.domain.entities import Applicant

logger = logging.getLogger(__name__)

class ApplicantService:
    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(self, organization_id: str, flow_id: str,
                     given_name: str, family_name: str, **kwargs) -> Applicant:
        applicant = Applicant(organization_id=organization_id, flow_id=flow_id,
                              given_name=given_name, family_name=family_name, **kwargs)
        saved = await self._repository.save(applicant)
        logger.info(f"Created Applicant: {saved.id}")
        return saved

    async def get(self, applicant_id: str) -> Applicant | None:
        return await self._repository.get(applicant_id)

    async def list(self, organization_id: str, flow_id: str | None = None,
                   status: str | None = None, skip: int = 0, limit: int = 100) -> list[Applicant]:
        return await self._repository.list(organization_id=organization_id,
                                           flow_id=flow_id, status=status, skip=skip, limit=limit)

    async def update(self, applicant_id: str, **kwargs) -> Applicant | None:
        applicant = await self._repository.get(applicant_id)
        if not applicant:
            return None
        for attr in ("credential_template_id", "user_id", "external_id",
                     "given_name", "family_name", "email", "phone", "status",
                     "reviewer_id", "reviewer_lock_expires_at", "submitted_at",
                     "reviewed_at", "approved_at", "credentialed_at",
                     "rejection_reason", "rejection_code", "application_data",
                     "issued_credential_id", "metadata"):
            if attr in kwargs:
                setattr(applicant, attr, kwargs[attr])
        applicant.touch()
        return await self._repository.save(applicant)

    async def delete(self, applicant_id: str) -> bool:
        return await self._repository.delete(applicant_id)
