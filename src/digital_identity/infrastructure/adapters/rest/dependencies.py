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
    
    return TrustProfileService(
        repository=repository,
        event_publisher=get_event_publisher(),
        trust_adapters=_trust_adapters,
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


async def get_lane_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Lane service instance."""
    from digital_identity.infrastructure.persistence.repositories import DeploymentProfileRepository
    from digital_identity.application.services.lane_service import LaneService
    
    repository = DeploymentProfileRepository(session)
    return LaneService(
        deployment_profile_repository=repository,
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


async def get_custom_anchor_repository(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Custom Anchor repository instance."""
    from digital_identity.infrastructure.persistence.repositories import CustomAnchorRepository
    
    return CustomAnchorRepository(session)


async def get_issuer_registry_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Issuer Registry service instance."""
    from digital_identity.infrastructure.persistence.repositories import (
        IssuerRepository,
        TrustProfileIssuerRepository,
        CascadeRevocationOperationRepository,
        IssuedCredentialRepository,
    )
    from digital_identity.application.services.issuer_registry_service import IssuerRegistryService
    
    issuer_repo = IssuerRepository(session)
    tp_issuer_repo = TrustProfileIssuerRepository(session)
    cascade_repo = CascadeRevocationOperationRepository(session)
    credential_repo = IssuedCredentialRepository(session)
    
    return IssuerRegistryService(
        issuer_repository=issuer_repo,
        trust_profile_issuer_repository=tp_issuer_repo,
        cascade_operation_repository=cascade_repo,
        credential_repository=credential_repo,
        event_publisher=get_event_publisher(),
    )


async def get_revocation_profile_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Revocation Profile service instance."""
    from digital_identity.infrastructure.persistence.repositories import RevocationProfileRepository
    from digital_identity.application.services.revocation_profile_service import RevocationProfileService

    repository = RevocationProfileRepository(session)
    return RevocationProfileService(
        repository=repository,
        event_publisher=get_event_publisher(),
    )


async def get_application_template_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Application Template service instance."""
    from digital_identity.infrastructure.persistence.repositories import ApplicationTemplateRepository
    from digital_identity.application.services.application_template_service import ApplicationTemplateService

    repository = ApplicationTemplateRepository(session)
    return ApplicationTemplateService(
        repository=repository,
        event_publisher=get_event_publisher(),
    )


async def get_verification_session_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Verification Session service instance."""
    from digital_identity.infrastructure.persistence.repositories import VerificationSessionRepository
    from digital_identity.application.services.verification_session_service import VerificationSessionService

    repository = VerificationSessionRepository(session)
    return VerificationSessionService(
        repository=repository,
        event_publisher=get_event_publisher(),
    )


async def get_compliance_profile_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Compliance Profile service instance."""
    from digital_identity.infrastructure.persistence.repositories import ComplianceProfileRepository
    from digital_identity.application.services.compliance_profile_service import ComplianceProfileService

    repository = ComplianceProfileRepository(session)
    return ComplianceProfileService(
        repository=repository,
        event_publisher=get_event_publisher(),
    )


async def get_trust_framework_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Trust Framework service instance."""
    from digital_identity.infrastructure.persistence.repositories import TrustFrameworkRepository
    from digital_identity.application.services.trust_framework_service import TrustFrameworkService

    repository = TrustFrameworkRepository(session)
    return TrustFrameworkService(
        repository=repository,
        event_publisher=get_event_publisher(),
    )


async def get_organization_trust_profile_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Organization Trust Profile service instance."""
    from digital_identity.infrastructure.persistence.repositories import (
        OrganizationTrustProfileRepository,
        TrustFrameworkRepository,
    )
    from digital_identity.application.services.organization_trust_profile_service import OrganizationTrustProfileService

    repository = OrganizationTrustProfileRepository(session)
    framework_repository = TrustFrameworkRepository(session)
    return OrganizationTrustProfileService(
        repository=repository,
        framework_repository=framework_repository,
        event_publisher=get_event_publisher(),
    )


async def get_organization_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Organization service instance."""
    from digital_identity.infrastructure.persistence.repositories import OrganizationRepository
    from digital_identity.application.services.organization_service import OrganizationService

    repository = OrganizationRepository(session)
    return OrganizationService(
        repository=repository,
        event_publisher=get_event_publisher(),
    )


async def get_webhook_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Webhook service instance."""
    from digital_identity.infrastructure.persistence.repositories import WebhookRepository
    from digital_identity.application.services.webhook_service import WebhookService

    repository = WebhookRepository(session)
    return WebhookService(
        repository=repository,
        event_publisher=get_event_publisher(),
    )


async def get_subscription_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get Subscription service instance."""
    from digital_identity.infrastructure.persistence.repositories import SubscriptionRepository
    from digital_identity.application.services.subscription_service import SubscriptionService

    repository = SubscriptionRepository(session)
    return SubscriptionService(
        repository=repository,
        event_publisher=get_event_publisher(),
    )


async def get_api_key_service(
    session: AsyncSession = Depends(get_db_session),
):
    """Get API Key service instance."""
    from digital_identity.infrastructure.persistence.repositories import ApiKeyRepository
    from digital_identity.application.services.api_key_service import ApiKeyService

    repository = ApiKeyRepository(session)
    return ApiKeyService(
        repository=repository,
        event_publisher=get_event_publisher(),
    )


async def get_issuance_record_service(
    session: AsyncSession = Depends(get_db_session),
):
    from digital_identity.infrastructure.persistence.repositories import IssuanceRecordRepository
    from digital_identity.application.services.issuance_record_service import IssuanceRecordService

    return IssuanceRecordService(
        repository=IssuanceRecordRepository(session),
        event_publisher=get_event_publisher(),
    )


async def get_policy_set_service(
    session: AsyncSession = Depends(get_db_session),
):
    from digital_identity.infrastructure.persistence.repositories import PolicySetRepository
    from digital_identity.application.services.policy_set_service import PolicySetService

    return PolicySetService(
        repository=PolicySetRepository(session),
        event_publisher=get_event_publisher(),
    )


async def get_wallet_profile_service(
    session: AsyncSession = Depends(get_db_session),
):
    from digital_identity.infrastructure.persistence.repositories import WalletProfileRepository
    from digital_identity.application.services.wallet_profile_service import WalletProfileService

    return WalletProfileService(
        repository=WalletProfileRepository(session),
        event_publisher=get_event_publisher(),
    )


async def get_device_registration_service(
    session: AsyncSession = Depends(get_db_session),
):
    from digital_identity.infrastructure.persistence.repositories import DeviceRegistrationRepository
    from digital_identity.application.services.device_registration_service import DeviceRegistrationService

    return DeviceRegistrationService(
        repository=DeviceRegistrationRepository(session),
        event_publisher=get_event_publisher(),
    )


async def get_applicant_service(
    session: AsyncSession = Depends(get_db_session),
):
    from digital_identity.infrastructure.persistence.repositories import ApplicantRepository
    from digital_identity.application.services.applicant_service import ApplicantService

    return ApplicantService(
        repository=ApplicantRepository(session),
        event_publisher=get_event_publisher(),
    )


async def get_reviewer_lock_service(
    session: AsyncSession = Depends(get_db_session),
):
    from digital_identity.infrastructure.persistence.repositories import ReviewerLockRepository
    from digital_identity.application.services.reviewer_lock_service import ReviewerLockService

    return ReviewerLockService(
        repository=ReviewerLockRepository(session),
        event_publisher=get_event_publisher(),
    )


async def get_vetting_check_service(
    session: AsyncSession = Depends(get_db_session),
):
    from digital_identity.infrastructure.persistence.repositories import VettingCheckRepository
    from digital_identity.application.services.vetting_check_service import VettingCheckService

    return VettingCheckService(
        repository=VettingCheckRepository(session),
        event_publisher=get_event_publisher(),
    )


async def get_biometric_enrollment_service(
    session: AsyncSession = Depends(get_db_session),
):
    from digital_identity.infrastructure.persistence.repositories import BiometricEnrollmentRepository
    from digital_identity.application.services.biometric_enrollment_service import BiometricEnrollmentService

    return BiometricEnrollmentService(
        repository=BiometricEnrollmentRepository(session),
        event_publisher=get_event_publisher(),
    )


async def get_notification_payload_service(
    session: AsyncSession = Depends(get_db_session),
):
    from digital_identity.infrastructure.persistence.repositories import NotificationPayloadRepository
    from digital_identity.application.services.notification_payload_service import NotificationPayloadService

    return NotificationPayloadService(
        repository=NotificationPayloadRepository(session),
        event_publisher=get_event_publisher(),
    )
