# Digital Identity API - Integration Guide

## Quick Start

### 1. Register the Plugin

In your main application file (e.g., `src/main.py`):

```python
from fastapi import FastAPI
from digital_identity.plugin import register_plugin

app = FastAPI(title="Marty API")

# Load configuration
config = load_config("config/mmf.yaml")
digital_identity_config = config.get("digital_identity", {})

# Register Digital Identity plugin
digital_identity_plugin = register_plugin(app, digital_identity_config)

# Add startup/shutdown hooks
@app.on_event("startup")
async def startup():
    await digital_identity_plugin.startup()

@app.on_event("shutdown")
async def shutdown():
    await digital_identity_plugin.shutdown()
```

### 2. Configure in `config/mmf.yaml`

```yaml
digital_identity:
  enabled: true
  
  trust_profiles:
    icao:
      enabled: true
      trust_store_path: "data/csca"
      master_list_sources:
        - "https://pkddownloadsg.icao.int/"
      pkd_urls:
        - "https://pkddownloadsg.icao.int/"
    
    aamva:
      enabled: true
      iaca_directory: "data/iaca"
      vical_url: "https://aamva.org/vical"
      dts_url: "https://aamva.org/dts"
    
    eudi:
      enabled: false
      trust_list_url: null
      member_state: null
  
  flows:
    default_approval_strategy: "auto"
    enable_hooks: true
    max_execution_time_hours: 24
  
  api:
    version: "v1"
    prefix: "/identity"
    enable_pagination: true
    default_page_size: 100
    max_page_size: 1000
```

### 3. Run Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "Add digital identity tables"

# Apply migration
alembic upgrade head
```

### 4. Test the API

```bash
# Start the server
python -m uvicorn main:app --reload

# Test endpoints
curl http://localhost:8000/v1/identity/trust-profiles
curl http://localhost:8000/v1/identity/flows
```

## Dependency Injection Setup

### Update `infrastructure/adapters/rest/dependencies.py`

Replace the placeholder `get_db_session()` with your actual session factory:

```python
# Before
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    raise NotImplementedError("Database session factory not configured")

# After
from marty.infrastructure.database import get_async_session

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_async_session() as session:
        yield session
```

### Wire Up Trust Adapters

In `dependencies.py`, update service factories to use configured trust adapters:

```python
async def get_trust_profile_service(
    session: AsyncSession = Depends(get_db_session),
    trust_adapter = Depends(get_trust_adapter),  # Add this
    event_publisher = Depends(get_event_publisher),  # Add this
):
    from digital_identity.infrastructure.persistence.repositories import TrustProfileRepository
    from digital_identity.application.services.trust_profile_service import TrustProfileService
    
    repository = TrustProfileRepository(session)
    return TrustProfileService(
        repository=repository,
        event_publisher=event_publisher,
        trust_adapter=trust_adapter,
    )
```

Add dependency providers:

```python
def get_trust_adapter():
    """Get configured trust adapter based on request context."""
    # TODO: Implement trust adapter selection logic
    # Could use request headers, URL params, or profile configuration
    from digital_identity.infrastructure.trust import IcaoTrustProfile
    return IcaoTrustProfile(...)

def get_event_publisher():
    """Get event publisher instance."""
    from marty.infrastructure.events import EventPublisher
    return EventPublisher.get_instance()
```

## Workflow Integration

### Connect to WorkflowEngine

Update `application/services/flow_service.py`:

```python
from marty_msf.framework.workflow import WorkflowEngine
from marty_msf.framework.saga.orchestrator import SagaOrchestrator

class FlowService:
    def __init__(
        self,
        flow_repository: FlowRepositoryPort,
        execution_repository: FlowExecutionRepositoryPort,
        event_publisher: EventPublisherPort | None = None,
        step_registry: StepHandlerRegistryPort | None = None,
        approval_strategy: ApprovalStrategyPort | None = None,
        workflow_engine: WorkflowEngine | None = None,  # Add this
    ):
        # ...
        self._workflow_engine = workflow_engine
```

### Implement Step Handlers

Create step handler implementations in `infrastructure/workflow/`:

```python
# infrastructure/workflow/step_handlers.py

from digital_identity.application.ports.outbound import StepHandlerRegistryPort

class DigitalIdentityStepHandlerRegistry(StepHandlerRegistryPort):
    def __init__(self):
        self._handlers = {}
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """Register default step handlers."""
        self.register_handler(FlowStep.VALIDATE_REQUEST, self._validate_request)
        self.register_handler(FlowStep.GENERATE_CREDENTIAL, self._generate_credential)
        # ... register other handlers
    
    async def _validate_request(self, context: dict[str, Any]) -> dict[str, Any]:
        """Validate incoming request."""
        # Implementation
        pass
    
    async def _generate_credential(self, context: dict[str, Any]) -> dict[str, Any]:
        """Generate credential."""
        # Implementation
        pass
```

## Event Publishing

### Connect to Event Bus

```python
# infrastructure/events/publisher.py

from marty.infrastructure.events import EventPublisher as BaseEventPublisher
from digital_identity.application.ports.outbound import EventPublisherPort
from digital_identity.domain.events import DomainEvent

class DigitalIdentityEventPublisher(EventPublisherPort):
    def __init__(self, base_publisher: BaseEventPublisher):
        self._publisher = base_publisher
    
    async def publish(self, event: DomainEvent) -> None:
        """Publish domain event to the event bus."""
        await self._publisher.publish(
            topic=f"digital_identity.{event.__class__.__name__}",
            payload=event.to_dict(),
        )
```

## Database Migrations

### Create Alembic Migration

```python
# migrations/versions/XXXX_add_digital_identity_tables.py

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'xxxx'
down_revision = 'previous_revision'
branch_labels = None
depends_on = None

def upgrade():
    # Trust Profiles
    op.create_table(
        'digital_identity_trust_profiles',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), unique=True, nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('profile_type', sa.String(50), nullable=False),
        sa.Column('enabled', sa.Boolean, default=True, nullable=False),
        sa.Column('trust_sources', postgresql.JSONB, default=list),
        sa.Column('allowed_algorithms', postgresql.JSONB, default=list),
        sa.Column('allowed_formats', postgresql.JSONB, default=list),
        sa.Column('revocation_policy', postgresql.JSONB, default=dict),
        sa.Column('time_policy', postgresql.JSONB, default=dict),
        sa.Column('allowed_issuers', postgresql.JSONB, nullable=True),
        sa.Column('denied_issuers', postgresql.JSONB, nullable=True),
        sa.Column('metadata', postgresql.JSONB, default=dict),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('version', sa.Integer, default=1, nullable=False),
    )
    
    op.create_index('idx_trust_profiles_name', 'digital_identity_trust_profiles', ['name'])
    op.create_index('idx_trust_profiles_type', 'digital_identity_trust_profiles', ['profile_type'])
    
    # Credential Templates
    op.create_table(
        'digital_identity_credential_templates',
        # ... (similar structure)
    )
    
    # Presentation Policies
    op.create_table(
        'digital_identity_presentation_policies',
        # ... (similar structure)
    )
    
    # Deployment Profiles
    op.create_table(
        'digital_identity_deployment_profiles',
        # ... (similar structure)
    )
    
    # Flows
    op.create_table(
        'digital_identity_flows',
        # ... (similar structure)
    )
    
    # Flow Executions
    op.create_table(
        'digital_identity_flow_executions',
        # ... (similar structure)
    )

def downgrade():
    op.drop_table('digital_identity_flow_executions')
    op.drop_table('digital_identity_flows')
    op.drop_table('digital_identity_deployment_profiles')
    op.drop_table('digital_identity_presentation_policies')
    op.drop_table('digital_identity_credential_templates')
    op.drop_table('digital_identity_trust_profiles')
```

## Testing

### Unit Tests

```python
# tests/unit/test_trust_profile_service.py

import pytest
from digital_identity.application.services import TrustProfileService
from digital_identity.domain.entities import TrustProfile

@pytest.fixture
async def service(mock_repository, mock_event_publisher):
    return TrustProfileService(
        repository=mock_repository,
        event_publisher=mock_event_publisher,
        trust_adapter=None,
    )

@pytest.mark.asyncio
async def test_create_trust_profile(service):
    data = {
        "name": "Test ICAO Profile",
        "profile_type": "icao",
        "trust_sources": [{"type": "pkd", "url": "https://example.com"}],
    }
    
    profile = await service.create(data)
    
    assert profile.name == "Test ICAO Profile"
    assert profile.profile_type.value == "icao"
```

### Integration Tests

```python
# tests/integration/test_trust_profile_api.py

import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_trust_profile(client: AsyncClient):
    response = await client.post(
        "/v1/identity/trust-profiles",
        json={
            "name": "Test Profile",
            "profile_type": "icao",
            "trust_sources": [],
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Profile"
```

## API Usage Examples

### Create a Trust Profile

```bash
curl -X POST http://localhost:8000/v1/identity/trust-profiles \
  -H "Content-Type: application/json" \
  -d '{
    "name": "US Passport ICAO",
    "description": "ICAO trust profile for US ePassports",
    "profile_type": "icao",
    "trust_sources": [
      {"type": "pkd", "url": "https://pkddownloadsg.icao.int/"}
    ],
    "allowed_algorithms": ["ES256", "ES384", "ES512"],
    "allowed_formats": ["sd_jwt_vc", "mdoc"],
    "revocation_policy": {
      "mode": "hard_fail",
      "check_ocsp": true,
      "check_crl": true,
      "check_status_list": true
    }
  }'
```

### Create a Credential Template

```bash
curl -X POST http://localhost:8000/v1/identity/credential-templates \
  -H "Content-Type: application/json" \
  -d '{
    "name": "US Passport Template",
    "credential_type": "org.icao.passport.eMRTD",
    "format": "sd_jwt_vc",
    "claims": [
      {
        "name": "given_name",
        "display_name": "Given Name",
        "data_type": "string",
        "required": true,
        "selectively_disclosable": true
      },
      {
        "name": "family_name",
        "display_name": "Family Name",
        "data_type": "string",
        "required": true,
        "selectively_disclosable": true
      }
    ],
    "trust_profile_id": "<trust_profile_id>"
  }'
```

### Create a Flow

```bash
curl -X POST http://localhost:8000/v1/identity/flows \
  -H "Content-Type: application/json" \
  -d '{
    "name": "US Passport Issuance",
    "flow_type": "application_approval_issuance",
    "trust_profile_id": "<trust_profile_id>",
    "credential_template_id": "<template_id>",
    "approval_strategy": "manual",
    "enabled": true
  }'
```

### Start a Flow Execution

```bash
curl -X POST http://localhost:8000/v1/identity/flows/<flow_id>/executions \
  -H "Content-Type: application/json" \
  -d '{
    "context_data": {
      "applicant_id": "12345",
      "document_number": "P123456789"
    }
  }'
```

### Approve an Execution

```bash
curl -X POST http://localhost:8000/v1/identity/flows/<flow_id>/executions/<exec_id>/approve \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Application approved by officer"
  }'
```

## Monitoring & Observability

### Add Metrics

```python
from prometheus_client import Counter, Histogram

# Flow execution metrics
flow_executions = Counter(
    'digital_identity_flow_executions_total',
    'Total number of flow executions',
    ['flow_type', 'status']
)

flow_execution_duration = Histogram(
    'digital_identity_flow_execution_duration_seconds',
    'Flow execution duration',
    ['flow_type']
)
```

### Add Logging

```python
import logging

logger = logging.getLogger("digital_identity")
logger.setLevel(logging.INFO)

# Add structured logging
logger.info(
    "Flow execution started",
    extra={
        "flow_id": flow.id,
        "flow_type": flow.flow_type.value,
        "execution_id": execution.id,
    }
)
```

### Add Tracing

```python
from opentelemetry import trace

tracer = trace.get_tracer("digital_identity")

with tracer.start_as_current_span("flow_execution") as span:
    span.set_attribute("flow.id", flow.id)
    span.set_attribute("flow.type", flow.flow_type.value)
    # ... execute flow
```

## Security Considerations

1. **Authentication**: Protect all endpoints with authentication middleware
2. **Authorization**: Implement RBAC for sensitive operations (create, delete, approve)
3. **Input Validation**: All inputs validated via Pydantic schemas
4. **SQL Injection**: SQLAlchemy ORM prevents SQL injection
5. **Audit Logging**: Log all state changes for compliance
6. **Rate Limiting**: Implement rate limits on public endpoints
7. **HTTPS Only**: Enforce HTTPS in production

## Production Checklist

- [ ] Database migrations applied
- [ ] Trust anchors loaded and validated
- [ ] Event publisher configured
- [ ] Workflow engine integration tested
- [ ] API authentication enabled
- [ ] API authorization policies configured
- [ ] Monitoring and alerting set up
- [ ] Backup strategy for trust stores
- [ ] SSL/TLS certificates configured
- [ ] Rate limiting enabled
- [ ] Audit logging enabled
- [ ] Performance testing completed
- [ ] Security review passed
- [ ] Documentation updated
- [ ] Runbook created for operations

## Troubleshooting

### Issue: Trust validation fails

**Solution**: Check trust anchor configuration and ensure trust stores are populated:

```python
from digital_identity.infrastructure.trust import IcaoTrustProfile

profile = IcaoTrustProfile(trust_store_path=Path("data/csca"))
anchors = await profile.get_trust_anchors()
print(f"Loaded {len(anchors)} trust anchors")
```

### Issue: Flow execution hangs

**Solution**: Check workflow engine status and step handler configuration:

```python
# Enable debug logging
import logging
logging.getLogger("digital_identity").setLevel(logging.DEBUG)

# Check execution status
execution = await flow_service.get_execution(execution_id)
print(f"Status: {execution.status}, Step: {execution.current_step}")
```

### Issue: Database connection errors

**Solution**: Verify database connection string and async session configuration:

```python
# Test database connection
from sqlalchemy import select
from digital_identity.infrastructure.persistence.models import TrustProfileModel

async with get_db_session() as session:
    result = await session.execute(select(TrustProfileModel).limit(1))
    print("Database connection OK")
```

## Support

For issues and questions:
- Check the [IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md)
- Review API documentation at `/docs` endpoint
- Contact the Marty development team
