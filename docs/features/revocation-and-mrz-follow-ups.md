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
