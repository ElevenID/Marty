# Deployment profile ownership and qualification

Deployment profiles, lanes, device synchronization, and update rollout remain
features to preserve. The former migration/update tutorials mixed current source
with old Python endpoints, deployment commands, and unverified completion claims.
This guide changes no application, assignment, configuration, schema, or data.

## Current source owners

- [Rust deployment-profile service](https://github.com/ElevenID/marty-ui/tree/main/rust/services/deployment-profile)
  owns service domain, persistence/migration, HTTP and gateway contracts.
- Verifier [profile synchronization](https://github.com/ElevenID/marty-verifier/blob/main/src-tauri/src/commands/profile_sync.rs)
  and [runtime configuration](https://github.com/ElevenID/marty-verifier/blob/main/src-tauri/src/runtime_config.rs)
  own applying device/profile/lane settings.
- Verifier [sync types and rollout selection](https://github.com/ElevenID/marty-verifier/blob/main/crates/marty-sync/src/profile_sync.rs)
  and [update commands](https://github.com/ElevenID/marty-verifier/blob/main/src-tauri/src/commands/update.rs)
  own the client contracts to qualify.

Use the owners' actual schemas, authorization, installation procedures and tests.
The old Python service examples, guessed HTTP routes, local DB
queries, SSH/systemd copy loops and environment snippets are not a supported
migration recipe. Historical dates, deployment durations, payload sizes, startup
timings and fleet percentages are not measured acceptance results.

## Profile and migration acceptance retained

- Inventory existing device IDs, sites, profiles, lane assignments, configuration
  files/environment overrides, network modes, software versions and operator
  settings. Preserve records and review a per-device mapping before applying it.
- Qualify authorized profile/lane create, read, update, delete and device
  assignment/reassignment against tenant/site/device binding. Validate references,
  missing/deleted assignments and concurrent updates, with auditable outcomes.
- Preserve profile defaults, explicit policy selection and lane override intent
  (lane > explicit > profile). Prove the actual precedence and dependent policy
  synchronization through the current runtime, including presentation/issuance
  policies and trust/cache lifetime where required.
- Preserve online, offline and air-gapped requirements. Qualify network blocking,
  startup with unavailable service, cached operation, expiry and reconnect behavior.
  Authenticated offline/USB import is a requirement to demonstrate, not a feature
  established by the old tutorial. Hybrid operation also needs an explicit owner.
- Preserve theme/locale/language, operator biometric controls, audit flags, cache
  TTL and update settings. Verify runtime/UI application, missing-field defaults,
  tampering/access protection, and error visibility; a synchronized row alone
  does not prove enforced device behavior.
- Qualify authenticated profile sync over certificate-validated HTTPS, scoped and
  rotatable credentials, actual endpoint and response types,
  version/change detection, cache persistence, deletion/staleness handling and
  recovery. The old fixed background-sync interval is not current policy.
- Qualify versioned schema migration, backfill and configuration conversion on
  representative existing data, with backup/restore and reversible assignment
  changes. Do not delete migrations or copy old database commands blindly.
- Stage a reviewed canary, observe sync errors, effective policy, network/UX and
  update behavior, then expand only under the release owner's procedures. Test
  rollback of binary/config/schema/cache/assignments and retention of audit data.

## Update rollout acceptance and open decisions

The current verifier update commands require updates enabled and a configured
update public key. They resolve the channel, check an available update, and gate
installation on rollout eligibility. The eligibility helper currently allows
updates when device ID or deployment profile is absent; this is an observed
source behavior to review with the release owner, not approval of that policy.
It checks a pinned version and calls the sync provider's `DefaultHasher`-based
cohort selector. The old table of example device buckets is not a durable cohort
contract and does not establish stability across releases or platforms.

Retain acceptance for signed updater validation and trusted channel/endpoint
configuration; exact version pins and mismatches; 0% freeze and 100% eligibility;
intermediate cohort distribution, repeatability and cross-version stability;
and both check-time reporting and install-time enforcement. Exercise missing or
invalid device/profile settings, malformed percentages, policy changes between
check and install, download/signature failures, interrupted installation and
recovery. Decide the missing-context and cohort-compatibility policies explicitly
before relying on them operationally. This cleanup implements neither decision.

Record eligibility/rejection reasons, checked/downloaded/installed outcomes,
version distribution, time-to-rollout and per-device failures without exposing
credentials. Qualify real-device canary and rollback, observability, load/startup
impact and operator diagnostics through executed owner tests.

Backend ring targeting (canary/beta/production), timed rollout schedules,
centralized telemetry, automatic pause thresholds and emergency rollback to a
specified version remain proposals until their contracts and implementations
are demonstrated. Ring names and rollback JSON in the old examples do not
establish implemented deployment APIs. No deployment or end-to-end qualification is claimed
by consolidating these documents.
