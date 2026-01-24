"""
DRY Test Migration Example: PKD Service

This shows how to migrate from duplicated test configuration to DRY patterns
using the shared Marty testing infrastructure.
"""

import pytest

# Import service app
from app.main import app as pkd_app
from fastapi import FastAPI

# DRY: Import shared testing infrastructure
from marty_common.testing import (  # Core utilities; Enhanced fixtures; Service-specific config
    CommonTestData,
    MockFactory,
    PKDServiceTestConfig,
    ServiceHealthChecker,
    TempResourceManager,
    TestClientFactory,
    enhanced_test_environment,
    mock_service_dependencies,
    test_data_factory,
)

# Create test configuration instance
test_config = PKDServiceTestConfig()

# Export common fixtures (replaces manual fixture definitions)
app = test_config.app
client = test_config.client
authenticated_client = test_config.authenticated_client
unauthenticated_client = test_config.unauthenticated_client


# Service-specific fixtures (only define what's unique to this service)
@pytest.fixture
def sample_masterlist_data(test_data_factory):
    """Sample CSCA masterlist data for PKD testing."""
    return {
        "version": "1",
        "seqNumber": "1",
        "contents": [
            {"country": "USA", "certificates": [test_data_factory.create_test_certificate_data()]}
        ],
    }


@pytest.fixture
def sample_pkd_request():
    """Sample PKD API request data."""
    return {"country": "USA", "certificate_type": "csca", "format": "pem"}


@pytest.fixture
def mock_pkd_services(mock_service_dependencies):
    """Mock PKD-specific services."""
    services = mock_service_dependencies.copy()
    services.update(
        {
            "masterlist_service": MockFactory.create_async_mock(),
            "crl_service": MockFactory.create_async_mock(),
            "sync_service": MockFactory.create_async_mock(),
        }
    )
    return services


# Usage example in tests:
"""
def test_get_masterlist(client, sample_masterlist_data, mock_pkd_services):
    '''Test getting CSCA masterlist - using DRY fixtures.'''
    # No need to manually create client or mock services
    # All provided by shared infrastructure

    response = client.get("/v1/pkd/masterlist/USA")
    assert response.status_code == 200


def test_service_health(service_health_checker):
    '''Test service health check - using shared health checker.'''
    is_running = service_health_checker.is_service_running(
        service_name="pkd-service"
    )
    # Test logic here...


def test_with_temp_files(temp_resource_manager, test_data_factory):
    '''Test with temporary files - using shared temp management.'''
    temp_cert_file = temp_resource_manager.create_temp_file(
        suffix=".pem",
        content=test_data_factory.create_test_certificate_data()
    )
    # Test logic here...
    # Cleanup handled automatically
"""

# COMPARISON: Before vs After

BEFORE_CONFTEST = '''
"""
Traditional approach - lots of duplication
"""

import asyncio
import os
import sys
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Manual path setup (repeated in every service)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app as pkd_app

@pytest.fixture
def app() -> FastAPI:
    """Return the FastAPI app for testing"""
    return pkd_app

@pytest.fixture
def client(app: FastAPI) -> Generator:
    """Return a TestClient for interacting with the FastAPI app"""
    with TestClient(app) as client:
        # Manual API key setup (repeated in every service)
        client.headers.update({"X-API-Key": "test_api_key"})
        yield client

# Manual service mocks (repeated with variations in every service)
@pytest.fixture
def mock_masterlist_service():
    return MasterListService()

# Manual test data (repeated with variations in every service)
@pytest.fixture
def sample_certificate():
    return "MOCK_CERTIFICATE_DATA"

# 50+ lines of repetitive fixture code per service...
'''

AFTER_CONFTEST = '''
"""
DRY approach - minimal service-specific code
"""

from marty_common.testing import PKDServiceTestConfig, test_data_factory
from app.main import app as pkd_app

# Create test configuration instance
test_config = PKDServiceTestConfig()

# Export common fixtures (gets app, client, auth, mocks, etc.)
app = test_config.app
client = test_config.client
authenticated_client = test_config.authenticated_client

# Only define PKD-specific fixtures (3-5 lines vs 50+ lines)
@pytest.fixture
def sample_masterlist_data(test_data_factory):
    return test_data_factory.create_pkd_masterlist()
'''

print("DRY Test Infrastructure Benefits:")
print("- Reduced test configuration from ~94 to ~20 lines per service")
print("- Consistent test patterns across all services")
print("- Shared mocks, utilities, and health checks")
print("- Automatic cleanup and resource management")
print("- Easy to add new common test functionality")
print("- Service-specific tests focus on business logic, not setup")
