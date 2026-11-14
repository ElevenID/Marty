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

## Rate limiting

`marty_common.middleware` retains the synchronous `RateLimiter` and
`RateLimitMiddleware` APIs. The memory backend serializes admission within one
process. The Redis backend uses `WATCH`/`MULTI` transactions to serialize admission
across clients and persists both token state and the minute/hour request history.
Use the same Redis namespace for instances enforcing the same policy and configure
connection/socket timeouts on the supplied synchronous Redis client.

Rules require finite positive rates and a positive integer burst size. A request's
cost consumes that many burst tokens; each admitted call counts once toward the
minute/hour request limits. Costs must be positive integers no larger than the
burst size. Window boundaries expire exactly at 60/3,600 seconds, and a rejection's
retry time accounts for every currently blocking limit. Slow-refilling buckets
remain stored until recreating a full bucket would be equivalent.

Storage errors, corrupt buckets, and exhausted transaction retries raise
`RateLimitBackendError`; they never silently grant a fresh burst. The gRPC
interceptor maps this to `UNAVAILABLE` and ordinary limit rejection to
`RESOURCE_EXHAUSTED`. It preserves all four synchronous RPC cardinalities and
charges one admission per RPC, including streams, rather than per stream message.
The default client identity/type extractors read metadata; callers must establish
that metadata at a trusted authentication boundary or supply authenticated
extractors. The limiter itself does not authenticate clients.

**Upgrade note:** old Redis hashes did not store request history, so their prior
window usage cannot be reconstructed safely. Such hashes fail closed until their
existing TTL expires. Quiesce the old limiter and allow those keys to expire before
switching versions; do not run old and new writers against the same namespace.
Custom distributed backends must override `update_client_data` with an atomic
operation. Existing get/set-only backend subclasses retain process-local locking.

The focused contract tests require real Redis and gRPC. Run
`python -m pytest tests/unit/rate_limiter_test.py` from the repository root, with
`redis-server` on `PATH`, `MARTY_TEST_REDIS_SERVER` naming a local binary, or
`MARTY_TEST_REDIS_URL` pointing to a disposable test service. The existing CI test
job provides an isolated Redis service. Local processes use a Unix socket with
persistence disabled; tests use unique key prefixes and clean up only their keys.

## License

AGPL-3.0-only, as declared in this package's metadata and the repository's
[existing license](../../LICENSE). This retirement does not change the terms.

### Optional biometric quality tooling

`marty_common.security.enhanced_biometric_processing` retains simplified source
parsers and heuristic image/template quality scores. These helpers do not
perform biometric matching, authenticate chip data, or establish standards
conformance. WSQ fingerprint extraction raises `BiometricTemplateError` until
a real decoder/extractor is provided; it never synthesizes minutiae. Iris
capture-device identity is `UNKNOWN` when the parser cannot obtain it from the
input. The supported identity verification stack remains Rust-owned.
