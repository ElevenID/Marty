"""Issuance Record Service — OID4VCI offer lifecycle."""
from __future__ import annotations
import logging
from digital_identity.domain.entities import IssuanceRecord

logger = logging.getLogger(__name__)

class IssuanceRecordService:
    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(self, flow_id: str, credential_template_id: str, holder_id: str,
                     credential_format: str = "SD_JWT_VC", **kwargs) -> IssuanceRecord:
        record = IssuanceRecord(flow_id=flow_id, credential_template_id=credential_template_id,
                                holder_id=holder_id, credential_format=credential_format, **kwargs)
        saved = await self._repository.save(record)
        logger.info(f"Created IssuanceRecord: {saved.id}")
        return saved

    async def get(self, record_id: str) -> IssuanceRecord | None:
        return await self._repository.get(record_id)

    async def list(self, flow_id: str | None = None, holder_id: str | None = None,
                   status: str | None = None, skip: int = 0, limit: int = 100) -> list[IssuanceRecord]:
        return await self._repository.list(flow_id=flow_id, holder_id=holder_id, status=status, skip=skip, limit=limit)

    async def update(self, record_id: str, **kwargs) -> IssuanceRecord | None:
        record = await self._repository.get(record_id)
        if not record:
            return None
        for attr in ("status", "credential_id", "offer_uri", "offer_expires_at",
                     "revocation_index", "valid_from", "valid_until", "claimed_at",
                     "flow_execution_id", "application_id"):
            if attr in kwargs:
                setattr(record, attr, kwargs[attr])
        record.touch()
        return await self._repository.save(record)

    async def delete(self, record_id: str) -> bool:
        return await self._repository.delete(record_id)
