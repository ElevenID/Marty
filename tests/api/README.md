# API Integration Tests

Integration tests for Marty UI-facing API endpoints using in-memory SQLite, mocked Keycloak authentication, and respx for HTTP mocking.

## Structure

```
tests/api/
├── __init__.py
├── conftest.py              # API test fixtures and setup
├── api_keys/
│   └── test_api_key_lifecycle.py
├── auth/                    # (future) Auth flow tests
├── credentials/             # (future) Credential config tests
├── identity/                # (future) Trust profile tests
├── organizations/
│   └── test_org_crud.py
└── webhooks/
    └── test_webhook_crud.py
```

## Running Tests

Run all API integration tests:
```bash
pytest -m api_integration
```

Run specific test modules:
```bash
pytest tests/api/organizations/
pytest tests/api/webhooks/
pytest tests/api/api_keys/
```

Run with verbose output:
```bash
pytest tests/api/ -v
```

Run specific test:
```bash
pytest tests/api/webhooks/test_webhook_crud.py::TestWebhookDelivery::test_webhook_hmac_signature_generation
```

## Test Fixtures

### Database
- `test_db_engine`: In-memory SQLite with foreign keys enabled
- `test_db_session`: Isolated session with automatic rollback after each test

### Authentication
- `mock_organization`: Test organization instance
- `mock_user`: Mock authenticated user data
- `authenticated_user_context`: Full auth context with user + org
- `authenticated_client`: HTTP client with auth headers set

### HTTP Client
- `api_client`: Async HTTP client with FastAPI app and mocked dependencies
- Uses `httpx.AsyncClient` for async requests

### Mocking
- `mock_keycloak`: Mocked Keycloak client for auth tests
- `mock_redis`: Mocked Redis client for caching/sessions
- `respx.mock`: Decorator for mocking external HTTP calls in webhook tests

## Entity Factories

Located in `tests/fixtures/api_factories.py`:

```python
from tests.fixtures.api_factories import (
    OrganizationFactory,
    APIKeyFactory,
    WebhookFactory,
    SubscriptionFactory,
    CredentialConfigFactory,
    TrustConfigFactory,
)

# Create test data
org = OrganizationFactory.create(name="Test Org")
api_key = APIKeyFactory.create(organization_id=org.id, scopes=["read:credentials"])
webhook = WebhookFactory.create(organization_id=org.id, event_types=["*"])
```

## Test Coverage

### Organizations (`test_org_crud.py`)
- ✅ GET organization details
- ✅ PATCH organization (name, logo_url, website_url, contact_email)
- ✅ Access control (403 for different org)
- ✅ Validation (empty name rejected)

### API Keys (`test_api_key_lifecycle.py`)
- ✅ Create API key with scopes and expiration
- ✅ List API keys (with revoked filtering)
- ✅ Revoke API key
- ✅ Delete API key
- ✅ Update IP allowlist
- ✅ Validation (empty scopes rejected)

### Webhooks (`test_webhook_crud.py`)
- ✅ Create webhook with event types
- ✅ List webhooks
- ✅ Update webhook (URL, event types, enabled status)
- ✅ Delete webhook
- ✅ Test webhook delivery (with respx mocking)
- ✅ HMAC signature verification
- ✅ Get delivery attempt history

## CI Integration

Tests are marked with `@pytest.mark.api_integration` and auto-applied to all tests in `tests/api/`.

Run in CI:
```bash
# Run only API integration tests
pytest -m api_integration --tb=short

# Exclude slow tests
pytest -m "api_integration and not slow"
```

## Adding New Tests

1. Create test file in appropriate subdirectory
2. Import necessary fixtures from `conftest.py`
3. Use entity factories from `api_factories.py`
4. Mark test class with `@pytest.mark.api_integration`
5. Use `async def` for test functions
6. Use `respx.mock` decorator for external HTTP calls

Example:
```python
import pytest
from tests.fixtures.api_factories import OrganizationFactory

@pytest.mark.asyncio
@pytest.mark.api_integration
class TestMyEndpoint:
    async def test_my_feature(
        self,
        authenticated_client,
        test_db_session,
        mock_organization,
    ):
        test_db_session.add(mock_organization)
        await test_db_session.commit()
        
        response = await authenticated_client.get("/api/my-endpoint")
        
        assert response.status_code == 200
```

## Dependencies

Required packages:
- `pytest>=7.4.3`
- `pytest-asyncio>=0.21.1`
- `httpx` - Async HTTP client
- `respx` - HTTP mocking for httpx
- `sqlalchemy[asyncio]` - Async database
- `aiosqlite` - SQLite async driver

Install:
```bash
pip install pytest pytest-asyncio httpx respx sqlalchemy[asyncio] aiosqlite
```
