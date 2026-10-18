# Centralized logging ownership and qualification

The compatibility package retains its logging APIs. This repository does not
ship an ELK deployment: the former setup wrapper referenced absent Compose and
Filebeat files. Local ports, index templates and dashboards from that tutorial
are not current deployment contracts.

Current service deployment belongs to
[marty-ui](https://github.com/ElevenID/marty-ui); shared native service
infrastructure belongs to
[marty-microservices-framework](https://github.com/ElevenID/marty-microservices-framework).
Use their current configuration and runbooks for the chosen logging backend.

## Retained Python compatibility APIs

The [structured logging module](../packages/marty-common/marty_common/logging/structured_logging.py)
retains `MartyStructuredLogger`, `setup_logging_for_service`, request context,
`LoggingMiddleware`, `PerformanceLogger`, `SecurityLogger` and
`BusinessLogger`. The existing consolidated logging, gRPC logging and metrics
modules remain available to their current consumers.

For a service that already depends on the compatibility package:

```python
from marty_common.logging.structured_logging import setup_logging_for_service

config = setup_logging_for_service("compatibility_worker", environment="development")
logger = config.get_logger()
with config.request_context(request_id="synthetic-request"):
    logger.info("Synthetic operation completed", success=True)
```

This emits a local event; it does not provision collectors or prove ingestion.

## Open deployment and acceptance requirements

Reconcile these requirements with the current service owners before claiming
centralized logging is qualified:

- Structured events with timestamp, service/version/environment, severity,
  event type, outcome and appropriate error context. Preserve request and
  correlation identifiers across HTTP/gRPC boundaries; constrain user/session
  identifiers and prevent secrets or unnecessary identity data entering logs.
- Searchable operational, security/audit, business and performance events.
  Validate field mappings and correlation using real cross-service requests,
  authorization failures and error paths, not only a sample local log entry.
- Authenticated, TLS-protected ingestion and search, network isolation,
  least-privilege access and reviewed retention/rotation/deletion policies.
  The old 7-day rollover/30-day deletion examples were not mandated policies.
- Service/request-rate, latency distribution, error, database/external-call,
  authentication/authorization and business-outcome views, with actionable
  alert routing and escalation. Dashboard existence alone proves no coverage.
- Collector and storage health, disk/capacity bounds, ingestion lag, dropped
  events, recovery and backpressure under load. Qualify resource sizing and
  failure handling against the selected backend.
- Reproducible backend provisioning, readiness, sample-event ingestion/search,
  schema checks, failure diagnostics and deterministic disposable cleanup.
  No deployment manifest, dashboard or alert is supplied by this document.

## Metrics, tracing and operational qualification

The retired advanced-monitoring and observability implementation/deployment
guides referenced absent monitoring, Helm and Kubernetes resources. Their
completion labels do not establish current capabilities. The following
requirements remain open until current MMF/UI owners demonstrate them:

- Cross-service distributed tracing, HTTP/gRPC client/server spans, domain spans,
  service/namespace/version/environment attribution, and correlated trace/span
  IDs in logs. Qualify configurable OTLP export, disabled/debug modes, sampling,
  batch limits and dropped/export-failure behavior against the chosen backend.
- Real metrics discovery/scraping, endpoint/network authorization, collector and
  target readiness, bounded label cardinality, sensible histogram/query units,
  storage sizing, retention, backup and tested recovery. Keep approved
  configuration under its deployment owner rather than restoring fixed examples.
- Trust/certificate issuance, renewal, expiry, validation, signing, revocation,
  PKI/KMS connectivity and audit metrics; HTTP/gRPC calls, streams, failures,
  active requests and dependency health; database pools, query times,
  transactions/rollbacks and replication lag where applicable; node/pod/resource
  health and restart/network failures.
- Operational, security and business views with role-based access. Authentication,
  authorization/MFA/rate-limit events and audit completeness need real evidence.
  Document volumes, SLA measures, revenue/cost and geographic/client analyses,
  customer satisfaction, forecasting, threat intelligence and anomaly detection
  remain scoped proposals until their data sources, privacy policy and owners
  are established. Mobile/voice/AR views and automated remediation are proposals.
- Alert expression and sustained-window tests, grouping/inhibition, no-data
  behavior, delivery confirmation, routing to authorized channels, escalation,
  acknowledgement/recovery and runbook links. Review thresholds and response
  commitments with owners; old contact addresses, credentials, retention sizes
  and escalation times are not current operational policy.
- Authenticated TLS-protected dashboards/collectors, least-privilege service
  accounts, managed notification credentials and administrative audit.
  Exercise real request-to-span/log/metric correlation, alert delivery and
  failure diagnostics in a disposable environment with deterministic cleanup.
- Review dashboard/query accuracy, alert noise, capacity trends, access and
  runbooks regularly. Monitor the collectors, stores and notification pipeline
  themselves; a healthy service endpoint does not prove usable observability.

Use [performance qualification](PERFORMANCE_TESTING.md) for calibrated
workloads and comparable evidence. The retained Python logging, metrics and
observability APIs remain unchanged by this consolidation.

The unconsumed certificate-lifecycle JSON example is retired. Keep reviewed
expiry-warning schedules, periodic checks, renewal/revocation/failure tracking,
logging and authenticated TLS notification delivery with managed SMTP secrets
as current-owner requirements. Certificate lifetime, algorithm/key size,
automatic-renewal lead time and overlap/rollover policy must be explicitly
approved and tested through the canonical certificate/KMS owners; the old
example's numbers and addresses are not defaults to restore.

The uncalled monitoring integration example is retired. It imported symbols
not exported by the current monitoring package, started a synthetic gRPC
skeleton and treated a mock database check as healthy. Preserve actual public
monitoring APIs and their consumers; qualify real dependency readiness,
request/interceptor metrics, alert callbacks, graceful startup/shutdown and
degraded health with current-owner tests. Synthetic counter increments and
source examples are not service acceptance.


## Consolidated compatibility logging

The [consolidated module](../packages/marty-common/marty_common/logging/consolidated_logging.py)
also retains `ServiceLogger`, `PerformanceTimer`, and `LoggingMixin.init_logging`
for existing Python consumers. For example:

```python
from marty_common.logging import ServiceLogger, PerformanceTimer

logger = ServiceLogger("compatibility_worker", __name__)
with PerformanceTimer(logger, "synthetic_operation"):
    logger.log_request_start("synthetic-request", "synthetic_operation")
    logger.log_request_end("synthetic-request", "synthetic_operation", success=True)
```

Existing services using the mixin can call `init_logging(service_name)` during
initialization. These helpers provide local context and timing; they do not
establish collector ingestion, production readiness, or complete event coverage.


Request context in the retained structured logger is local to the current
execution context. Updates copy the current values, nested scopes restore the
outer context even after exceptions, and clearing one request does not clear
another task or thread. Both structured and standard JSON outputs use the same
request/user/session/correlation field projection, including absent values as
`null` inside a nonempty context. Arbitrary context keys are not added to events.
Child tasks inherit their parent's context snapshot; detached work must clear or
replace it deliberately. This does not change the middleware's process-wide
logger setup or qualify multi-service logging configuration and ingestion.
