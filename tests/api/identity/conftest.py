"""
Pytest fixtures for Identity API integration tests.

Provides fixtures for:
- Mock trust adapters
- Parameterized trust profile test data
- Event publisher mocks
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

# Import directly from value_objects module to avoid loading entire plugin
from digital_identity.domain.value_objects import TrustProfileType


@pytest.fixture
def mock_trust_adapter():
    """
    Mock trust adapter for external trust source fetching.
    
    Returns an AsyncMock that simulates trust anchor refresh without
    calling external services (ICAO PKD, AAMVA IACA, etc.).
    """
    adapter = AsyncMock()
    
    # Mock fetch_trust_anchors to return sample anchors
    adapter.fetch_trust_anchors.return_value = [
        {
            "id": str(uuid4()),
            "country_code": "US",
            "certificate": "-----BEGIN CERTIFICATE-----\nMOCK...\n-----END CERTIFICATE-----",
            "valid_from": "2024-01-01T00:00:00Z",
            "valid_until": "2026-12-31T23:59:59Z",
        }
    ]
    
    # Mock refresh_anchors to return success result
    adapter.refresh_anchors.return_value = Mock(
        success=True,
        anchors_updated=5,
        error=None,
    )
    
    return adapter


@pytest.fixture
def mock_event_publisher():
    """
    Mock event publisher for domain event testing.
    
    Use to verify that domain events are published during operations.
    """
    publisher = AsyncMock()
    publisher.publish.return_value = None
    publisher.published_events = []
    
    # Store published events for assertion
    async def capture_publish(event):
        publisher.published_events.append(event)
    
    publisher.publish.side_effect = capture_publish
    
    return publisher


@pytest.fixture(
    params=[
        TrustProfileType.ICAO,
        TrustProfileType.AAMVA,
        TrustProfileType.EUDI,
        TrustProfileType.CUSTOM,
    ]
)
def trust_profile_type(request) -> TrustProfileType:
    """
    Parameterized fixture providing all TrustProfileType values.
    
    Tests using this fixture will run 4 times, once for each profile type.
    """
    return request.param


@pytest.fixture
def trust_profile_payload(trust_profile_type: TrustProfileType) -> dict[str, Any]:
    """
    Generate valid trust profile creation payload based on profile type.
    
    Returns a dict matching TrustProfileCreate schema for the given type.
    """
    base_payload = {
        "name": f"Test {trust_profile_type.value.upper()} Profile {uuid4().hex[:8]}",
        "description": f"Test trust profile for {trust_profile_type.value}",
        "profile_type": trust_profile_type.value,
        "enabled": True,
        "allowed_algorithms": ["ES256", "ES384", "ES512"],
        "allowed_formats": ["sd_jwt_vc", "mdoc"],
        "metadata": {"test": True, "profile_type": trust_profile_type.value},
    }
    
    # Type-specific trust sources
    if trust_profile_type == TrustProfileType.ICAO:
        base_payload["trust_sources"] = [
            {
                "type": "pkd",
                "url": "https://pkddownloadsg.icao.int/",
                "country_filter": ["US", "CA", "GB"],
            }
        ]
    elif trust_profile_type == TrustProfileType.AAMVA:
        base_payload["trust_sources"] = [
            {
                "type": "iaca",
                "url": "https://iaca.aamva.org/",
                "jurisdiction_filter": ["US-CA", "US-NY"],
            }
        ]
    elif trust_profile_type == TrustProfileType.EUDI:
        base_payload["trust_sources"] = [
            {
                "type": "eudi_trust_list",
                "url": "https://eudi.europa.eu/trust-list",
                "member_state": "DE",
            }
        ]
    else:  # CUSTOM
        base_payload["trust_sources"] = [
            {
                "type": "x509_pinned",
                "certificates": ["-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----"],
            }
        ]
    
    # Revocation policy
    base_payload["revocation_policy"] = {
        "mode": "hard_fail",
        "check_ocsp": True,
        "check_crl": True,
        "check_status_list": True,
        "offline_grace_period_hours": 24,
        "cache_ttl_hours": 1,
    }
    
    # Time policy
    base_payload["time_policy"] = {
        "clock_skew_tolerance_seconds": 300,
        "max_credential_age_days": None,
        "require_not_before": True,
        "require_not_after": True,
    }
    
    return base_payload


@pytest.fixture
def sample_trust_profile_create() -> dict[str, Any]:
    """
    Simple non-parameterized trust profile payload for single tests.
    
    Use this when you don't need to test all profile types.
    """
    return {
        "name": f"Simple Test Profile {uuid4().hex[:8]}",
        "description": "Simple test trust profile",
        "profile_type": "custom",
        "enabled": True,
        "trust_sources": [
            {
                "type": "x509_pinned",
                "certificates": ["-----BEGIN CERTIFICATE-----\nMOCK\n-----END CERTIFICATE-----"],
            }
        ],
        "allowed_algorithms": ["ES256", "ES384"],
        "allowed_formats": ["sd_jwt_vc"],
        "revocation_policy": {
            "mode": "hard_fail",
            "check_ocsp": True,
            "check_crl": True,
            "check_status_list": True,
        },
        "time_policy": {
            "clock_skew_tolerance_seconds": 300,
            "require_not_before": True,
            "require_not_after": True,
        },
        "metadata": {"test": True},
    }


@pytest.fixture
async def authenticated_client_with_event_publisher(
    test_db_session,
    mock_auth_token,
    mock_event_publisher,
    mock_organization,
    mock_redis,
):
    """
    API client with authentication and event publisher mock.
    
    Use this fixture in tests that need to verify domain events.
    The mock_event_publisher is available and captures all published events.
    """
    from src.subscription.routes import router as subscription_router
    from src.subscription.routes import api_key_router, webhook_router
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from httpx import AsyncClient, ASGITransport
    
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
    except ImportError:
        pass
    
    # Override dependencies
    async def override_get_db():
        yield test_db_session
    
    async def override_get_current_organization():
        return mock_organization
    
    async def override_get_api_key_service():
        from src.subscription.api_key_service import APIKeyService
        return APIKeyService(test_db_session, mock_redis)
    
    async def override_get_db_session():
        yield test_db_session
    
    async def override_get_trust_profile_service_with_events():
        from digital_identity.infrastructure.persistence.repositories import TrustProfileRepository
        from digital_identity.application.services.trust_profile_service import TrustProfileService
        from unittest.mock import AsyncMock
        
        repository = TrustProfileRepository(test_db_session)
        
        # Create mock trust validation adapter for refresh testing
        trust_validation = AsyncMock()
        trust_validation.refresh_trust_data = AsyncMock(return_value={
            "success": True,
            "anchors_updated": 5,
            "error": None,
        })
        
        return TrustProfileService(
            repository=repository,
            event_publisher=mock_event_publisher,
            trust_validation=trust_validation,
        )
    
    # Use FastAPI's dependency_overrides
    from src.subscription.routes import get_current_organization, get_db, get_api_key_service
    
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_organization] = override_get_current_organization
    app.dependency_overrides[get_api_key_service] = override_get_api_key_service
    
    # Override digital identity dependencies
    try:
        from digital_identity.infrastructure.adapters.rest.dependencies import (
            get_db_session,
            get_trust_profile_service,
        )
        app.dependency_overrides[get_db_session] = override_get_db_session
        app.dependency_overrides[get_trust_profile_service] = override_get_trust_profile_service_with_events
    except ImportError:
        pass
    
    # Create client
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Set auth headers
        client.headers["Authorization"] = f"Bearer {mock_auth_token}"
        client.cookies.set("session", mock_auth_token)
        
        # Attach the mock for easy access in tests
        client.mock_event_publisher = mock_event_publisher
        
        yield client
