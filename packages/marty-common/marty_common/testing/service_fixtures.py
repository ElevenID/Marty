"""
Enhanced test fixtures and utilities integrating with existing infrastructure.

This module extends the marty_common.testing infrastructure to provide
DRY patterns for service-specific test configurations.
"""

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from marty_common.testing.test_utilities import (
    CommonTestData,
    MockFactory,
    ServiceHealthChecker,
    TempResourceManager,
    TestClientFactory,
)


class ServiceTestMixin:
    """Base mixin for service test configurations."""

    @staticmethod
    def setup_service_paths(service_name: str) -> dict[str, Path]:
        """Set up standard paths for a service test suite."""
        current_dir = Path.cwd()

        # Navigate up to find service root
        service_root = current_dir
        while service_root.name != service_name and service_root.parent != service_root:
            service_root = service_root.parent

        project_root = service_root.parent.parent  # assuming src/service_name structure

        return {
            "service_root": service_root,
            "project_root": project_root,
            "test_dir": service_root / "tests",
            "app_dir": service_root / "app",
            "data_dir": service_root / "tests" / "data",
            "fixtures_dir": service_root / "tests" / "fixtures",
        }


class FastAPIServiceTestConfig(ServiceTestMixin):
    """Test configuration for FastAPI services with DRY patterns."""

    def __init__(self, service_name: str, app_module_path: str) -> None:
        self.service_name = service_name
        self.app_module_path = app_module_path
        self.paths = self.setup_service_paths(service_name)

    @pytest.fixture
    def app(self) -> FastAPI:
        """Import and return the FastAPI app for testing."""
        # Dynamic import of the service app
        module_parts = self.app_module_path.split(".")
        module = __import__(self.app_module_path, fromlist=[module_parts[-1]])
        return module.app

    @pytest.fixture
    def client(self, app: FastAPI) -> Generator[TestClient, None, None]:
        """Create a test client with API key authentication."""
        with TestClientFactory.create_fastapi_client(app) as client:
            yield client

    @pytest.fixture
    def authenticated_client(self, app: FastAPI) -> Generator[TestClient, None, None]:
        """Create an authenticated test client."""
        with TestClientFactory.create_fastapi_client(app, "valid_test_key") as client:
            yield client

    @pytest.fixture
    def unauthenticated_client(self, app: FastAPI) -> Generator[TestClient, None, None]:
        """Create a client without authentication headers."""
        with TestClient(app) as client:
            yield client


def create_service_test_config(service_name: str, app_module_path: str) -> type:
    """Factory function to create a test configuration class for a service."""

    class ServiceTestConfig(FastAPIServiceTestConfig):
        def __init__(self) -> None:
            super().__init__(service_name, app_module_path)

    return ServiceTestConfig


# Pre-configured test configurations for known services
class PKDServiceTestConfig(FastAPIServiceTestConfig):
    """Test configuration for PKD service."""

    def __init__(self) -> None:
        super().__init__("pkd_service", "app.main")


class DocumentProcessingTestConfig(FastAPIServiceTestConfig):
    """Test configuration for Document Processing service."""

    def __init__(self) -> None:
        super().__init__("document_processing", "app.main")


# Enhanced fixtures that combine common patterns
@pytest.fixture
def enhanced_test_environment(
    temp_resource_manager: TempResourceManager,
    common_test_data: CommonTestData,
    service_health_checker: ServiceHealthChecker,
) -> dict[str, Any]:
    """Provide a complete test environment with all utilities."""
    return {
        "temp_manager": temp_resource_manager,
        "test_data": common_test_data,
        "health_checker": service_health_checker,
        "mock_factory": MockFactory(),
    }


@pytest.fixture
def mock_service_dependencies() -> dict[str, Any]:
    """Provide commonly mocked service dependencies."""
    return {
        "database": MockFactory.create_async_mock(),
        "cache": MockFactory.create_async_mock(),
        "grpc_service": MockFactory.create_grpc_service_mock(),
        "external_api": MockFactory.create_async_mock(),
    }


# Service-specific test data factories
class TestDataFactory:
    """Factory for creating service-specific test data."""

    @staticmethod
    def create_test_passport_data() -> dict[str, Any]:
        """Create test passport data."""
        return {
            "mrz_line1": "P<USADOE<<JOHN<<<<<<<<<<<<<<<<<<<<<<<<<<<<",
            "mrz_line2": "1234567890USA9001014M3001014<<<<<<<<<<<<<<<",
            "document_number": "123456789",
            "country_code": "USA",
            "surname": "DOE",
            "given_names": "JOHN",
        }

    @staticmethod
    def create_test_certificate_data() -> dict[str, Any]:
        """Create test certificate data."""
        return {
            "issuer": "Test CA",
            "subject": "CN=Test Certificate",
            "serial_number": "0123456789ABCDEF",
            "not_before": "2024-01-01T00:00:00Z",
            "not_after": "2025-01-01T00:00:00Z",
            "key_type": "RSA",
            "key_size": 2048,
        }

    @staticmethod
    def create_test_verification_request() -> dict[str, Any]:
        """Create test verification request data."""
        return {
            "document_type": "passport",
            "image_data": CommonTestData.SAMPLE_BASE64_IMAGE,
            "verification_level": "basic",
        }


@pytest.fixture
def test_data_factory() -> TestDataFactory:
    """Provide access to test data factory."""
    return TestDataFactory()
