# Revocation and MRZ follow-ups

The old completion/verification reports and MRZ rewrite demonstration are
retired at Marty Git checkpoint `5e8d3d6`. They did not prove present production
readiness. The requirements below preserve their unfinished feature intent;
none is marked complete by this cleanup. Reconcile each against the current
canonical implementation and executed tests before closing it.

## Revocation and status-list feature requirements

Canonical runtime decisions belong to the current Rust status-list/revocation
owners in Marty Core and Marty UI. Keep existing profile APIs, credential-centric
delegation, tenant isolation and format behavior while qualifying these items:

- Actual Status List Manager integration and durable list updates. The reports
  described placeholders and an in-memory development repository; those claims
  are not acceptance for current implementations. Prove collision-free index
  allocation, full-list and concurrent-update behavior, persistent recovery and
  multi-instance/distributed coordination.
- SYNC, BATCH and ASYNC_QUEUE processing, durable publishing jobs, retries and
  bounded failure handling. Qualify the supported bitstring/token/legacy formats
  through their canonical encoders and independent verification; do not restore
  a Python encoding implementation or infer format support from old examples.
- Size/age-based rotation, credential transitions to a new list, archival,
  cleanup and version management without losing revocation history.
- Revocation/allocation/publication/delegation metrics, correlation-safe logs,
  alerts for unusual activity or unavailable services, and profile/list health
  views. Require load, failure, performance and security acceptance.
- Authenticated internal calls, authorized profile administration, rate limits,
  audit records and validated configuration. Existing feature access must not
  be replaced with unauthenticated examples from the old reports.
- Optional future migration tooling for inline `revocation_policy`, bulk profile
  creation, validation and reviewed rollback. OCSP/CRL fallback, registry
  federation, advanced analytics and multi-region operation remain proposals;
  they are not delivered by the retired reports.

The retained [profile proposal](../RevocationProfile_Proposal.md),
[integration architecture](../RevocationProfile_Integration_Architecture.md) and
[testing guide](../RevocationProfile_Testing_Guide.md) contain the feature design.
Their historical examples do not establish current supported deployment state.

## MRZ migration and parsing intent

The removed `migrate_mrz_usage.py` only analyzed imports and suggested edits;
its `--apply` path explicitly did not implement automatic application. The example
used obsolete `src.marty_common` imports. No bulk migration or new parser feature
is claimed complete by deleting those artifacts.

Preserve the intended hardened parsing and strict document-type/check-digit
validation requirements,
normalized results and caller compatibility through the existing canonical parser
and its thin adapters. `packages/marty-common/marty_common/utils/mrz_enhanced.py`
and `mrz_hardened.py` remain, along with live callers and native packaging tests.
Their `use_hardened` and `strict_mode` compatibility flags currently store the
selected value without selecting a distinct native parsing branch; any promised
mode distinction still needs an explicit native contract and executed tests.
Any future bulk refactor needs an inventory of real callers, a dry-run diff,
explicitly reviewed mappings and positive/negative document fixtures. It must
not add a second parsing/validation kernel or silently rewrite callers.

## Retired status tools and inherited roadmap requirements

The import/attribute-scoring scripts, score utilities, two `.py.legacy` backups,
completed agent reuse-review record, and remaining implementation-success reports
are retired from the working tree. Their prior source remains at Marty checkpoint
`decbfcf`. Hardcoded completion/quality percentages were not behavioral or release
acceptance. Runtime gRPC request validation, its schemas and sibling passport,
certificate/MRZ validation APIs remain; only the three scoring-helper exports
(`ModuleValidator`, `FeatureValidator`, `QualityMetricsAnalyzer`) are removed.
No tracked consumer was found outside the retired tool, including the workspace's
other repositories.

Retain the following historical ambitions as unclosed requirements until their
current canonical owners provide fresh evidence:

- Passport SOD/data-group integrity and certificate-chain validation; RFID/NFC,
  APDU, DG1/DG2 and secure messaging; EAC, active authentication, biometrics and
  CSCA trust; PKD/CRL/OCSP, PC/SC hardware and observability. Canonical protocol
  and crypto decisions belong to Marty Core; actual device/service/negative
  tests qualify them, not Python import or class-presence checks.
- OBv3 persistent repositories, publish/unpublish REST behavior, wallet
  compatibility and UI/end-to-end acceptance. Keep system compliance profiles
  read-only, expose only PUBLISHED templates, retain the template foreign key,
  derive wallet compatibility, enforce service-owned publication validation,
  and deny DRAFT Flow/policy dependencies. Bulk async application generation
  was outside the historical MVP and remains separately scoped work.
- Organization DID/trust validation, proper async-session injection, background
  batch processing, status-list allocation/updates, and remaining service
  observability migrations and tests. Earlier status reports close none of these.
- Deployment-profile runtime/lane synchronization and caching, online/offline/
  hybrid operation, locale/theme/operator controls, active policy and trust TTL,
  rollout percentages, version pinning and audit. Admin CRUD/device assignment
  and backend/verifier/end-to-end plus real-device acceptance need their own
  executed proof. Historical 'complete' labels are not that proof.
- The central service-configuration-factory design remains unresolved: retained
  Python compatibility sources still import `marty_common.service_config_factory`
  even though only a non-importable `.legacy` backup existed. Removing that
  backup does not supply a factory or retire those callers. Reconcile them with
  the current configuration owner or explicitly retire the obsolete consumers;
  do not restore a parallel Python framework solely from the backup.

Use [OBv3 readiness](../../src/digital_identity/docs/OBV3_READINESS.md) for that
feature's retained checklist and current source-bound owners for implementation.
Source fixtures, contracts, baselines and operational documentation remain
eligible for version control; generated reports use `reports/generated/`.

## Unclosed deployment and integration acceptance

Retired validation and integration-test reports at checkpoint `3b28fef` were
session summaries, not current acceptance results. The former tested basic Kind
operations and protobuf imports; it did not deploy and exercise the full service
stack because its Docker build hit resource limits. Full-stack startup, service
health, real cross-service requests and failure paths still need executed
acceptance against the supported deployment owners. Lightweight cluster checks
do not close that requirement.

The digital-identity report named an integration test file that is absent from
the current tree and admitted that unresolved `organizations` and
`trust_frameworks` foreign keys blocked execution. Preserve the intended CRUD,
linkage, persistence, event publication and negative-path coverage for trust
profiles, credential/application templates, presentation policies, deployment
profiles and flows. Scenarios include airport boarding, age predicates instead
of full birth dates, employee access, holder binding/freshness and multiple
online/offline/hybrid deployments with locale-specific UX. Reconcile schema
ownership and fixtures against the current service owners, then execute and add
their tests to CI. Do not weaken production foreign keys merely to unblock a
fixture. No test coverage or feature completion is claimed by deleting a report.

The retired database proof scripts connected to fixed localhost development
accounts and some created ad hoc test tables. Their config API and service-name
list are not current deployment contracts. Retain service-owned database
configuration, migrations and transaction boundaries, and qualify isolation and
cross-service access denial with disposable databases and the current owners'
positive/negative tests. Deleting the scripts supplies no new isolation proof.

Retired pre-commit checks targeted the removed Python framework, generators,
templates, CLI, UI and root Rust workspace. Current general code/security hooks
and protobuf compilation remain, together with CI and the source ownership and
native packaging tests. Platform Rust checks belong to their owning repositories;
the compatibility repository must not recreate the retired framework merely to
satisfy directory/substring heuristics.

The orphaned Kind/nginx, Sphereon/import, make-target, security-presence,
development-tool and template-debug checkers are retired too. They referenced
missing owners or performed source/import smoke checks rather than exercising
supported service behavior. Preserve actual security scanning, development setup
and retained configuration. OID4VCI/OID4VP wallet qualification, authenticated
service boundaries, real deployment behavior, current configuration validation
and positive/negative security tests remain obligations of their current owners;
removing these old scripts does not satisfy them.

Unused Kubernetes fixtures that imported a missing orchestrator are retired as
part of that closure. Disposable namespace lifecycle, service health/discovery,
authenticated gRPC, port-forward cleanup, deployment/Helm readiness, and useful
log/resource diagnostics remain test-infrastructure requirements for the current
UI/integration owners. Keep owned isolated environments and deterministic cleanup;
these prototypes were not executed proof of those capabilities. Existing test
markers, non-Kubernetes fixtures and current source/data fixtures remain.

The uncalled local-key generator, development-DSN mapper and obsolete Python
unittest drivers are retired. Signing-key provisioning and issuance acceptance
must use the current managed KMS/platform-signing boundary, not a second local
ES256 key manager. Database credentials and migration ownership remain explicit
current-owner configuration. Test selection must discover real current tests
and exercise their supported services; empty discovery and a missing deployment
are not passing integration evidence.

The empty Docker test skeleton and the orphaned phase-test/E2E shell wrappers
are retired as well. The skeleton contained no executable tests, and its README
pointed to absent service and passport-flow test files; the wrappers named absent
phase/performance tests or a retired Compose/UI stack. Real current service
coverage and passport issuance-to-verification E2E coverage, including multiple
sequential passports, startup/readiness, failure paths and isolated cleanup,
remain unmet requirements until current owners supply executed tests. Use the
repository's current pytest/Make/CI entrypoints for existing tests, and the UI
and integration repositories for supported deployed-service qualification.

## Retired profile receipt and failure-policy qualification

The old RevocationProfile implementation summary is retired. Preserve
credential-centric revoke/suspend/reinstate behavior, application-template and
trust-profile `revocation_profile_id` linkage, deliberate default-profile
selection, authorized admin lifecycle APIs and authenticated internal
allocation/processing APIs. Keep service-only endpoints off the public gateway
unless explicitly designed and authorized.

Qualify failures between credential state, status-list persistence and
publication. The historical local-success fallback did not implement or prove
durable retry; do not assume success means verifiers observe revocation.
Current owners must define fail-closed or durable pending/retry behavior,
idempotency, recovery and audit with executed negative tests. Inline-policy
migration needs validation, compatibility and reviewed rollback.
