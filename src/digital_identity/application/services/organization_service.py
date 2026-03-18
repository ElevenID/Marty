"""
Organization Service

Application service for Organization CRUD.
"""

from __future__ import annotations

import logging

from digital_identity.domain.entities import Organization

logger = logging.getLogger(__name__)


class OrganizationService:
    """Service for Organization management."""

    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(
        self,
        name: str,
        display_name: str,
        owner_id: str,
        visibility: str = "PRIVATE",
        description: str | None = None,
        join_code: str | None = None,
    ) -> Organization:
        """Create a new Organization."""
        existing = await self._repository.get_by_name(name)
        if existing:
            raise ValueError(f"Organization with name '{name}' already exists")

        org = Organization(
            name=name,
            display_name=display_name,
            description=description,
            visibility=visibility,
            owner_id=owner_id,
            join_code=join_code,
            status="ACTIVE",
        )

        saved = await self._repository.save(org)
        logger.info(f"Created Organization: {saved.id} ({saved.name})")
        return saved

    async def get(self, org_id: str) -> Organization | None:
        """Get an Organization by ID."""
        return await self._repository.get(org_id)

    async def get_by_name(self, name: str) -> Organization | None:
        """Get an Organization by slug name."""
        return await self._repository.get_by_name(name)

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        status: str | None = None,
        visibility: str | None = None,
    ) -> list[Organization]:
        """List Organizations with optional filters."""
        return await self._repository.list(
            skip=skip, limit=limit, status=status, visibility=visibility,
        )

    async def update(
        self,
        org_id: str,
        **kwargs,
    ) -> Organization | None:
        """Update an Organization."""
        org = await self._repository.get(org_id)
        if not org:
            return None

        if org.status == "DELETED":
            raise ValueError("Cannot update a deleted Organization")

        if "display_name" in kwargs:
            org.display_name = kwargs["display_name"]
        if "description" in kwargs:
            org.description = kwargs["description"]
        if "visibility" in kwargs:
            org.visibility = kwargs["visibility"]
        if "owner_id" in kwargs:
            org.owner_id = kwargs["owner_id"]
        if "join_code" in kwargs:
            org.join_code = kwargs["join_code"]
        if "status" in kwargs:
            org.status = kwargs["status"]

        org.touch()
        saved = await self._repository.save(org)
        logger.info(f"Updated Organization: {saved.id}")
        return saved

    async def delete(self, org_id: str) -> bool:
        """Soft-delete an Organization by setting status to DELETED."""
        org = await self._repository.get(org_id)
        if not org:
            return False

        org.status = "DELETED"
        org.touch()
        await self._repository.save(org)
        logger.info(f"Soft-deleted Organization: {org_id}")
        return True
