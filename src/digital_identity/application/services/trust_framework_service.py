"""
Trust Framework Service

Application service for TrustFramework CRUD.
System-managed frameworks (is_system=True) are immutable.
"""

from __future__ import annotations

import logging
from typing import Any

from digital_identity.domain.entities import TrustFramework
from digital_identity.domain.value_objects import CryptoAlgorithm, CredentialFormat

logger = logging.getLogger(__name__)


class TrustFrameworkService:
    """Service for Trust Framework management."""

    def __init__(self, repository, event_publisher=None):
        self._repository = repository
        self._event_publisher = event_publisher

    async def create(
        self,
        code: str,
        display_name: str,
        default_algorithms: list[str],
        default_formats: list[str],
        is_system: bool = True,
        description: str | None = None,
        pkd_endpoints: dict[str, Any] | None = None,
        validation_ruleset: dict[str, Any] | None = None,
        sync_config: dict[str, Any] | None = None,
    ) -> TrustFramework:
        """Create a new Trust Framework."""
        existing = await self._repository.get_by_code(code)
        if existing:
            raise ValueError(f"Trust Framework with code '{code}' already exists")

        framework = TrustFramework(
            code=code,
            display_name=display_name,
            description=description,
            pkd_endpoints=pkd_endpoints or {},
            default_algorithms=[CryptoAlgorithm(a) for a in default_algorithms],
            default_formats=[CredentialFormat(f) for f in default_formats],
            validation_ruleset=validation_ruleset or {},
            sync_config=sync_config or {},
            is_system=is_system,
        )

        saved = await self._repository.save(framework)
        logger.info(f"Created Trust Framework: {saved.id} ({saved.code})")
        return saved

    async def get(self, framework_id: str) -> TrustFramework | None:
        """Get a Trust Framework by ID."""
        return await self._repository.get(framework_id)

    async def get_by_code(self, code: str) -> TrustFramework | None:
        """Get a Trust Framework by code."""
        return await self._repository.get_by_code(code)

    async def list(self, skip: int = 0, limit: int = 100) -> list[TrustFramework]:
        """List all Trust Frameworks."""
        return await self._repository.list(skip=skip, limit=limit)

    async def update(
        self,
        framework_id: str,
        **kwargs,
    ) -> TrustFramework | None:
        """Update a Trust Framework. System frameworks cannot be modified."""
        framework = await self._repository.get(framework_id)
        if not framework:
            return None

        if framework.is_system:
            raise ValueError("System Trust Frameworks cannot be modified")

        if "display_name" in kwargs:
            framework.display_name = kwargs["display_name"]
        if "description" in kwargs:
            framework.description = kwargs["description"]
        if "pkd_endpoints" in kwargs:
            framework.pkd_endpoints = kwargs["pkd_endpoints"]
        if "default_algorithms" in kwargs:
            framework.default_algorithms = [CryptoAlgorithm(a) for a in kwargs["default_algorithms"]]
        if "default_formats" in kwargs:
            framework.default_formats = [CredentialFormat(f) for f in kwargs["default_formats"]]
        if "validation_ruleset" in kwargs:
            framework.validation_ruleset = kwargs["validation_ruleset"]
        if "sync_config" in kwargs:
            framework.sync_config = kwargs["sync_config"]

        framework.touch()
        saved = await self._repository.save(framework)
        logger.info(f"Updated Trust Framework: {saved.id} ({saved.code})")
        return saved

    async def delete(self, framework_id: str) -> bool:
        """Delete a Trust Framework. System frameworks cannot be deleted."""
        framework = await self._repository.get(framework_id)
        if not framework:
            return False

        if framework.is_system:
            raise ValueError("System Trust Frameworks cannot be deleted")

        result = await self._repository.delete(framework_id)
        if result:
            logger.info(f"Deleted Trust Framework: {framework_id}")
        return result
