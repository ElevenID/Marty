"""Policy Set Service — Cedar policy collection management."""
from __future__ import annotations
import logging
from digital_identity.domain.entities import PolicySet

logger = logging.getLogger(__name__)

class PolicySetService:
    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(self, organization_id: str, name: str, policy_type: str,
                     cedar_policies: list, **kwargs) -> PolicySet:
        ps = PolicySet(organization_id=organization_id, name=name,
                       policy_type=policy_type, cedar_policies=cedar_policies, **kwargs)
        saved = await self._repository.save(ps)
        logger.info(f"Created PolicySet: {saved.id} ({saved.name})")
        return saved

    async def get(self, ps_id: str) -> PolicySet | None:
        return await self._repository.get(ps_id)

    async def list(self, organization_id: str, policy_type: str | None = None,
                   status: str | None = None, skip: int = 0, limit: int = 100) -> list[PolicySet]:
        return await self._repository.list(organization_id=organization_id,
                                           policy_type=policy_type, status=status, skip=skip, limit=limit)

    async def update(self, ps_id: str, **kwargs) -> PolicySet | None:
        ps = await self._repository.get(ps_id)
        if not ps:
            return None
        for attr in ("name", "description", "policy_type", "cedar_policies",
                     "cedar_schema_version", "status"):
            if attr in kwargs:
                setattr(ps, attr, kwargs[attr])
        ps.touch()
        return await self._repository.save(ps)

    async def delete(self, ps_id: str) -> bool:
        return await self._repository.delete(ps_id)
