# API and onboarding qualification requirements

The old API-test launcher and empty API test skeleton are retired. Their README
named absent tests, fixtures and factories; it did not establish coverage.
The trust-profile onboarding checker only matched strings in retired nested
JavaScript/Python checkout paths. No runtime feature is retired by removing them.

Current deployed API and browser acceptance belongs to
[marty-ui](https://github.com/ElevenID/marty-ui) and
[marty-integration-tests](https://github.com/ElevenID/marty-integration-tests).
Reconcile and execute these inherited scenarios before claiming coverage:

- Real authentication and session failures, tenant/organization isolation,
  authorized organization reads/updates and input validation.
- API-key creation, scopes, expiry, listing/revoked filtering, revocation,
  deletion and IP allowlists; deny empty/invalid scopes and cross-tenant access.
- Webhook CRUD, URL/event/enabled configuration, authenticated delivery,
  independently verified HMAC, delivery history, retries and failure handling.
  Mocks alone do not qualify real delivery/security boundaries.
- Credential configuration, trust-profile, identity and subscription API
  behavior through current routes, persistence, constraints and negative cases.
- Vendor onboarding role/organization flow, trust-framework selection
  (ICAO/EUDI/AAMVA/custom where supported), validated payload and correct
  persisted organization/profile/framework linkage with tenant isolation.
  Qualify real browser-to-service E2E, rejection paths and repeat submissions.
- Disposable service-owned databases and fixtures, enforced foreign keys,
  controlled synthetic identities, cleanup, and a CI selection that executes
  the real tests and fails when required coverage is absent. SQLite mocks and
  source-text presence do not prove current Rust/PostgreSQL behavior.

These requirements remain open until current-owner tests demonstrate them.
Preserve actual models, routes and runtime capabilities; no placeholder test
suite or parallel Python service is supplied by this document.

## Business-focused onboarding requirements

The old business-onboarding implementation receipt is retired. Its named
UI/backend files and checked boxes did not qualify the current deployed flow.
Preserve these scenarios with the current UI/service owners:

- A business-language use-case wizard for travel, driving licences, EU
  credentials, employee/student IDs and access badges; multi-select cards and
  contextual acceptance/jurisdiction options, with a deliberate "set up later"
  path. Keep role, organization, verifier/issuer identity, trust sources, review
  and completion journeys coherent.
- Reviewed use-case mappings to ICAO, AAMVA, EUDI and custom profiles, including
  multiple passport/DTC profiles for travel and jurisdiction-specific state/EU
  defaults. Require correct payloads and persisted use-case tags; mappings
  need product/security ownership rather than assumed regulatory compliance.
- Progressive advanced configuration: inspect/edit generated profiles, add,
  delete or edit manual profiles and trust anchors/certificates/PKD sources.
  Preserve explicit auto-generated/manually-configured flags and human-readable
  display names distinct from stable technical names.
- Organization foreign keys, per-organization names, enabled framework/profile
  uniqueness policy, tenant isolation, validated status values and indexed
  tag/status lookup where appropriate. Reconcile multi-profile travel needs
  against uniqueness rules; do not silently impose conflicting old constraints.
- Dashboard setup/attention/readiness indicators based on measured certificate
  expiry and trust-list freshness, actionable follow-ups and expandable details.
  A green UI badge is not proof of standards or regulatory compliance.
- Current component, mapping, jurisdiction, manual-profile CRUD, status,
  persistence and E2E tests; migration upgrade/rollback on representative
  existing data with real constraints. Preserve data and failure handling.
