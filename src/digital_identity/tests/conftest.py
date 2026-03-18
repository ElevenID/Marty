"""
Test Fixtures for Digital Identity Module

Provides pytest fixtures for testing Digital Identity services, repositories,
and API endpoints.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from uuid import uuid4

from sqlalchemy import JSON
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from digital_identity.infrastructure.persistence.models import Base
from digital_identity.infrastructure.persistence.database import (
    DigitalIdentityDatabaseConfig,
    DigitalIdentityDatabaseManager,
    set_database_manager,
)


# ============================================================================
# OrganizationModel is now defined in persistence/models.py — no stub needed
# ============================================================================

from digital_identity.infrastructure.adapters.events import InMemoryEventPublisher
from digital_identity.domain.entities import (
    TrustProfile,
    CredentialTemplate,
    PresentationPolicy,
    DeploymentProfile,
    Flow,
    FlowExecution,
)
from digital_identity.domain.value_objects import (
    TrustProfileType,
    FlowType,
    FlowStatus,
    ApprovalStrategy,
    ClaimDefinition,
    RevocationPolicy,
    TimePolicy,
)
from digital_identity.infrastructure.persistence.repositories import (
    TrustProfileRepository,
    CredentialTemplateRepository,
    PresentationPolicyRepository,
    DeploymentProfileRepository,
    FlowRepository,
    FlowExecutionRepository,
)
from digital_identity.application.services.trust_profile_service import TrustProfileService
from digital_identity.application.services.credential_template_service import CredentialTemplateService
from digital_identity.application.services.presentation_policy_service import PresentationPolicyService
from digital_identity.application.services.deployment_profile_service import DeploymentProfileService
from digital_identity.application.services.flow_service import FlowService


# ============================================================================
# Database Fixtures
# ============================================================================


@pytest.fixture
def db_config() -> DigitalIdentityDatabaseConfig:
    """Create test database configuration (in-memory SQLite)."""
    return DigitalIdentityDatabaseConfig(
        url="sqlite+aiosqlite:///:memory:",
        echo=False,
    )


@pytest_asyncio.fixture
async def db_engine(db_config: DigitalIdentityDatabaseConfig):
    """Create test database engine."""
    engine = create_async_engine(
        db_config.url,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        autoflush=False,
    )
    
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def db_manager(db_config: DigitalIdentityDatabaseConfig) -> AsyncGenerator[DigitalIdentityDatabaseManager, None]:
    """Create test database manager."""
    manager = DigitalIdentityDatabaseManager(db_config)
    
    # Override global manager for tests
    set_database_manager(manager)
    
    # Create tables
    await manager.create_all()
    
    yield manager
    
    # Cleanup
    await manager.dispose()
    set_database_manager(None)


# ============================================================================
# Event Publisher Fixtures
# ============================================================================


@pytest.fixture
def event_publisher() -> InMemoryEventPublisher:
    """Create in-memory event publisher for testing."""
    return InMemoryEventPublisher()


# ============================================================================
# Repository Fixtures
# ============================================================================


@pytest.fixture
def trust_profile_repository(db_session: AsyncSession) -> TrustProfileRepository:
    """Create TrustProfile repository."""
    return TrustProfileRepository(db_session)


@pytest.fixture
def credential_template_repository(db_session: AsyncSession) -> CredentialTemplateRepository:
    """Create CredentialTemplate repository."""
    return CredentialTemplateRepository(db_session)


@pytest.fixture
def presentation_policy_repository(db_session: AsyncSession) -> PresentationPolicyRepository:
    """Create PresentationPolicy repository."""
    return PresentationPolicyRepository(db_session)


@pytest.fixture
def deployment_profile_repository(db_session: AsyncSession) -> DeploymentProfileRepository:
    """Create DeploymentProfile repository."""
    return DeploymentProfileRepository(db_session)


@pytest.fixture
def flow_repository(db_session: AsyncSession) -> FlowRepository:
    """Create Flow repository."""
    return FlowRepository(db_session)


@pytest.fixture
def flow_execution_repository(db_session: AsyncSession) -> FlowExecutionRepository:
    """Create FlowExecution repository."""
    return FlowExecutionRepository(db_session)


# ============================================================================
# Service Fixtures
# ============================================================================


@pytest.fixture
def trust_profile_service(
    trust_profile_repository: TrustProfileRepository,
    event_publisher: InMemoryEventPublisher,
) -> TrustProfileService:
    """Create TrustProfile service with mock trust adapters."""
    from unittest.mock import AsyncMock

    # Provide stub adapters keyed by profile type so _adapter_for() resolves
    mock_adapters = {
        "ICAO": AsyncMock(name="icao_adapter"),
        "AAMVA": AsyncMock(name="aamva_adapter"),
        "EUDI": AsyncMock(name="eudi_adapter"),
        "CUSTOM": AsyncMock(name="custom_adapter"),
    }
    return TrustProfileService(
        repository=trust_profile_repository,
        event_publisher=event_publisher,
        trust_adapters=mock_adapters,
    )


@pytest.fixture
def credential_template_service(
    credential_template_repository: CredentialTemplateRepository,
    event_publisher: InMemoryEventPublisher,
) -> CredentialTemplateService:
    """Create CredentialTemplate service."""
    return CredentialTemplateService(
        repository=credential_template_repository,
        event_publisher=event_publisher,
    )


@pytest.fixture
def presentation_policy_service(
    presentation_policy_repository: PresentationPolicyRepository,
    event_publisher: InMemoryEventPublisher,
) -> PresentationPolicyService:
    """Create PresentationPolicy service."""
    return PresentationPolicyService(
        repository=presentation_policy_repository,
        event_publisher=event_publisher,
    )


@pytest.fixture
def deployment_profile_service(
    deployment_profile_repository: DeploymentProfileRepository,
    event_publisher: InMemoryEventPublisher,
) -> DeploymentProfileService:
    """Create DeploymentProfile service."""
    return DeploymentProfileService(
        repository=deployment_profile_repository,
        event_publisher=event_publisher,
    )


@pytest.fixture
def flow_service(
    flow_repository: FlowRepository,
    flow_execution_repository: FlowExecutionRepository,
    event_publisher: InMemoryEventPublisher,
) -> FlowService:
    """Create Flow service."""
    return FlowService(
        flow_repository=flow_repository,
        execution_repository=flow_execution_repository,
        event_publisher=event_publisher,
        step_registry=None,
        approval_strategies=None,
    )


@pytest.fixture
def artifact_service() -> IssuerArtifactService:
    """Create IssuerArtifact service with mock dependencies."""
    from digital_identity.application.services.issuer_artifact_service import IssuerArtifactService
    
    # Mock key vault client
    class MockKeyVaultClient:
        async def ensure_key(self, key_id: str, algorithm: str) -> None:
            pass
        
        async def key_exists(self, key_id: str) -> bool:
            return True
    
    # Mock key manager
    class MockKeyManager:
        def generate_key(self, algorithm: str) -> dict[str, str]:
            return {
                "did": f"did:key:mock_{algorithm}",
                "jwk": '{"kty": "EC", "crv": "P-256"}',
            }
    
    return IssuerArtifactService(
        key_vault=MockKeyVaultClient(),
        key_manager=MockKeyManager(),
    )


# ============================================================================
# Sample Entity Fixtures
# ============================================================================


@pytest.fixture
def sample_trust_profile() -> TrustProfile:
    """Create sample TrustProfile entity."""
    return TrustProfile(
        id=uuid4(),
        name="ICAO-PKI-Test",
        type=TrustProfileType.ICAO,
        description="Test ICAO trust profile",
        config={
            "trust_store_path": "/test/csca",
            "enable_crl_check": True,
        },
    )


@pytest.fixture
def sample_credential_template() -> CredentialTemplate:
    """Create sample CredentialTemplate entity."""
    return CredentialTemplate(
        id=uuid4(),
        name="mDL-Template-Test",
        credential_type="org.iso.18013.5.1.mDL",
        description="Test mobile driver's license template",
        claims=[
            ClaimDefinition(
                name="family_name",
                namespace="org.iso.18013.5.1",
                display_name="Family Name",
                mandatory=True,
                value_type="string",
            ),
            ClaimDefinition(
                name="given_name",
                namespace="org.iso.18013.5.1",
                display_name="Given Name",
                mandatory=True,
                value_type="string",
            ),
            ClaimDefinition(
                name="birth_date",
                namespace="org.iso.18013.5.1",
                display_name="Date of Birth",
                mandatory=True,
                value_type="full-date",
            ),
        ],
        trust_profile_id=None,
        revocation_policy=RevocationPolicy(
            enabled=True,
            method="status_list",
            update_frequency="daily",
        ),
        time_policy=TimePolicy(
            validity_period_days=365,
            not_before_offset_seconds=0,
            clock_skew_seconds=300,
        ),
    )


@pytest.fixture
def sample_presentation_policy() -> PresentationPolicy:
    """Create sample PresentationPolicy entity."""
    from digital_identity.domain.value_objects import RequiredClaim
    
    return PresentationPolicy(
        id=uuid4(),
        name="Age-Verification-Test",
        description="Test age verification policy",
        purpose="Age verification for testing",
        accepted_credential_types=["org.iso.18013.5.1.mDL"],
        required_claims=[
            RequiredClaim(
                claim_name="age_over_21",
                credential_type="org.iso.18013.5.1.mDL",
                accept_predicate=True,
            ),
        ],
        trust_profile_id=None,
    )


@pytest.fixture
def sample_deployment_profile() -> DeploymentProfile:
    """Create sample DeploymentProfile entity."""
    from digital_identity.domain.value_objects import NetworkMode, UXConfig
    
    return DeploymentProfile(
        id=uuid4(),
        name="Test-Deployment",
        description="Test deployment profile",
        environment="development",
        enabled_flow_ids=[],
        default_presentation_policy_id=None,
        network_mode=NetworkMode.ONLINE,
        ux_config=UXConfig(
            language="en",
            theme="default",
            show_operator_mode=False,
            accessibility_enabled=True,
        ),
    )


@pytest.fixture
def sample_flow() -> Flow:
    """Create sample Flow entity."""
    return Flow(
        id=uuid4(),
        name="Test-Issuance-Flow",
        flow_type=FlowType.ISSUANCE,
        description="Test credential issuance flow",
        deployment_profile_ids=[],
        hooks={
            "pre_step": {"document_scan": [{"action": "validate_country_support"}]},
            "post_step": {"biometric_capture": [{"action": "log_capture_quality"}]},
            "on_error": {"default": [{"action": "notify_admin"}]},
        },
        approval_strategy=ApprovalStrategy.AUTO,
    )


@pytest.fixture
def sample_flow_execution(sample_flow: Flow) -> FlowExecution:
    """Create sample FlowExecution entity."""
    return FlowExecution(
        id=uuid4(),
        flow_id=sample_flow.id,
        status=FlowStatus.PENDING,
        current_step=None,
        context={"subject_id": str(uuid4())},
        step_results={},
        error_message=None,
        started_at=None,
        completed_at=None,
    )


# ============================================================================
# API Test Fixtures (for FastAPI TestClient)
# ============================================================================


@pytest.fixture
def trust_profile_create_data() -> dict:
    """Sample data for creating a trust profile via API."""
    return {
        "name": "API-Test-Profile",
        "type": "ICAO",
        "description": "Created via API test",
        "config": {
            "trust_store_path": "/api/test/csca",
        },
    }


@pytest.fixture
def credential_template_create_data() -> dict:
    """Sample data for creating a credential template via API."""
    return {
        "name": "API-Test-Template",
        "credential_type": "test.credential.v1",
        "description": "Created via API test",
        "claims": [
            {
                "name": "test_claim",
                "namespace": "test.namespace",
                "display_name": "Test Claim",
                "mandatory": True,
                "value_type": "string",
            },
        ],
    }


@pytest.fixture
def presentation_policy_create_data() -> dict:
    """Sample data for creating a presentation policy via API."""
    return {
        "name": "API-Test-Policy",
        "description": "Created via API test",
        "required_credentials": [
            {
                "credential_type": "test.credential.v1",
                "formats": ["sd-jwt"],
            },
        ],
        "requested_claims": [
            {
                "name": "test_claim",
                "namespace": "test.namespace",
                "mandatory": False,
            },
        ],
    }


@pytest.fixture
def flow_create_data() -> dict:
    """Sample data for creating a flow via API."""
    return {
        "name": "API-Test-Flow",
        "flow_type": "ISSUANCE",
        "description": "Created via API test",
        "approval_strategy": "AUTO",
        "timeout_seconds": 1800,
    }
