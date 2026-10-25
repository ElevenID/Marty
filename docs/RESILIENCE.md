# Resilience ownership and qualification

Shared service resilience belongs to Rust
[`mmf-resilience`](https://github.com/ElevenID/marty-microservices-framework/tree/main/crates/mmf-resilience).
Its source owns retry/backoff, circuit breakers, bulkheads, timeouts, and fallback
chains. New service work should compose that owner rather than add another Python
runtime. This is not a claim that every former Python integration has migrated.

## Retained compatibility APIs

The Python [resilience package](../packages/marty-common/marty_common/resilience/__init__.py)
remains available pending an audited migration of its consumers. This cleanup
preserves its primitives, interceptors, configuration, degradation, monitoring,
and chaos APIs.

| Capability | Retained Python owner |
| --- | --- |
| Breaker states, thresholds, reset windows, error classification | [circuit_breaker.py](../packages/marty-common/marty_common/resilience/circuit_breaker.py) |
| Bounded retry, backoff, sync/async calls | [retry.py](../packages/marty-common/marty_common/resilience/retry.py), [advanced_retry.py](../packages/marty-common/marty_common/resilience/advanced_retry.py) |
| gRPC client/server composition and typed error translation | [comprehensive_interceptors.py](../packages/marty-common/marty_common/resilience/comprehensive_interceptors.py), [error_codes.py](../packages/marty-common/marty_common/resilience/error_codes.py) |
| Environment presets, YAML and environment overrides | [config.py](../packages/marty-common/marty_common/resilience/config.py) |
| Ordered fallback, cached/default responses, health and feature controls | [graceful_degradation.py](../packages/marty-common/marty_common/resilience/graceful_degradation.py) |
| Metrics, registered component health and reports | [metrics.py](../packages/marty-common/marty_common/resilience/metrics.py), [monitoring.py](../packages/marty-common/marty_common/resilience/monitoring.py) |

The former `apps.runtime` launcher and `scripts/resilience_demo.py` are retired.
Their environment wiring is not a current deployment contract. Consult the
actual configuration owner for supported fields rather than copying the old
quickstart's service setup, Flask health endpoint, or nonexistent config paths.

## Checks and remaining acceptance work

Collected Python checks are in
[chaos_resilience_test.py](../tests/unit/chaos_resilience_test.py) and
[compatibility_consolidation_test.py](../tests/unit/compatibility_consolidation_test.py).
The former covers deterministic injector cleanup and breaker/retry/fallback
composition; the latter covers compatibility behavior including sync/async retry
limits. These tests do not qualify deployed services or the Rust runtime.

The obsolete `integration_tests` and `comprehensive_integration_tests` modules
reported random, in-process mock outcomes. Neither performed real gRPC calls nor
was collected by the normal pytest filename pattern. Their orchestrators, mock
services, canned scenarios, and print runners were removed; a printed success
rate was not an integration assertion. Their intent remains acceptance work:

- Verify breaker closed/open/half-open transitions, threshold and timeout
  boundaries, failed recovery probes, successful recovery, and client-error
  classification without waiting on random outcomes.
- Verify bounded sync/async retry, non-retryable errors, backoff/jitter bounds,
  attempt/deadline limits, and combined retry/breaker/fallback behavior.
- Verify configured fallback ordering, unavailable/failed fallbacks, explicit
  degraded responses, and recovery to primary operation. Authentication and
  authorization failures must not become successful access through fallback.
- Exercise real gRPC client/server interceptor composition, typed error/status
  propagation, deadlines, latency, and cancellation across transport boundaries.
  Retain per-method breaker policy and structured protobuf `Any` error-detail
  requirements until implemented and qualified in the owning service.
- Qualify concurrency limits and error classification, and any required adaptive,
  Fibonacci, or polynomial backoff separately; their Python configuration names
  do not establish equivalent Rust support.
- Validate deployment configuration and threshold overrides at startup. Check
  that observed latency, retry counts, breaker states, dependency health, and
  alerts reflect real outcomes rather than only local mock counters.
- Exercise controlled dependency outages, simultaneous failures, load and
  recovery in the service owner. Qualify fault-injection controls separately;
  no deployment injection configuration is established by these retired demos.

The old `FailureScenario.failure_type` and `duration_seconds` fields were unused;
its quickstart also supplied a nonexistent `latency_range` field. Selecting fault
types, bounding their duration, and exercising latency remain explicit
requirements for a future qualification harness, not implemented guarantees.
No equivalence between Python configuration and Rust configuration is assumed.

## Retained Python qualification tooling

`marty_common.resilience.chaos_testing` retains its public injector, configuration,
context manager, and `ResilienceTestSuite` APIs for compatibility. Its embedded
pytest fixtures and standalone print demo were removed from the runtime package.
Collected checks now live in `tests/unit/chaos_resilience_test.py`; they exercise
injected exceptions and cleanup, breaker recovery with controlled time, and a
bounded retry/breaker/fallback sequence through the real Python primitives.
These checks qualify retained compatibility behavior, not the Rust runtime.

The synthetic suite's aggregate counters are not integration qualification:
`chaos_context` starts a background task whose exceptions do not reach the
protected operation, and retry policy factories do not populate the suite's
separate retry metrics registry. Its degradation method also accepts but does
not invoke the supplied fallback operation. Those public APIs remain unchanged;
callers must not infer verified fault handling from their printed summaries.
A future API audit must define how concurrent delay injection and synchronous
failure injection interact before changing the context manager's behavior.

Memory pressure, CPU spike, and disk-full enum values have no injection dispatch
implementation. Real-service, deployment, and Rust fault-injection qualification
remain separate work; retaining these names does not establish support.
