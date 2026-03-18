"""
Application Template Service

Application service for ApplicationTemplate CRUD.
"""

from __future__ import annotations

import logging
from typing import Any

from digital_identity.domain.entities import ApplicationTemplate
from digital_identity.domain.value_objects import (
    ApprovalStrategy,
    EvidenceRequirement,
    EvidenceType,
)

logger = logging.getLogger(__name__)


def _parse_evidence_requirements(raw: list[dict]) -> list[EvidenceRequirement]:
    """Convert list of dicts into EvidenceRequirement dataclasses."""
    result = []
    for item in raw:
        try:
            ev_type = EvidenceType(item.get("evidence_type", "DOCUMENT"))
        except ValueError:
            ev_type = EvidenceType.DOCUMENT
        result.append(
            EvidenceRequirement(
                evidence_type=ev_type,
                required=item.get("required", True),
                provider_config=item.get("provider_config", {}),
                description=item.get("description"),
                auto_validate=item.get("auto_validate", False),
            )
        )
    return result


class ApplicationTemplateService:
    """Service for Application Template management."""

    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(
        self,
        name: str,
        organization_id: str | None = None,
        description: str | None = None,
        status: str = "DRAFT",
        evidence_requirements: list[dict] | None = None,
        form_fields: list[dict] | None = None,
        claim_collection_rules: list[dict] | None = None,
        approval_strategy: str = "AUTO",
        application_validity_days: int = 30,
        notifications: dict[str, Any] | None = None,
        ui_config: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ApplicationTemplate:
        """Create a new Application Template."""
        template = ApplicationTemplate(
            name=name,
            organization_id=organization_id,
            description=description,
            status=status,
            evidence_requirements=_parse_evidence_requirements(
                evidence_requirements or []
            ),
            form_fields=form_fields or [],
            claim_collection_rules=claim_collection_rules or [],
            approval_strategy=ApprovalStrategy(approval_strategy),
            application_validity_days=application_validity_days,
            notifications=notifications or {},
            ui_config=ui_config or {},
            metadata=metadata or {},
        )

        saved = await self._repository.save(template)
        logger.info(f"Created Application Template: {saved.id} ({saved.name})")
        return saved

    async def get(self, template_id: str) -> ApplicationTemplate | None:
        """Get an Application Template by ID."""
        return await self._repository.get(template_id)

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        organization_id: str | None = None,
    ) -> list[ApplicationTemplate]:
        """List Application Templates with optional filters."""
        return await self._repository.list(
            skip=skip, limit=limit, organization_id=organization_id
        )

    async def update(
        self,
        template_id: str,
        **updates: Any,
    ) -> ApplicationTemplate | None:
        """Update an Application Template."""
        template = await self._repository.get(template_id)
        if not template:
            return None

        for key, value in updates.items():
            if value is None:
                continue
            if key == "approval_strategy":
                setattr(template, key, ApprovalStrategy(value))
            elif key == "evidence_requirements":
                setattr(template, key, _parse_evidence_requirements(value))
            elif hasattr(template, key):
                setattr(template, key, value)

        template.touch()
        saved = await self._repository.save(template)
        logger.info(f"Updated Application Template: {template_id}")
        return saved

    async def delete(self, template_id: str) -> bool:
        """Delete an Application Template."""
        if not await self._repository.exists(template_id):
            return False
        result = await self._repository.delete(template_id)
        logger.info(f"Deleted Application Template: {template_id}")
        return result
