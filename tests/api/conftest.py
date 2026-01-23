"""
Pytest fixtures for API integration tests.

Provides fixtures for:
- In-memory SQLite database with async support
- Mocked Keycloak authentication
- Async HTTP test client
- Common test data factories
"""
from __future__ import annotations

import os
from typing import AsyncGenerator, Optional
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy import text

# Mock settings for tests
TEST_SETTINGS = {
    "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    "REDIS_URL": "redis://localhost:6379/1",
    "KEYCLOAK_URL": "http://test-keycloak:8080",
    "KEYCLOAK_REALM": "test-realm",
    "SECRET_KEY": "test-secret-key-for-testing-only",
}


@pytest.fixture(scope="session")
def event_loop_policy():
    """Set event loop policy for async tests."""
    import asyncio
    return asyncio.get_event_loop_policy()


@pytest.fixture
async def test_db_engine():
    """Create in-memory SQLite database engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    
    # Enable foreign keys for SQLite
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        # Temporarily disable foreign keys for test setup
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()
    
    # Create all tables
    from src.subscription.models import Base as SubscriptionBase
    from digital_identity.infrastructure.persistence.models import Base as IdentityBase
    
    async with engine.begin() as conn:
        await conn.run_sync(SubscriptionBase.metadata.create_all)
        await conn.run_sync(IdentityBase.metadata.create_all)
    
    # Re-enable foreign keys after tables are created
    async with engine.connect() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.commit()
    
    yield engine
    
    await engine.dispose()


@pytest.fixture
async def test_db_session(test_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create isolated database session for each test.
    
    Automatically rolls back after each test to maintain isolation.
    """
    async_session_maker = async_sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session_maker() as session:
        yield session
        # Rollback happens automatically when the session is closed


@pytest.fixture
def mock_organization():
    """Mock organization for testing."""
    from src.subscription.models import Organization
    from datetime import datetime, timezone
    
    return Organization(
        id=uuid4(),
        name="Test Organization",
        slug="test-org",
        settings={},
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_user():
    """Mock authenticated user for testing."""
    return {
        "sub": "test-user-id",
        "email": "test@example.com",
        "email_verified": True,
        "name": "Test User",
        "preferred_username": "testuser",
        "given_name": "Test",
        "family_name": "User",
    }


@pytest.fixture
def mock_auth_token():
    """Mock JWT token for testing."""
    return "mock-jwt-token-for-testing"


@pytest.fixture
def authenticated_user_context(mock_user, mock_organization):
    """
    Mock authenticated user context with organization.
    
    Returns dict with user info and organization ID for dependency injection.
    """
    return {
        "user": mock_user,
        "organization_id": mock_organization.id,
        "organization": mock_organization,
        "roles": ["admin"],
    }


@pytest.fixture
def mock_keycloak():
    """Mock Keycloak client for authentication tests."""
    mock = AsyncMock()
    mock.userinfo.return_value = {
        "sub": "test-user-id",
        "email": "test@example.com",
        "email_verified": True,
        "name": "Test User",
    }
    mock.introspect.return_value = {
        "active": True,
        "sub": "test-user-id",
        "email": "test@example.com",
    }
    return mock


@pytest.fixture
def mock_redis():
    """Mock Redis client for session/cache tests."""
    mock = AsyncMock()
    mock.get.return_value = None
    mock.set.return_value = True
    mock.delete.return_value = True
    mock.exists.return_value = False
    return mock


@pytest.fixture
async def api_client(test_db_session, mock_organization, authenticated_user_context, mock_redis):
    """
    Async HTTP client for API integration tests.
    
    Automatically injects mocked auth and database dependencies.
    """
    from src.subscription.routes import router as subscription_router
    from src.subscription.routes import api_key_router, webhook_router
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    
    # Create test FastAPI app
    app = FastAPI(title="Marty API Test")
    
    # Add CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(subscription_router)
    app.include_router(api_key_router)
    app.include_router(webhook_router)
    
    # Include digital identity routers
    try:
        from digital_identity.infrastructure.adapters.rest.routers import (
            trust_profile_router,
            credential_template_router,
            presentation_policy_router,
            deployment_profile_router,
            lane_router,
            flow_router,
        )
        from digital_identity.infrastructure.adapters.rest.device_router import device_router
        
        app.include_router(trust_profile_router)
        app.include_router(credential_template_router)
        app.include_router(presentation_policy_router)
        app.include_router(deployment_profile_router)
        app.include_router(lane_router)
        app.include_router(flow_router)
        app.include_router(device_router)
    except ImportError as e:
        # Digital identity module may not be fully configured
        pass
    
    # Override dependencies
    async def override_get_db():
        yield test_db_session
    
    async def override_get_current_organization():
        return mock_organization
    
    async def override_get_api_key_service():
        from src.subscription.api_key_service import APIKeyService
        return APIKeyService(test_db_session, mock_redis)
    
    # Override digital identity dependencies
    async def override_get_db_session():
        yield test_db_session
    
    async def override_get_trust_profile_service():
        from digital_identity.infrastructure.persistence.repositories import TrustProfileRepository
        from digital_identity.application.services.trust_profile_service import TrustProfileService
        from unittest.mock import AsyncMock
        
        repository = TrustProfileRepository(test_db_session)
        # Create a simple mock event publisher for tests
        event_publisher = AsyncMock()
        event_publisher.publish = AsyncMock()
        
        # Create mock trust validation adapter for refresh testing
        trust_validation = AsyncMock()
        trust_validation.refresh_trust_data = AsyncMock(return_value={
            "success": True,
            "anchors_updated": 5,
            "error": None,
        })
        
        return TrustProfileService(
            repository=repository,
            event_publisher=event_publisher,
            trust_validation=trust_validation,
        )
    
    # Use FastAPI's dependency_overrides instead of patching
    from src.subscription.routes import get_current_organization, get_db, get_api_key_service
    
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_organization] = override_get_current_organization
    app.dependency_overrides[get_api_key_service] = override_get_api_key_service
    
    # Override digital identity dependencies if routers were loaded
    try:
        from digital_identity.infrastructure.adapters.rest.dependencies import (
            get_db_session,
            get_trust_profile_service,
        )
        app.dependency_overrides[get_db_session] = override_get_db_session
        app.dependency_overrides[get_trust_profile_service] = override_get_trust_profile_service
    except ImportError:
        pass
    
    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
async def authenticated_client(api_client, mock_auth_token):
    """
    API client with authentication headers set.
    
    Use this for testing authenticated endpoints.
    """
    api_client.headers["Authorization"] = f"Bearer {mock_auth_token}"
    api_client.cookies.set("session", mock_auth_token)
    return api_client


@pytest.fixture
def mock_square_service():
    """Mock Square payment service for subscription tests."""
    mock = AsyncMock()
    mock.create_subscription.return_value = Mock(
        id=uuid4(),
        plan="professional",
        status="active",
        api_calls_used=0,
        api_calls_limit=10000,
        current_period_start=None,
        current_period_end=None,
    )
    return mock


# Marker for API integration tests
def pytest_configure(config):
    """Register API integration test marker."""
    config.addinivalue_line(
        "markers",
        "api_integration: mark test as API integration test requiring database and HTTP client"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-mark API tests with api_integration marker."""
    for item in items:
        if "tests/api" in str(item.fspath):
            item.add_marker(pytest.mark.api_integration)
