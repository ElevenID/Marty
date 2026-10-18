# Resilience qualification requirements

The retired `marty_common.resilience.integration_tests` module simulated service
calls with random failures and printed success summaries. It had no consumers,
was not collected by the normal pytest filename pattern, and did not qualify
real service integrations. Its three names in the package `__all__` were never
imported or usable as package exports. Removing it does not establish coverage.

Retain these requirements when qualifying the current Rust MMF resilience owner
identified in [the resilience ownership note](../RESILIENCE.md):

- Circuit breakers reject requests after the configured failure threshold, allow
  recovery probes after the timeout, close after successful probes, and reopen
  after a failed probe.
- Retryable transient failures receive bounded attempts and backoff; permanent
  failures propagate without retry, and exhausted attempts preserve the failure.
- Explicitly supported fallback responses are distinguishable from primary
  responses. Recovery restores primary operation. Fallback failure propagates.
- Combined retry, breaker, and degradation behavior remains bounded under
  simultaneous dependency failures and recovers when dependencies recover.

The old mock authentication fallback to an anonymous guest is not an approved
security policy. Degradation must not turn authentication or authorization
failures into successful access.

Acceptance should use deterministic failure sequences and controlled time, then
exercise real transport/service boundaries separately. Request counts and a
printed success rate do not demonstrate recovery or an integration pass. Rust
coverage of these requirements has not been verified by this cleanup.

The public Python resilience primitives, chaos injection APIs, and documented
`comprehensive_integration_tests` orchestrator remain available pending their own
compatibility and coverage audit.
