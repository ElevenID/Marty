# Presentation policy ownership and acceptance

The former cross-repository implementation summary mixed existing code, planned
features, and unchecked deployment claims. This note preserves the feature
intent and remaining acceptance work without claiming end-to-end completion.
No policy behavior, stored data, migration, or client feature is removed here.

## Current source owners

- [Rust presentation-policy service](https://github.com/ElevenID/marty-ui/tree/main/rust/services/presentation-policy)
  owns the service application, domain, persistence, transport, and configuration.
- [Native policy evaluation](https://github.com/ElevenID/marty-core/tree/main/marty-verification/src/policy)
  owns claim, issuer, freshness, disclosure, and ranking logic.
- [Authenticator policy operations](https://github.com/ElevenID/marty-authenticator/blob/main/rust/src/operations/policy.rs)
  and [verifier policy handling](https://github.com/ElevenID/marty-verifier/blob/main/src-tauri/src/commands/verification/policy.rs)
  are the client integration owners to qualify.

Source presence is not deployment or test evidence. Historical Python endpoint,
Alembic runner, `marty-sync`, Flutter widget/service, and storage paths are not
current setup instructions. Do not run old migration snippets or restore old
Python orchestration to satisfy this document.

## Feature decisions and requirements retained

- Give holders a clear required/optional claim view and informed choice to
  decline disclosure, with explicit non-compliance warnings and derived-attribute
  preferences. Holder choice does not imply a verifier must accept the result.
- Avoid third-party policy exposure and fingerprinting through protocol payloads;
  distribute policies only to authorized devices and scope cached policies to
  the relevant organization/deployment profile.
- Preserve credential type matching, required/optional claim paths, display
  labels and constraints, issuer allowlists, trust-profile requirements,
  freshness/age bounds, and raw-to-derived claim preferences. Qualify empty
  issuer-list semantics and missing/invalid dates explicitly.
- Preserve FRESHEST_FIRST, HIGHEST_TRUST_FIRST, MINIMUM_CLAIMS_FIRST and CUSTOM
  ranking intent, configurable freshness/trust/claim-count weights, stable
  tie-breaking, and minimum-disclosure selection. Verify actual native API names
  and weight validation; a field in the old example is not an implementation.
- Authenticate and authorize policy create/list/get/update/delete and sync.
  Validate schemas and ranking strategies and deny unauthorized cross-profile
  access. Qualify initial and delta sync, version/timestamp handling,
  If-Modified-Since/Last-Modified and 200/304 behavior where supported, and
  explicit typed failures. No old HTTP route is assumed to remain the contract.
- Qualify tenant/profile-scoped offline policy caching, serialization, version
  tracking, sync timestamps, stale/deleted policy handling, and notification of
  client updates. Background refresh, startup initialization and secure local
  storage remain requirements; the old six-hour refresh example is unqualified.
- Keep cryptographic validity distinct from policy compliance. The old summary
  treated policy violations as informational warnings; current Rust and consumer
  contracts must establish which failures warn, reject, or prevent a business
  action. Never turn failed cryptographic verification into policy success.
- Prove the real policy creation/update-to-sync-to-holder-selection-to-verifier
  flow with compliant, missing-claim, untrusted-issuer, stale, and untrusted-profile
  cases, including offline operation, access denial, and recovery after updates.
  A listed file, local mock, or claimed percentage is not coverage evidence.
- Preserve existing policy records and qualify schema migration/backfill,
  optional-field defaults, rollback, profile isolation and version audit history
  before declaring a replacement deployed. Do not delete data migrations merely
  because their old invocation examples are obsolete.

## Unfinished proposals

Constraint validation beyond presence (such as age and country predicates),
credential expiration, administrator versioning, templates, A/B testing,
compliance analytics, and pre-deployment impact simulation remain intent until
owned and demonstrated. Anomaly detection, federated learning, recommendations,
and zero-knowledge integration are longer-term proposals, not delivered features.

This cleanup verifies ownership paths and preserves requirements. It does not
qualify policy migration, deploy applications, or establish test coverage in the
service, native kernel, wallet, or verifier.
