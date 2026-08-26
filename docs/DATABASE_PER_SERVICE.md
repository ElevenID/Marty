# Database Per Service Implementation

> **Historical record:** This document describes a retired Python microservice
> design. It is not a current deployment guide, and its named launcher and
> service modules do not exist. Do not use these paths to build or operate
> Marty; deploy the Rust services from `marty-ui` release artifacts.

This implementation provides database isolation per service following the microservices pattern of "database per service". Each service has its own database schema and manages its own data lifecycle.

## Architecture

### Services with Dedicated Databases

1. **document_signer** - Manages credential offers, access tokens, and issuance audit trails
2. **csca_service** - Manages CSCA certificates, certificate chains, and CRL/OCSP caches  
3. **pkd_service** - Manages PKD download manifests and certificate entries
4. **passport_engine** - Manages passport validation requests and results cache

### Key Components

#### Configuration Changes

- `marty_common/config.py` - Updated `database()` method to accept service name parameter
- `src/apps/runtime.py` - Updated `build_dependencies_async()` to accept service name
- Configuration files now support per-service database DSNs in format:

  ```yaml
  database:
    document_signer: <dsn>
    csca_service: <dsn>
    pkd_service: <dsn>
    passport_engine: <dsn>
    default: <fallback_dsn>  # for backward compatibility
  ```

#### Migration Infrastructure

Each service has its own Alembic setup:

```
src/services/{service_name}/
├── alembic/
│   ├── env.py
│   ├── versions/
│   └── alembic.ini
└── models.py
```

#### Makefile Targets

New database migration targets:

- `make db-upgrade SERVICE=<service_name>` - Run migrations for specific service
- `make db-revision SERVICE=<service_name> MESSAGE="description"` - Create new migration
- `make db-downgrade SERVICE=<service_name> [REVISION=<rev>]` - Downgrade migrations
- `make db-current SERVICE=<service_name>` - Show current migration status
- `make db-history SERVICE=<service_name>` - Show migration history
- `make db-upgrade-all` - Run migrations for all services

## Database Schemas

### document_signer Service

Tables:

- `document_signer_outbox` - Event outbox for async messaging
- `credential_offers` - OIDC4VCI credential offers
- `access_tokens` - OAuth2 access tokens for credential issuance
- `issued_credential_audit` - Audit trail for all credential operations

### csca_service Service  

Tables:

- `csca_outbox` - Event outbox for async messaging
- `csca_certificates` - CSCA certificate storage and metadata
- `certificate_chains` - Certificate chain validation data
- `crl_cache` - Certificate Revocation List cache
- `ocsp_cache` - OCSP response cache

### pkd_service Service

Tables:

- `pkd_outbox` - Event outbox for async messaging  
- `pkd_download_manifest` - PKD manifest tracking
- `pkd_certificate_entries` - Individual certificate entries from PKD
- `pkd_sync_jobs` - Background sync job tracking

### passport_engine Service

Tables:

- `passport_engine_outbox` - Event outbox for async messaging
- `passport_validation_requests` - Passport validation request tracking
- `passport_validation_cache` - Validation result caching

## Usage Examples

### Creating New Migration

```bash
# Create a new migration for document_signer service
make db-revision SERVICE=document_signer MESSAGE="Add user consent tracking"

# Run the migration
make db-upgrade SERVICE=document_signer
```

### Service Initialization

```python
from src.apps.runtime import build_dependencies_async

# Build dependencies for a specific service
dependencies = await build_dependencies_async(service_name="document_signer")

# This will automatically use the document_signer database configuration
```

### Configuration Examples

```yaml
# Single database (backward compatible)
database:
  url: "postgresql+asyncpg://user:pass@localhost:5432/marty"

# Per-service databases
database:
  document_signer: "postgresql+asyncpg://user:pass@localhost:5432/marty_doc_signer"
  csca_service: "postgresql+asyncpg://user:pass@localhost:5432/marty_csca"
  pkd_service: "postgresql+asyncpg://user:pass@localhost:5432/marty_pkd"
  passport_engine: "postgresql+asyncpg://user:pass@localhost:5432/marty_passport"
  default: "postgresql+asyncpg://user:pass@localhost:5432/marty_default"
```

## Benefits

1. **Data Isolation** - Each service owns its data completely
2. **Independent Scaling** - Database resources can be scaled per service
3. **Independent Deployments** - Schema changes don't affect other services
4. **Technology Diversity** - Services can use different database technologies if needed
5. **Improved Security** - Blast radius of security issues is contained per service
6. **Clear Boundaries** - Enforces proper service boundaries and reduces coupling

## Migration from Shared Database

1. **Phase 1**: Deploy configuration changes (backward compatible)
2. **Phase 2**: Create per-service databases and run initial migrations
3. **Phase 3**: Migrate data from shared database to service-specific databases
4. **Phase 4**: Update service deployment configurations to use service-specific databases
5. **Phase 5**: Remove shared database dependencies

## Outbox Pattern

Each service implements the outbox pattern for reliable event publishing:

- Events are written to the service's outbox table in the same transaction as business data
- Background dispatcher reads from outbox and publishes to event bus
- Ensures exactly-once delivery semantics across service boundaries
