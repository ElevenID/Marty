# Marty Common Test Utilities

This module provides shared testing utilities, fixtures, and patterns used across all Marty services to eliminate code duplication and standardize testing approaches.

## Features

### Core Classes

- **`MockFactory`**: Factory for creating common mock objects (AsyncMock, MagicMock, gRPC service mocks)
- **`ServiceHealthChecker`**: Utilities for checking service availability and health
- **`TempResourceManager`**: Manages temporary files and directories with automatic cleanup
- **`TestClientFactory`**: Factory for creating test clients (FastAPI, gRPC)
- **`CommonTestData`**: Provides sample test data (certificates, images, MRZ data)
- **`AsyncTestUtils`**: Utilities for async testing (condition waiting, timeouts)

### Base Test Classes

- **`BaseServiceTest`**: Base class for service tests with common setup/teardown
- **`BaseIntegrationTest`**: Base class for integration tests with service availability checking

### Pytest Fixtures

- `mock_factory`: Provides MockFactory instance
- `service_health_checker`: Provides ServiceHealthChecker instance  
- `temp_resource_manager`: Provides TempResourceManager with auto-cleanup
- `common_test_data`: Provides CommonTestData instance
- `sample_certificate`: Provides mock certificate bytes
- `grpc_service_mock`: Provides mock gRPC service
- `test_mode`: Detects test mode (mock/partial/integration)
- `service_status`: Provides status of all services

## Usage Examples

### Basic Service Test

```python
from marty_common.testing import BaseServiceTest, MockFactory

class TestMyService(BaseServiceTest):
    def test_service_functionality(self, mock_factory: MockFactory):
        # Create mocks using factory
        service_mock = mock_factory.create_grpc_service_mock()

        # Test your service
        assert service_mock.running is True
```

### Integration Test

```python
from marty_common.testing import BaseIntegrationTest

class TestMyIntegration(BaseIntegrationTest):
    def test_with_real_service(self):
        # Skip if service not available
        self.skip_if_service_unavailable("trust-anchor")

        # Run integration test
        # ...
```

### Using Temporary Resources

```python
def test_file_operations(temp_resource_manager):
    # Create temp file
    temp_file = temp_resource_manager.create_temp_file(
        content="test data",
        suffix=".json"
    )

    # Use the file
    assert temp_file.read_text() == "test data"

    # Cleanup is automatic
```

### Service Health Checking

```python
def test_service_availability(service_health_checker):
    # Check if service is running
    if service_health_checker.is_service_running(service_name="postgres"):
        # Run tests that require postgres
        pass
    else:
        pytest.skip("Postgres not available")
```

## Test Modes

The utilities automatically detect the test environment:

- **`mock`**: No real services available - use mocks
- **`partial`**: Some services available - mixed testing
- **`integration`**: All services available - full integration testing

Set `MARTY_TEST_MODE` environment variable to override detection.

## Benefits

1. **Eliminates Duplication**: Common test patterns shared across all services
2. **Standardizes Approaches**: Consistent testing patterns and utilities
3. **Simplifies Setup**: Base classes handle common setup/teardown
4. **Improves Reliability**: Automatic resource cleanup and service checking
5. **Enhances Flexibility**: Supports multiple test modes (mock/integration)

## Integration

Import from `marty_common.testing` in your test files:

```python
from marty_common.testing import (
    BaseServiceTest,
    MockFactory,
    ServiceHealthChecker,
    # ... other utilities
)
```

The utilities work seamlessly with pytest and support both sync and async testing patterns.
