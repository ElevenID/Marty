"""
Example demonstrating usage of shared test utilities.

This file shows how to use the common test utilities and patterns
across different types of tests in the Marty project.
"""

from unittest.mock import AsyncMock

import pytest

# Import from the shared test utilities
from marty_common.testing import (
    BaseIntegrationTest,
    BaseServiceTest,
    CommonTestData,
    MockFactory,
    ServiceHealthChecker,
    TestClientFactory,
    common_test_data,
    grpc_service_mock,
    mock_factory,
    sample_certificate,
    service_health_checker,
    temp_resource_manager,
    test_client_factory,
)


class TestServiceExample(BaseServiceTest):
    """Example service test using shared base class."""

    def test_mock_creation_patterns(self, mock_factory: MockFactory):
        """Test using mock factory for common mock patterns."""
        # Create async mock with common patterns
        async_mock = mock_factory.create_async_mock()
        assert isinstance(async_mock, AsyncMock)

        # Create gRPC service mock
        grpc_mock = mock_factory.create_grpc_service_mock()
        assert hasattr(grpc_mock, "start")
        assert hasattr(grpc_mock, "stop")
        assert grpc_mock.running is True

    def test_temp_resources(self, temp_resource_manager):
        """Test using temporary resource manager."""
        # Create temporary directory
        temp_dir = temp_resource_manager.create_temp_directory()
        assert temp_dir.exists()

        # Create temporary file with content
        temp_file = temp_resource_manager.create_temp_file(suffix=".test", content="test content")
        assert temp_file.exists()
        assert temp_file.read_text() == "test content"

        # Cleanup is automatic via fixture

    def test_common_test_data(self, common_test_data: CommonTestData):
        """Test using common test data."""
        # Access sample data
        assert common_test_data.SAMPLE_BASE64_IMAGE
        assert common_test_data.SAMPLE_CERTIFICATE_PEM.startswith("-----BEGIN CERTIFICATE-----")

        # Get sample request data
        request = common_test_data.get_sample_process_request()
        assert "processParam" in request
        assert "List" in request

    def test_certificate_fixture(self, sample_certificate: bytes):
        """Test using certificate fixture."""
        assert isinstance(sample_certificate, bytes)
        assert sample_certificate == b"MOCK_CERTIFICATE_DATA"


class TestIntegrationExample(BaseIntegrationTest):
    """Example integration test using shared base class."""

    def test_service_health_checking(self, service_health_checker: ServiceHealthChecker):
        """Test service health checking utilities."""
        # Check if postgres is running (will likely be False in this example)
        postgres_running = service_health_checker.is_service_running(service_name="postgres")
        assert isinstance(postgres_running, bool)

        # Get service address
        if postgres_running:
            address = service_health_checker.get_service_address("postgres")
            assert address == "localhost:5432"

    def test_service_skip_behavior(self):
        """Test skipping when service unavailable."""
        # This will skip the test if trust-anchor service is not running
        self.skip_if_service_unavailable("trust-anchor")

        # If we get here, the service is available
        # Perform integration test logic here
        assert True  # Placeholder for actual test logic

    def test_grpc_mock_service(self, grpc_service_mock: AsyncMock):
        """Test using gRPC service mock."""
        assert hasattr(grpc_service_mock, "start")
        assert hasattr(grpc_service_mock, "stop")
        assert grpc_service_mock.running is True


# Example FastAPI test using test client factory
def test_fastapi_client_creation(test_client_factory: TestClientFactory):
    """Example of creating FastAPI test client with common patterns."""
    from fastapi import FastAPI

    # Create a simple test app
    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # Create test client with API key
    client = test_client_factory.create_fastapi_client(app)

    # Verify API key is set
    assert "X-API-Key" in client.headers
    assert client.headers["X-API-Key"] == "test_api_key"

    # Test the endpoint
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# Example pytest parametrize with common test data
@pytest.mark.parametrize("test_image", [CommonTestData.SAMPLE_BASE64_IMAGE])
def test_image_processing_example(test_image: str):
    """Example test using parametrized test data."""
    assert test_image  # Should not be empty
    assert test_image.endswith("==")  # Base64 padding


# Example async test
@pytest.mark.asyncio
async def test_async_utilities_example():
    """Example async test using async test utilities."""
    from marty_common.testing.test_utilities import AsyncTestUtils

    # Test waiting for condition
    test_condition = lambda: True  # Always true for this example
    result = await AsyncTestUtils.wait_for_condition(test_condition, timeout=1.0)
    assert result is True

    # Test with failing condition
    failing_condition = lambda: False
    result = await AsyncTestUtils.wait_for_condition(failing_condition, timeout=0.1)
    assert result is False


# Example of session-scoped fixture usage
def test_test_mode_detection(test_mode: str):
    """Test mode detection fixture example."""
    assert test_mode in ["mock", "partial", "integration"]


def test_service_status_fixture(service_status: dict[str, bool]):
    """Service status fixture example."""
    assert isinstance(service_status, dict)
    # At minimum, should have entries for known services
    known_services = ["postgres", "trust-anchor", "csca-service"]
    for service in known_services:
        assert service in service_status
        assert isinstance(service_status[service], bool)
