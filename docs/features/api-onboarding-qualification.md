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
