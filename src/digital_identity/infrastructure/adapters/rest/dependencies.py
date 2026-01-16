"""
FastAPI Dependency Injection for Digital Identity API

Provides service instances for router endpoints.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from digital_identity.infrastructure.persistence.database import (
    get_database_manager,
    get_db_session as _get_db_session,
)

logger = logging.getLogger(__name__)


# Global holders for optional dependencies (set at application startup)
_event_publisher: Any | None = None
_trust_adapters: dict[str, Any] = {}
_step_registry: Any | None = None
_approval_strategy: Any | None = None


def configure_dependencies(
    event_publisher: Any | None = None,
    trust_adapters: dict[str, Any] | None = None,
    step_registry: Any | None = None,
    approval_strategy: Any | None = None,
) -> None:
    """
    Configure global dependencies for the Digital Identity module.
    
    Call this during application startup to inject dependencies.
    
    Args:
        event_publisher: Domain event publisher instance
        trust_adapters: Dict of trust profile type -> adapter instance
        step_registry: Flow step handler registry
        approval_strategy: Approval strategy implementation
    """
    global _event_publisher, _trust_adapters, _step_registry, _approval_strategy
    
    _event_publisher = event_publisher
    _trust_adapters = trust_adapters or {}
    _step_registry = step_registry
    _approval_strategy = approval_strategy
    
    logger.info(
        "Digital Identity dependencies configured: "
        f"event_publisher={event_publisher is not None}, "
        f"trust_adapters={list(_trust_adapters.keys())}, "
        f"step_registry={step_registry is not None}, "
        f"approval_strategy={approval_strategy is not None}"
    )


def get_event_publisher() -> Any | None:
    """Get configured event publisher."""
    return _event_publisher


def get_trust_adapter(profile_type: str) -> Any | None:
    """Get trust adapter for a specific profile type."""
    return _trust_adapters.get(profile_type)


def get_step_registry() -> Any | None:
    """Get flow step handler registry."""
    return _step_registry


def get_approval_strategy() -> Any | None:
    """Get approval strategy implementation."""
    return _approval_strategy


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session.
    
    Uses the Digital Identity database manager.
    """
    async for session in _get_db_session():
        yield session


# Service factories
# These create service instances with proper repository injection


async def get_trust_profile_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Trust Profile service instance."""
    from digital_identity.infrastructure.persistence.repositories import TrustProfileRepository
    from digital_identity.application.services.trust_profile_service import TrustProfileService
    
    repository = TrustProfileRepository(session)
    
    # Get configured trust adapter based on default profile type
    # Individual operations may use different adapters based on profile.type
    trust_adapter = get_trust_adapter("ICAO")  # Default to ICAO
    
    return TrustProfileService(
        repository=repository,
        event_publisher=get_event_publisher(),
        trust_adapter=trust_adapter,
    )


async def get_credential_template_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Credential Template service instance."""
    from digital_identity.infrastructure.persistence.repositories import CredentialTemplateRepository
    from digital_identity.application.services.credential_template_service import CredentialTemplateService
    
    repository = CredentialTemplateRepository(session)
    return CredentialTemplateService(
        repository=repository,
        event_publisher=get_event_publisher(),
    )


async def get_presentation_policy_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Presentation Policy service instance."""
    from digital_identity.infrastructure.persistence.repositories import PresentationPolicyRepository
    from digital_identity.application.services.presentation_policy_service import PresentationPolicyService
    
    repository = PresentationPolicyRepository(session)
    return PresentationPolicyService(
        repository=repository,
        event_publisher=get_event_publisher(),
    )


async def get_deployment_profile_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Deployment Profile service instance."""
    from digital_identity.infrastructure.persistence.repositories import DeploymentProfileRepository
    from digital_identity.application.services.deployment_profile_service import DeploymentProfileService
    
    repository = DeploymentProfileRepository(session)
    return DeploymentProfileService(
        repository=repository,
        event_publisher=get_event_publisher(),
    )


async def get_flow_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Flow service instance."""
    from digital_identity.infrastructure.persistence.repositories import (
        FlowRepository,
        FlowExecutionRepository,
    )
    from digital_identity.application.services.flow_service import FlowService
    
    flow_repository = FlowRepository(session)
    execution_repository = FlowExecutionRepository(session)
    
    return FlowService(
        flow_repository=flow_repository,
        execution_repository=execution_repository,
        event_publisher=get_event_publisher(),
        step_registry=get_step_registry(),
        approval_strategy=get_approval_strategy(),
    )
