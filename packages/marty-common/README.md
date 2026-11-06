# Marty Common

`marty-common` is the retained Python infrastructure package used by Marty
billing and commerce and by source tooling. Version 0.3 removes the obsolete
Core 0.1 identity compatibility layer. No Core wheel is required to install or
use the retained package.

## Retained APIs

- FastAPI service setup, request/security middleware and health helpers.
- Database configuration, sessions, models, repositories, outbox and messaging.
- Cedar policy evaluation and organization authorization.
- Configuration, telemetry, logging and resilience utilities.
- Externally provisioned TLS/mTLS and managed-provider client abstractions.
- DTOs, enum values, migration profiles, public metadata and pairwise IDs.

```python
from marty_common.service_setup import create_service_app
from marty_common.database import DatabaseConfig, DatabaseManager
from marty_common.events import DomainEvent
from marty_common.cedar_engine import CedarEngine, AuthzDecision

app = create_service_app(title="Billing", service_name="billing")
```

Credential issuance, verification, eMRTD/chip operations, and managed signing
belong to the current Rust platform. The old `ffi` extra, crypto bridge and
identity adapters are removed. Requesting the removed Python JWT or automatic
ACME mode fails closed; mTLS and externally provisioned certificates remain.

The root repository retains protocol schemas and migration evidence as source
records. Older gRPC helpers that refer to those checkout schemas are source
tooling, not an installed identity service. No stored data, keys, migration
records or enum wire values are removed.

See [the audited retirement boundary](../../docs/features/python-identity-retirement.md)
for consumers, current owners and remaining product requirements.

## License

MIT
