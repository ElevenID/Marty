# Performance testing ownership and remaining requirements

Performance execution belongs to
[marty-performance](https://github.com/ElevenID/marty-performance).
Follow its [current runner instructions](https://github.com/ElevenID/marty-performance/blob/main/README.md)
for hardware qualification, digest-pinned stack preparation, synthetic gateway
workloads, test-window controls and result classes.

The compatibility repository's Python load/stress runner, shell wrapper,
threshold validator and dashboard generator are retired. They targeted old
Python services and fixed ports; the shell wrapper passed flags unsupported by
the runner. No tracked CI invocation was found. Their old Make commands and
claims of release-gating CI integration were not supported.

## Current coverage and limits

The native runner provides gateway smoke/readiness and an authenticated
management lifecycle workload, versioned workload contracts, execution profiles
and stable JSON evidence. Its foundation is not demonstrated parity for every
old intended workload. Broader lifecycle, issuance, verification, stress, burst
and soak qualification remains subject to the owning repository's roadmap.

Performance findings are advisory. Correctness failures and invalid test
conditions fail runs; latency and throughput changes do not gate releases.
The retired hardcoded service thresholds are not current SLOs or baselines.
Do not promote them into release gates without an explicit owner decision.

## Retained workload and measurement requirements

- Exercise real authenticated public service paths and business outcomes for
  trust/PKD, document/passport, credential issuance/presentation/verification
  and UI journeys. Health or documentation responses alone do not qualify them.
- Define steady-load concurrency, duration and arrival-rate limits; calibrated
  ramp-up/stress, burst and soak profiles; representative synthetic payloads;
  setup, warm-up, teardown and recovery. Record actual offered and achieved load.
- Record request counts, successful/failed outcomes, status/error categories,
  timeout/connection failures, response sizes, duration and throughput, plus
  mean, minimum, maximum and p50/p95/p99 latency with explicit units. Validate
  business correctness independently of an HTTP success status.
- Bind measurements to workload/fixture versions, released image digests,
  runtime/configuration, hardware/resource limits and result class. Compare
  only compatible runs, label migration previews and diagnostic profiling,
  and qualify repeated measurements before accepting a durable baseline.
- Retain useful raw results and machine-readable aggregates with bounded
  access/retention, sanitized request metadata and reproducible summaries.
  Trend analysis and regression review must preserve provenance and distinguish
  environmental noise from changes. Generated CSV/JSON/HTML/charts belong in
  ignored output or CI artifacts, not committed implementation proof.

## Observability and unfinished follow-ups

The retired generator could write dashboard/alert configuration, but no current
deployed replacement is established by deleting it. Retain request rate/volume,
status/error breakdown, latency histograms/percentiles, resource/database
bottleneck views and run correlation as current-owner requirements. Metrics
labels must remain bounded and must not expose credentials or identity data.

Qualify scrape/ingestion, dashboard queries, error-rate denominators and units,
alert delivery/routing/escalation, sustained-window behavior and absence of data.
Choose calibrated warning thresholds with owners; copying the old rate-as-percent
formula or arbitrary throughput limits is not acceptance. Verify logging and
monitoring failures and resource exhaustion alongside load failures.

Use [centralized logging requirements](CENTRALIZED_LOGGING.md) for shared event,
security and backend qualification. No workload, dashboard, alert or baseline
requirement is marked complete by this cleanup.
