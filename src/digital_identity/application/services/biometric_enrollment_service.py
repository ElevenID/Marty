"""Biometric Enrollment Service — manage biometric data for applicants."""
from __future__ import annotations
import logging
from digital_identity.domain.entities import BiometricEnrollment

logger = logging.getLogger(__name__)

class BiometricEnrollmentService:
    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(self, applicant_id: str, organization_id: str,
                     modality: str = "FACE", **kwargs) -> BiometricEnrollment:
        enrollment = BiometricEnrollment(applicant_id=applicant_id,
                                          organization_id=organization_id,
                                          modality=modality, **kwargs)
        saved = await self._repository.save(enrollment)
        logger.info(f"Created BiometricEnrollment: {saved.id} ({saved.modality})")
        return saved

    async def get(self, enrollment_id: str) -> BiometricEnrollment | None:
        return await self._repository.get(enrollment_id)

    async def list(self, applicant_id: str, skip: int = 0,
                   limit: int = 100) -> list[BiometricEnrollment]:
        return await self._repository.list(applicant_id=applicant_id, skip=skip, limit=limit)

    async def update(self, enrollment_id: str, **kwargs) -> BiometricEnrollment | None:
        enrollment = await self._repository.get(enrollment_id)
        if not enrollment:
            return None
        for attr in ("status", "quality_score", "quality_threshold",
                     "failure_reason", "template_ref", "image_ref",
                     "liveness_result", "captured_at", "expires_at"):
            if attr in kwargs:
                setattr(enrollment, attr, kwargs[attr])
        enrollment.touch()
        return await self._repository.save(enrollment)

    async def delete(self, enrollment_id: str) -> bool:
        return await self._repository.delete(enrollment_id)
