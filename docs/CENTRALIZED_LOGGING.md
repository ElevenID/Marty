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
