# Digital Identity API

A comprehensive digital identity management API for the Marty platform, implementing 5 core identity primitives with support for multiple trust frameworks (ICAO, AAMVA, EUDI, Custom).

## Features

- **Trust Profiles**: Abstract trust validation across ICAO (ePassports), AAMVA (mDL), EUDI, and custom trust models
- **Credential Templates**: Define credential schemas with selective disclosure and predicates
- **Presentation Policies**: Specify verification requirements with freshness and holder binding
- **Deployment Profiles**: Configure operational environments with network modes and UX settings
- **Flows**: Orchestrate credential lifecycle workflows with approval strategies and extensible hooks

## Architecture

Implements **Hexagonal Architecture** (Ports & Adapters) with:

- **Domain Layer**: Pure business logic (entities, value objects, events)
- **Application Layer**: Use cases (services, ports/interfaces)
- **Infrastructure Layer**: External adapters (REST API, persistence, trust adapters)

## Quick Start

### 1. Installation

```bash
# The module is already part of the Marty project
cd /path/to/Marty
```

### 2. Configuration

Add to `config/mmf.yaml`:

```yaml
digital_identity:
  enabled: true
  
  trust_profiles:
    icao:
      enabled: true
      trust_store_path: "data/csca"
      master_list_sources:
        - "https://pkddownloadsg.icao.int/"
    
    aamva:
      enabled: true
      iaca_directory: "data/iaca"
      vical_url: "https://aamva.org/vical"
```

### 3. Register Plugin

In your FastAPI application:

```python
from fastapi import FastAPI
from digital_identity.plugin import register_plugin

app = FastAPI()

# Load config and register plugin
config = load_config("config/mmf.yaml")
plugin = register_plugin(app, config.get("digital_identity"))
```

### 4. Run Migrations

```bash
alembic revision --autogenerate -m "Add digital identity tables"
alembic upgrade head
```

### 5. Test API

```bash
# Start server
python -m uvicorn main:app --reload

# Create a trust profile
curl -X POST http://localhost:8000/v1/identity/trust-profiles \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ICAO US Passports",
    "profile_type": "icao",
    "trust_sources": [{"type": "pkd", "url": "https://pkddownloadsg.icao.int/"}]
  }'
```

## API Endpoints

All endpoints use the `/v1/identity/` prefix:

### Trust Profiles
```
POST   /v1/identity/trust-profiles           # Create
GET    /v1/identity/trust-profiles           # List
GET    /v1/identity/trust-profiles/{id}      # Get
PATCH  /v1/identity/trust-profiles/{id}      # Update
DELETE /v1/identity/trust-profiles/{id}      # Delete
POST   /v1/identity/trust-profiles/{id}/refresh  # Refresh trust anchors
```

### Credential Templates
```
POST   /v1/identity/credential-templates     # Create
GET    /v1/identity/credential-templates     # List
GET    /v1/identity/credential-templates/{id}  # Get
PATCH  /v1/identity/credential-templates/{id}  # Update
DELETE /v1/identity/credential-templates/{id}  # Delete
```

### Presentation Policies
```
POST   /v1/identity/presentation-policies    # Create
GET    /v1/identity/presentation-policies    # List
GET    /v1/identity/presentation-policies/{id}  # Get
PATCH  /v1/identity/presentation-policies/{id}  # Update
DELETE /v1/identity/presentation-policies/{id}  # Delete
```

### Deployment Profiles
```
POST   /v1/identity/deployment-profiles      # Create
GET    /v1/identity/deployment-profiles      # List
GET    /v1/identity/deployment-profiles/{id}  # Get
PATCH  /v1/identity/deployment-profiles/{id}  # Update
DELETE /v1/identity/deployment-profiles/{id}  # Delete
```

### Flows
```
POST   /v1/identity/flows                    # Create
GET    /v1/identity/flows                    # List
GET    /v1/identity/flows/{id}               # Get
PATCH  /v1/identity/flows/{id}               # Update
DELETE /v1/identity/flows/{id}               # Delete

POST   /v1/identity/flows/{flow_id}/executions  # Start execution
GET    /v1/identity/flows/{flow_id}/executions  # List executions
GET    /v1/identity/flows/{flow_id}/executions/{exec_id}  # Get execution
POST   /v1/identity/flows/{flow_id}/executions/{exec_id}/approve  # Approve
POST   /v1/identity/flows/{flow_id}/executions/{exec_id}/reject   # Reject
```

## Flow Types

### OID4VCI Pre-Authorized
Standard OpenID4VCI pre-authorized code flow for credential issuance.

**Steps**: Validate Request → Await Approval → Generate Credential → Deliver Credential

### OID4VCI Authorization Code
OpenID4VCI authorization code flow with OAuth2 authorization.

**Steps**: Validate Request → Authorize → Generate Token → Await Approval → Generate Credential → Deliver

### OID4VP Presentation
OpenID4VP credential presentation and verification.

**Steps**: Validate Request → Request Presentation → Verify Presentation → Respond

### mDL Issuance
ISO 18013-5 mobile Driver's License provisioning.

**Steps**: Validate Request → Authenticate Device → Await Approval → Provision mDL → Deliver

### mDL Presentation
ISO 18013-5 mDL presentation over NFC or BLE.

**Steps**: Validate Request → Engage NFC → Verify mDL → Respond

### Application Approval Issuance
Custom application-based credential issuance with identity verification.

**Steps**: Validate Request → Verify Applicant → Await Approval → Generate Credential → Deliver

## Trust Frameworks

### ICAO (ePassports)
- Wraps `CSCATrustStore` and Rust `CscaRegistry`
- CSCA certificate management
- Master List parsing
- PKD integration

### AAMVA (mDL)
- Wraps Rust `IacaRegistry`
- IACA certificate management
- Jurisdiction-based lookups (US states, Canadian provinces)
- VICAL/DTS integration

### EUDI (EU Digital Identity)
- Placeholder for eIDAS 2.0 trust framework
- EU member state trust lists
- To be implemented when specifications finalize

### Custom
- Flexible trust source configuration
- Manual trust anchor management
- Custom validation callbacks
- Pluggable revocation checking

## Approval Strategies

| Strategy | Behavior | Use Case |
|----------|----------|----------|
| **AUTO** | Immediate approval | Low-risk, automated workflows |
| **MANUAL** | Set to AWAITING_APPROVAL status | High-value credentials, compliance review |
| **RULES_BASED** | External rule engine evaluation | Policy-driven decisions |
| **EXTERNAL** | Call external approval service | Integration with existing systems |

## Extension Points

### Hooks
Add custom logic at specific flow steps:

```python
# Add a pre-approval verification hook
await flow_service.add_hook(
    flow_id="<flow_id>",
    step=FlowStep.AWAIT_APPROVAL,
    position="pre",
    handler=custom_verification_handler,
)
```

### Custom Step Handlers
Register custom handlers for flow steps:

```python
from digital_identity.application.ports.outbound import StepHandlerRegistryPort

class CustomStepHandlerRegistry(StepHandlerRegistryPort):
    async def execute_step(self, step: FlowStep, context: dict) -> dict:
        if step == FlowStep.VERIFY_APPLICANT:
            # Custom identity verification logic
            pass
        # ... handle other steps
```

### Custom Trust Adapters
Implement the `TrustProfilePort` interface:

```python
from digital_identity.application.ports.trust_profile import TrustProfilePort

class MyCustomTrustProfile(TrustProfilePort):
    async def get_trust_anchors(self, issuer: str | None) -> list[TrustAnchor]:
        # Custom trust anchor resolution
        pass
    
    async def validate_chain(self, certificate_chain: list[str], issuer: str | None) -> ChainValidationResult:
        # Custom chain validation
        pass
```

## Database Schema

The module creates 6 tables:

- `digital_identity_trust_profiles` - Trust profile configurations
- `digital_identity_credential_templates` - Credential schemas
- `digital_identity_presentation_policies` - Verification requirements
- `digital_identity_deployment_profiles` - Operational configurations
- `digital_identity_flows` - Flow definitions
- `digital_identity_flow_executions` - Flow runtime state

All tables use:
- UUID primary keys
- Timestamps (created_at, updated_at)
- Optimistic locking (version column)
- JSONB for complex nested structures

## Development

### Project Structure
```
digital_identity/
├── domain/              # Entities, value objects, events
├── application/         # Services, ports/interfaces
├── infrastructure/      # Adapters (REST, persistence, trust)
└── plugin/             # MMF plugin registration
```

### Running Tests
```bash
# Unit tests
pytest tests/unit/

# Integration tests
pytest tests/integration/

# All tests
pytest
```

### Code Quality
```bash
# Type checking
mypy src/digital_identity/

# Linting
ruff check src/digital_identity/

# Formatting
black src/digital_identity/
```

## Documentation

- [**IMPLEMENTATION_SUMMARY.md**](./IMPLEMENTATION_SUMMARY.md) - Complete implementation details
- [**INTEGRATION_GUIDE.md**](./INTEGRATION_GUIDE.md) - Step-by-step integration instructions
- **API Documentation**: Available at `/docs` endpoint (Swagger UI)

## Examples

See `INTEGRATION_GUIDE.md` for complete examples of:
- Creating trust profiles
- Defining credential templates
- Configuring presentation policies
- Starting and managing flow executions
- Implementing custom hooks and handlers

## Requirements

- Python 3.11+
- PostgreSQL 14+
- SQLAlchemy 2.0+
- FastAPI 0.100+
- Pydantic 2.0+
- Rust marty-verification (optional, for high-performance trust validation)

## Status

✅ **Core Implementation Complete**
- Domain layer (entities, value objects, events)
- Application layer (services, ports)
- Persistence layer (SQLAlchemy models, repositories)
- REST API (routers, schemas, dependencies)
- Trust adapters (ICAO, AAMVA, EUDI, Custom)
- MMF plugin registration
- Documentation

🚧 **Remaining Integration Work**
- Database migrations (Alembic scripts)
- Dependency injection wiring
- Event publisher connection
- Workflow engine integration
- Trust anchor refresh mechanisms
- Production configuration

## Contributing

1. Follow hexagonal architecture patterns
2. Add tests for new features
3. Update documentation
4. Use type hints
5. Follow existing code style

## License

Part of the Marty project. See main project LICENSE file.

## Support

For questions and issues:
- Check documentation in this directory
- Review existing code examples
- Contact Marty development team

---

**Version**: 0.1.0  
**Status**: Beta - Core implementation complete, integration in progress
