# Compatibility consolidation and manual scanning

## Manual security scanner

Python 3.11 or newer and uv are sufficient for the Bandit code scan; it reads
its exact version, all maintained source/script targets and plugin exclusions
from `pyproject.toml`. Local pre-commit and required CI use this same fail-closed
runner. Other checks require their selected scanner dependencies; dependency
auditing also requires the installed project in the active interpreter.

```sh
python scripts/security_scan.py code
python scripts/security_scan.py deps
python scripts/security_scan.py secrets
python scripts/security_scan.py containers --image REGISTRY/IMAGE@sha256:DIGEST
python scripts/security_scan.py containers --filesystem PATH
python scripts/security_scan.py code --tool semgrep
```

Actions select Bandit, pip-audit, detect-secrets, and Syft/Grype respectively.
`full` selects those automated checks; it requires an explicit container or
filesystem target too. `dependencies` remains an alias for `deps`. Optional
`--tool` adapters retain Safety, Semgrep, TruffleHog, git-secrets and hadolint;
hadolint requires explicit `--dockerfile` paths. No scanner is installed globally,
no arbitrary local images are selected, and no Compose build is attempted.

Results are isolated in a new ignored `reports/generated/security/` run directory,
or a new explicit `--output-dir`. Existing directories are rejected so stale
reports cannot become new acceptance. `summary.json` names the selected checks;
raw tool output stays in that directory and may contain sensitive findings.
Use bounded private retention and do not commit these reports. `--ephemeral`
instead removes temporary reports on exit; the local hook and CI use it. Bandit
then prints file/line/rule diagnostics without copying source or secret literals.

- Exit 0: selected tools returned recognized clean results.
- Exit 1: recognized results contain findings, regardless of a tool's own zero
  exit status (for example detect-secrets or Grype).
- Exit 2: missing tools/targets, timeouts, scanner errors, invalid/empty evidence
  or manual-only qualification. An unclassified git-secrets failure is an error,
  not an inferred finding count. `compliance` deliberately returns manual/incomplete;
  source counts and grep matches are not compliance proof.

Dependency auditing uses the active interpreter with an installed Marty project,
not a fresh tool-only environment. Partial/skipped package audits are incomplete.
Secret scanning neither creates nor approves a baseline and disables external
credential verification. The pre-commit detect-secrets baseline referenced in
this tree is absent; it still needs reviewed provisioning before that separate
hook can be claimed operational. Optional tools may require their own policy,
authentication, rules or vulnerability databases; installing an adapter does
not establish successful execution or equivalent detection coverage.
The git-secrets adapter requires nonempty `secrets.patterns` configuration;
an allowlist or provider-only configuration does not qualify this adapter.
It does not register patterns or print their values into the summary.

The removed shell report generators, custom keyword dumps, source-count compliance
scores and arbitrary image inventory did not qualify security behavior. Current
[security requirements](../SECURITY.md) remain open under their owning services.
Only the Bandit code action is enforced by the existing CI Gate. Other manual
adapters do not add CI/release gates or replace those requirements.

## Monitoring namespaces

`marty_common.monitoring` remains the health-monitoring package. Its existing
`HealthCheck`, `Metric`, `Alert`, `MetricsCollector`, `HealthMonitor` and
`create_default_monitor` exports retain their constructors and behavior.

The formerly shadowed sibling `monitoring.py` implementation now lives at
`marty_common.monitoring.service_monitor`. Its distinct callback-based health
checks and typed service metrics remain there; they are not replacements for
the package's object model. Nonconflicting service factories, `ServiceMonitor`,
`ServiceInfo`, `MetricType`, `MetricsInterceptor` and `monitor_operation` are
available lazily through the package. Health-status and alert-severity enums
are shared. Trust monitoring remains untouched. No service/thread starts merely
by importing the package, and no runtime readiness is claimed by this move.
The gRPC metrics interceptor now returns a proper method handler with the original
serializers and request/response cardinality. Streaming success and duration are
recorded when response iteration finishes, and iteration failures record errors.

## Retry compatibility

`resilience.retry` owns the common Tenacity policy and retry configuration/metric
types. `resilience.retry_enhanced` retains its public names as a thin facade.
Old import paths and pickled class references resolve; the basic and enhanced
metric registries remain separate, including same-name operation histories.
Each facade retains its logger and configured exception selection. In particular,
the default exception tuple still takes precedence over the broader classifier.

The combined attempt/deadline stop policy is fixed to use Tenacity's stop
composition rather than a raw list, so the default timeout configuration can
actually retry. Backoff selection and decorator signatures are otherwise retained.

`AdvancedRetryManager` and `AdvancedRetryConfig` remain distinct: their abort
exceptions, circuit breaker, adaptive strategies and statistics are not equivalent
to the simple decorators. Their current implementation is not deleted or silently
mapped to a weaker policy. Broader scheduling/metrics/API changes require their
own compatibility decisions and tests.

## Configuration and listener ownership

The uncalled `create_development_config`/`create_production_config` example
factories and PKD's unused `utils.config.get_config` dictionary adapter are
retired. Keep the actual configuration models, YAML/environment loaders,
validation and serialization. The removed examples were not production secret
provisioning: placeholder JWT/encryption credentials and a shared temporary
trust cache must not become runtime defaults.

Current deployment configuration belongs to Rust service/platform owners.
Preserve the examples' useful requirements there: required database credentials
and TLS, bounded pools and PKD retry/timeouts, fail-closed trust refresh with
staleness thresholds, owned cache/backup directories, monitoring/tracing options,
rotation overlap/scheduling/backup retention, and environment-specific resource,
replica and health/readiness settings. Concrete example hostnames, development
passwords and unresolved `${...}` strings are not credentials or deployment inputs.
OpenXPKI credentials must use the maintained provider's explicit environment/file
resolution; its TLS policy, realm, endpoint, timeouts and local store still need
provider-owner qualification. Removing the unused dictionary does not change or
qualify that provider.

The Python metrics server and trust-service listener now default to loopback.
Their routes and explicit bind controls remain: pass `host` to metrics helpers
or set `TRUST_SVC_HOST` deliberately for a container/private network. An explicit
all-interface bind still requires deployment access control; these compatibility
listeners are not authenticated public endpoints.

## gRPC authentication and authorization

The published Python gRPC/Cedar APIs remain for compatibility. The interceptor
wraps all four RPC cardinalities and scopes identity to handler execution;
`require` reads that context rather than decoding caller metadata. It preserves
policy evaluation and file loading. No tracked production server currently
constructs this interceptor, so these checks do not establish deployed coverage.
Services adopting it must wire it to `grpc.aio.server(interceptors=[...])` and
qualify their Cedar policies, authenticated transport and actual RPCs.

JWT validation uses Core's Rust `oidc_validate_id_token` public operation, with
required signature, issuer, audience, subject, issued-at and expiry validation.
Configure `MARTY_JWT_JWKS_FILE`, `MARTY_JWT_ISSUER`, `MARTY_JWT_AUDIENCE` and an
asymmetric `MARTY_JWT_ALGORITHM` (default RS256). Alternatively supply a public
PEM using `MARTY_JWT_PUBLIC_KEY` and its `MARTY_JWT_KEY_ID`; conversion is also
native. Shared-secret/HS authentication and disabling authentication are retired.
This is an explicit OIDC JWT profile, not opaque OAuth-token introspection.
Missing/incompatible native validation fails closed; no Python crypto fallback
or long-term signing key is introduced. Production rotation/JWKS refresh remains
an operator-owned requirement; the interceptor snapshots supplied public keys.

Without a bearer credential, verified gRPC TLS peer identity may authenticate.
Caller `x-client-cert*` headers never establish identity or roles. A supplied
invalid/duplicate bearer credential never falls back to TLS. Only the exact
standard Health/Check and Health/Watch methods may bypass authentication; those
handlers receive no authenticated identity. Certificates do not automatically
grant roles based on organizational-unit strings. Configure authorization for
the selected certificate identity explicitly. Context is reset after completion,
error or cancellation; independent concurrent requests do not share principals.

## mDoc signing compatibility

All eight legacy RPCs remain, including incomplete QR/device-transfer/template
work. They are not replaced by a narrower Rust format builder. The adapter no
longer fabricates signature bytes or ignores recording errors. Before signing,
inject trusted signer-version profiles through `verification_keys`, mapping
signer id to `(algorithm, public SPKI DER)`. Missing configuration fails closed.
The signer must return a successful typed protobuf response with nonempty
signature, configured signer id and timezone-bearing timestamp. Rust verifies
the signature before recording it and setting ACTIVE. Verification recomputes
the signature over current document data and returns consistent validity flags.

Signing content is the deterministic serialized `MDocResponse` with
`signature_info` and lifecycle `status` cleared. This binds document identity,
person fields, images, custom fields and creation data. The signature wrapper's
timestamp is presentation metadata, not authenticated issuance time; signer id
selects a configured verification key and is not independently signed provenance.
This retained gRPC envelope is not ISO 18013 MSO encoding. No tracked production
runtime constructs the adapter. Managed signer provenance, profile distribution,
tenant/key-version lifecycle, persistence, interoperability and a real device
transfer implementation still require Rust-owner work. No KMS worker code or
deployment path is changed by this compatibility cleanup.
