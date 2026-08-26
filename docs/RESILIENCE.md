# Resilience Layer

> **Historical record:** This describes the retired Python service runtime's
> resilience integration. It is not a current runtime guide. Do not configure
> the removed launcher; current retry, circuit-breaker, and failure-policy
> behavior is owned by the shared Rust MMF resilience crate.

This document describes the resilience features added to the Marty microservice platform.

## Overview

Components delivered:

1. Standardized error taxonomy (`marty_common.resilience.error_codes`) mapped to canonical gRPC status codes.
2. Lightweight in‑memory circuit breaker (`CircuitBreaker`) applied inbound (server interceptor) and optionally outbound (`async_call_with_resilience`).
3. Retry helpers (`retry_sync`, `retry_async`, `default_retry`) built on `tenacity` with exponential backoff + jitter.
4. Composite async gRPC server interceptor (`ResilienceServerInterceptor`) providing:
   - Exception translation (including custom `MartyError` subclasses).
   - Per‑RPC circuit breaking.
   - Failure / chaos injection for resilience testing.
5. Outbound helper `async_call_with_resilience` combining circuit breaker + retry around client stub calls.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MARTY_RESILIENCE_ENABLED` | `true` | Toggle registration of the resilience interceptor in `apps.runtime` |
| `MARTY_CIRCUIT_BREAKER_ENABLED` | `true` | Enable server‑side circuit breaker logic (still creates no‑op breakers if disabled) |
| `MARTY_FAILURE_INJECTION` | `false` | Enable failure injection feature |
| `MARTY_FAILURE_INJECTION_RATE` | `0.0` | Probability (0.0‑1.0) of random injected transient failure when enabled |

Per‑request targeted failure injection: add metadata `x-failure-inject: true` (only honored when `MARTY_FAILURE_INJECTION` is enabled).

## Error Mapping

| Error Class | Category | gRPC Status |
|-------------|----------|-------------|
| `ValidationError` | validation | `INVALID_ARGUMENT` |
| `NotFoundError` | not_found | `NOT_FOUND` |
| `ConflictError` | conflict | `ALREADY_EXISTS` |
| `UnauthorizedError` | unauthorized | `PERMISSION_DENIED` |
| `TransientBackendError` | transient | `UNAVAILABLE` |
| other / unknown | internal | `INTERNAL` |

Helper: `map_exception_to_status(exc)` returns `(grpc.StatusCode, message)`.

## Circuit Breaker

State machine: `CLOSED -> OPEN -> HALF_OPEN -> CLOSED` with immediate reopen on HALF_OPEN failure.

Config (`CircuitBreakerConfig`):

- `failure_threshold`: consecutive failures in CLOSED to OPEN the breaker.
- `recovery_timeout`: seconds to stay OPEN before allowing a HALF_OPEN trial.
- `half_open_success_threshold`: successes required while HALF_OPEN to fully CLOSE.
- `failure_reset_timeout`: inactivity window after which the failure counter resets while CLOSED.

Inbound usage: one breaker per fully-qualified RPC method path.

Outbound usage: `async_call_with_resilience("service.Method", lambda: stub.Method(req))`.

## Retry Helpers

``default_retry(max_attempts=5, base=0.2, max_wait=3.0)``

Backoff: exponential with jitter via `tenacity.wait_exponential_jitter`.

Retry predicate: transient exceptions (`TransientBackendError` or those marked transient by `exception_is_transient`).

Decorators: `@retry_async()`, `@retry_sync()` or call policy returned by `default_retry`.

## Failure Injection

Purpose: Validate client retry paths, circuit breaker transitions, observability alerts under error conditions.

Activate globally with `MARTY_FAILURE_INJECTION=true` and optionally set probability `MARTY_FAILURE_INJECTION_RATE=0.25`.

Force per-call injection with request metadata: `x-failure-inject: true`.

Injected failures raise `TransientBackendError` -> mapped to `UNAVAILABLE`.

## Testing

Added unit tests:

- `test_circuit_breaker.py` – state transitions, half-open behavior, reset timer.
- `test_resilience_interceptor.py` – error mapping verification & failure injection.

Run all tests:

```bash
pytest -k resilience -v
```

## Integration Guidance

Inbound (already wired): Set `MARTY_RESILIENCE_ENABLED=false` to temporarily disable.

Outbound example:

```python
from marty_common.resilience import async_call_with_resilience

async def get_doc(stub, request):
    return await async_call_with_resilience(
        "document_signer.GetDocument", lambda: stub.GetDocument(request),
        retry_kwargs={"max_attempts": 4}
    )
```

## Future Enhancements

- Metrics export (success/failure counts, state) via Prometheus.
- Configurable breaker policies per method via config file.
- Structured error detail metadata (rich protobuf Any attachments).
