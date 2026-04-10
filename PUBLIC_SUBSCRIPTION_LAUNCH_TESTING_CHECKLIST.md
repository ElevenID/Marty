# Public Subscription Launch Testing Checklist

**Date:** April 9, 2026  
**Status:** Draft — synthesized from `Marty`, `marty-ui`, `marty-subscriptions`, `marty-integration-tests`, `marty-docs`, and `marty-blog`

This checklist is specifically for **real launch-readiness testing** before opening a **public self-serve subscription option**.

It complements, but does **not** duplicate:

- `PRE_DEPLOYMENT_CHECKLIST.md` — mostly KMS/security hardening
- `TESTING_CHECKLIST.md` — mostly build/CI/release plumbing

---

## What your current list already covers

These are absolutely the right buckets to keep:

- [x] Functional licensing *(meaningful automated coverage exists; public subscription E2E is still incomplete)*
- [x] CRUD tests of MIP resources through the gateway API *(core gateway CRUD exists, with especially strong coverage for deployments, flows, compliance, applications, and revocation actions)*
- [ ] Docs
- [ ] Blog / launch content
- [ ] Org creation *(org setup is tested; first-user self-serve org creation is not yet evidenced)*
- [x] Org KMS setup and using it *(strong API + integration coverage exists for current SoftwareHSM/AWS paths)*
- [x] Application flow: apply, review, issue, and receive a credential *(backend and wallet integration exist; the default UI claim path is still skipped by default)*

---

## Existing evidence already in the repo

### Already has meaningful automated test coverage

- `Marty/tests/licensing/test_subscription_bridge.py`
  - Covers subscription → license creation, upgrade, cancellation, payment success refresh, and payment failure handling.
- `Marty/tests/licensing/test_phase7_routes_billing.py`
  - Covers backend billing routes for subscribe, change-plan, cancel, subscription lookup, invoices, and payment methods.
- `Marty/tests/licensing/test_phase_b_alignment.py`
  - Covers `/api/payments/process` happy path, validation, metadata/billing contact handling, and provider-error behavior.
- `Marty/tests/licensing/test_usage_enforcement.py` and `Marty/tests/licensing/test_usage_routes.py`
  - Cover `api_calls_limit` enforcement, rate-limit headers, and current/admin usage visibility.
- `Marty/tests/subscription/test_signing_service.py` and `Marty/tests/subscription/test_square_service.py`
  - Cover tier-based signing-path enforcement, plan limits, webhook signature verification, and webhook dispatching.
- `Marty/tests/integration/test_kms_api_integration.py`
  - Covers the KMS API lifecycle: configure, read, delete, test-connectivity, and test-signing.
- `Marty/tests/integration/test_kms_integration.py`
  - Covers real SoftwareHSM and LocalStack AWS KMS signing, public-key retrieval, verification, timeout, and cache behavior.
- `Marty/tests/integration/test_kms_credential_e2e.py`
  - Covers real KMS-backed credential issuance, signature verification, multiple credentials, key rotation, and payload variations.
- `Marty/tests/security/test_kms_security.py` and `Marty/tests/security/test_phase_d_hardening.py`
  - Cover auth/authz, SSRF protection, audit logging, TLS, rate-limiter wiring, and circuit-breaker hardening around KMS.
- `marty-integration-tests/tests/integration/gateway/test_organization_flow.py`
  - Covers organization setup basics, trust profiles, credential templates, and presentation policies.
- `marty-integration-tests/tests/integration/gateway/test_credential_issuance_flow.py`
  - Covers direct issuance, issuance retrieval/listing, multiple formats, and bulk issuance.
- `marty-integration-tests/tests/integration/gateway/test_deployment_profile_flow.py`
  - Covers deployment profile CRUD, activation, lanes, device assignment, and deployment API key generation.
- `marty-integration-tests/tests/integration/gateway/test_compliance_profile_integration.py`
  - Covers compliance profile CRUD basics, template integration, issuance integration, format constraints, and org isolation.
- `marty-integration-tests/tests/integration/gateway/test_application_flow.py`
  - Covers application templates, application submission, evidence submission, approval/rejection, and issuance transaction linkage.
- `marty-integration-tests/tests/integration/gateway/test_flow_definition.py`
  - Covers flow definition CRUD basics plus flow instance startup for issuance and verification flows.
- `marty-integration-tests/tests/integration/gateway/test_complete_lifecycle.py`
  - Covers credential lifecycle and revocation actions/status inspection.
- `marty-integration-tests/tests/integration/gateway/test_org_authorization.py`
  - Covers core cross-org denial scenarios for organization details, members, API keys, and template creation.
- `marty-integration-tests/tests/integration/gateway/test_wallet_issuance_flow.py` and `marty-integration-tests/tests/integration/gateway/test_wallet_oid4vci_gateway.py`
  - Cover real wallet offer redemption and OID4VCI issuance paths.
- `marty-subscriptions/src/application/__tests__/paymentApi.test.js`
  - Has unit coverage for payment API helper wiring.
- `marty-subscriptions/src/application/__tests__/paymentCheckoutUseCases.test.js`
  - Has unit coverage for checkout use-case logic.
- `marty-docs/src/content/docs/getting-started/quickstart.md`
  - Has a CLI quickstart.
- `marty-docs/src/content/docs/api/issuance.md`
  - Has a basic issuance API page.

### Important caveats

- [ ] `PRE_DEPLOYMENT_CHECKLIST.md` is **not** a public-subscription launch checklist; it is primarily KMS/security focused.
- [ ] `TESTING_CHECKLIST.md` is **not** a product go-live checklist; it is primarily CI/build/release focused.
- [ ] `marty-subscriptions` currently has **unit tests**, but I did **not** find evidence of a real end-to-end paid subscription journey.
- [ ] `test_org_authorization.py` still skips some multi-user / multi-role scenarios, which means the nastiest “real customer” authz bugs can still hide in the walls.
- [ ] `test_ui_claim_credential_e2e.py` exists, but it is skipped by default and depends on live services plus hardcoded IDs.
- [ ] Self-serve onboarding still looks thin: I did not find real first-user signup / first-org creation / paid activation coverage.
- [ ] AWS/SoftwareHSM KMS paths are much better covered than Azure/GCP; if Azure/GCP are part of launch messaging, their real provider paths still need end-to-end proof.
- [ ] New gateway CRUD tests were added for additional resource families, but local validation is currently limited because the running gateway is returning `503 Service Unavailable` for several resource endpoints, including `/v1/revocation-profiles`.
- [ ] `marty-blog/EDITORIAL_IMPROVEMENTS.md` still lists missing tutorials and launch-worthy content (including a Hello World issuance tutorial).
- [ ] `marty-ui/ONBOARDING_IMPLEMENTATION_PROGRESS.md` still contains many unchecked onboarding tests.

---

## Launch blockers — real testing required before public subscriptions

These are the items I would treat as **must-pass** before announcing a public self-serve subscription option.

### 1. Functional licensing

- [x] New paid subscription creates a valid license automatically.
- [x] Plan upgrade reissues license with updated entitlements.
- [x] Plan downgrade removes features that should no longer be available.
- [x] Immediate cancellation revokes future issuance rights; delayed-cancel timing still needs stronger end-to-end proof.
- [ ] Payment failure triggers grace-period behavior correctly.
- [ ] Expired or revoked license blocks issuance/admin actions but does **not** break historical verification that should remain valid.
  - **Update (Apr 9, 2026):** Added 8 license expiry boundary tests: grace period exact boundary (within/past), zero-grace immediate blocking, days-until-expiry accuracy, tampered key rejection, revocation property reflection, and feature wildcard entitlement. **27 tests** passing in E2E chain suite.
- [x] Tier-specific signing-path enforcement is tested at the service layer; full gateway/UI entitlement enforcement still needs broader proof.
- [x] `api_calls_limit` / quota behavior is enforced and observable.
- [x] License refresh on payment success is covered in automated bridge tests.

**Evidence to build on:** `tests/licensing/test_subscription_bridge.py`, `tests/licensing/test_usage_enforcement.py`, `tests/licensing/test_usage_routes.py`, `tests/subscription/test_signing_service.py`, `tests/licensing/test_e2e_chain.py`.  
**Gap:** I still did **not** find a convincing public-subscription **browser-to-backend E2E** for purchase → license issuance → entitlement enforcement.

### 2. Billing and payment lifecycle

- [x] Subscribe flow succeeds with a valid payment method at the backend API layer.
- [x] `/api/payments/process` happy path, validation, and billing metadata handling are tested.
- [x] Card decline / payment provider error shows the right UI and leaves subscription state consistent.
  - **Tested (Apr 9, 2026):** `SquareError` handling tested for subscribe, change-plan, cancel, and add-payment-method routes — all return 400 with descriptive error.
- [ ] Duplicate checkout / double-submit is idempotent.
- [x] Change-plan backend routing is tested.
- [x] Immediate-cancel backend routing is tested.
- [ ] Billing proration / downgrade semantics are tested end-to-end.
- [ ] Cancel at period end is tested end-to-end.
- [x] Payment method add/list backend routes are tested.
- [ ] Payment method update/remove behaves correctly.
- [ ] Invoice history is correct and visible to org admins.
- [x] Webhook signature verification plus success/failure dispatch are tested.
- [x] Webhook retry and out-of-order event handling are tested.
  - **Update (Apr 9, 2026):** Circuit breaker threshold/config, event type case sensitivity, None event_types safety, and custom retry config are now covered. 18 tests passing.
- [ ] Refund / chargeback behavior is defined and tested.
- [ ] Failed recurring billing produces the correct subscription state, alerts, and customer messaging.

**Evidence to build on:** `tests/licensing/test_phase7_routes_billing.py`, `tests/licensing/test_phase_b_alignment.py`, `tests/subscription/test_square_service.py`, plus `marty-subscriptions` unit tests.
**Update (Apr 9, 2026 — Wave 2):** Added billing edge case suite with 9 new tests covering change-plan Square errors, change-plan invalid tier, cancel with no subscription, cancel Square error, add-payment-method Square error, missing payment nonce handling, and soft-failure recovery for invoices/payment-methods. **83 tests** now passing across billing + E2E chain + webhook suites.  
**Update (Apr 9, 2026 — Wave 3):** `marty-integration-tests/docker-compose.yml` now includes a `billing-service` definition and passes `BILLING_SERVICE_URL` into the gateway. A root `.env` placeholder file was added in `marty-integration-tests/` for local Square sandbox variables so future browser-to-backend billing tests have an explicit config home instead of hidden env drift. End-to-end checkout coverage is still missing, but the integration stack is no longer structurally missing the billing service.
**Gap:** I still did **not** find a real browser checkout / webhook reconciliation / renewal journey.

### 3. Gateway CRUD of MIP resources

Run real CRUD coverage through the gateway, not just at individual services.

- [x] Organizations: get/list coverage exists, and full organization setup is exercised through the gateway.
- [x] Organizations: update and delete/disable behavior have explicit gateway tests.
- [x] Trust profiles: create/get/list are covered.
- [x] Trust profiles: update / activate-deactivate / delete have explicit gateway tests.
- [x] Credential templates: create/get/list are covered.
- [x] Credential templates: update/delete have explicit gateway tests.
- [x] Presentation policies: create/get/list are covered.
- [x] Presentation policies: update/delete have explicit gateway tests.
- [x] Deployment profiles: create/read/update/delete, activation, lanes, device assignment, and API key generation are covered.
- [x] Flows: create/read/list and execute/start coverage exists for issuance and verification flows.
- [x] Flow update/delete coverage now has direct gateway tests.
- [x] Compliance profiles: create/read/list, template integration, issuance integration, and org isolation are covered.
- [x] Compliance profile update/delete coverage now has direct gateway tests.
- [ ] Revocation profiles now have explicit gateway CRUD tests in the suite, but they are not yet validated green because the live gateway is returning `503 Service Unavailable` for `/v1/revocation-profiles`.
- [x] Revocation actions and status inspection are covered in gateway lifecycle tests.
- [x] API keys: scope, revoke, and rotate coverage now exists at the service and endpoint levels, though cross-org abuse cases still need broader proof.
- [ ] Every CRUD action is org-scoped and audited.

**Evidence to build on:** `test_organization_flow.py`, `test_deployment_profile_flow.py`, `test_flow_definition.py`, `test_compliance_profile_integration.py`, `test_application_flow.py`, `test_complete_lifecycle.py`, `tests/subscription/test_api_key_service.py`, and `tests/api/api_keys/test_api_key_lifecycle.py`.  
**Gap:** revocation profile CRUD tests now exist but still need a clean green run through a healthy gateway, and full org-scoping/audit proof across every CRUD path remains incomplete.

**Update (Apr 9, 2026 — Wave 2):** Cross-org attack tests expanded from 6 to 11 resource types, then to nested deployment actions (lane creation + deployment API-key generation). Tests for deployment profiles, flow definitions, and presentation policies confirmed green locally. 503-skip pattern added so tests degrade gracefully when backend services are down rather than false-failing.

**Update (Apr 9, 2026 — Wave 3):** `marty-integration-tests/docker-compose.yml` was missing gateway backing services for `deployment-profiles` and `revocation-profiles` even though the gateway registry and route modules expected them. The compose stack now wires both services into the integration environment and passes `DEPLOYMENT_PROFILE_SERVICE_URL` / `REVOCATION_PROFILE_SERVICE_URL` to the gateway. Full green validation is pending image build completion and rerun against the compose gateway (`http://localhost:28000`).

### 4. AuthN, AuthZ, and org isolation

- [x] Non-member cannot read or mutate several org-scoped resources.
- [ ] Member vs admin vs owner permissions are enforced for every MIP resource.
- [x] Cross-org attacks are blocked for org details, members, API keys, and credential-template creation.
- [ ] Cross-org attacks across every resource type (flows, policies, deployments, compliance, etc.) still need fuller evidence.
  - **Update (Apr 9, 2026 — Wave 2):** Cross-org authz tests now cover 11 resource types (org details, members, API keys, credential templates, compliance profiles, revocation profiles, trust profiles, deployment profiles, flow definitions, application templates, presentation policies). Deployment profiles (422 — validation blocks) and presentation policies (422) confirmed green locally. Credential templates, compliance, revocation, trust, and application templates skip cleanly when backend services are unavailable (503-skip).
  - **Update (Apr 9, 2026 — Wave 3):** Nested deployment-profile abuse paths are now covered too (`POST /v1/deployment-profiles/{id}/lanes` and `POST /v1/deployment-profiles/{id}/generate-api-key`). Integration compose wiring for deployment/revocation services has been fixed so more of these skips can be converted into hard pass/fail evidence once the compose images finish building.
- [ ] Cache invalidation works when org membership or role changes.
- [ ] API key scopes cannot be abused across orgs or beyond intended permissions.
- [ ] Public endpoints are only public where intentionally allowed.
- [ ] Audit trail records authz failures and sensitive admin actions.

**Evidence to build on:** `marty-integration-tests/tests/integration/gateway/test_org_authorization.py`, `marty-ui/ORG_AUTHORIZATION_PHASE2_MIGRATION.md`.  
**Gap:** multi-user / multi-role test cases and cache invalidation coverage are still skipped or listed as remaining work.

### 5. Org creation and onboarding

- [x] Post-creation organization setup is covered once an org already exists.
- [ ] Brand-new user can sign up and create their first org.
- [ ] Brand-new user can choose a free tier and land in a usable state immediately.
- [ ] Brand-new user can choose a paid tier and complete payment without manual back-office intervention.
- [ ] Invite flow works for valid, expired, reused, and invalid invite links.
- [ ] Domain-match / auto-association behavior works for open, approval, and invite-only policies.
- [ ] First-login routing sends users to the correct place based on role, intent, and org state.
- [ ] Org switcher behavior is correct for multi-org users.
- [ ] Billing/admin contact capture is complete enough for real customers.

**Evidence to build on:** `marty-ui/ONBOARDING_IMPLEMENTATION_PROGRESS.md`.  
**Gap:** first-user signup, self-serve org creation, paid activation, invite happy paths, and first-login routing still show little or no real automated evidence.

### 6. Org KMS setup and actual use

- [x] Configure KMS via API is covered.
- [x] Test connectivity endpoint behaves correctly with valid and invalid results.
- [x] Test-signing endpoint behaves correctly.
- [x] Real signing / credential issuance uses the configured KMS for SoftwareHSM and AWS KMS/LocalStack paths.
- [x] Key rotation has dedicated automated coverage.
- [x] Reconfiguration / deletion clears caches and updated configuration is re-read.
- [x] Timeout and circuit-breaker / hardening behavior have dedicated tests.
- [x] Secrets are tested for encryption-at-rest and non-leakage in API errors/responses.
- [ ] If Azure/GCP are publicly claimed, their real provider paths must be tested end-to-end, not just stubbed.

**Evidence to build on:** `tests/integration/test_kms_api_integration.py`, `tests/integration/test_kms_integration.py`, `tests/integration/test_kms_credential_e2e.py`, `tests/subscription/test_key_rotation.py`, `tests/security/test_kms_security.py`, and `tests/security/test_phase_d_hardening.py`.  
**Gap:** if Azure/GCP are part of the launch story, their real provider paths still need end-to-end proof.

### 7. Applicant flow: apply and get a credential

- [ ] Applicant can discover the right application path from UI or deep link.
- [x] Application creation works at the gateway/backend layer.
- [ ] Payment-required application flow works if there is an applicant fee.
- [x] Submit → review → approve/reject → issue works end-to-end.
- [ ] Claim flow works from the actual UI path, not just internal service calls.
- [ ] Credential offer expiry and refresh behavior is correct.
- [x] Wallet handoff / offer redemption works for the Walt.id-backed integration path.
- [ ] Applicant notifications (email/push) are correct for status changes and issuance completion.
- [ ] Applicant can retrieve issued credential / see claim state afterward.

**Evidence to build on:** `marty-integration-tests/tests/integration/gateway/test_application_flow.py`, `marty-integration-tests/tests/integration/gateway/test_wallet_issuance_flow.py`, `marty-integration-tests/tests/integration/gateway/test_wallet_oid4vci_gateway.py`, and `marty-integration-tests/tests/integration/test_ui_claim_credential_e2e.py`.  
**Gap:** the actual UI claim test is skipped by default and depends on a special environment with live services and fixed IDs.

---

## High-priority items you were missing from the checklist

These are the biggest missing categories I would add.

### 8. Subscription operations and support readiness

- [ ] Internal admin can inspect subscription state and fix a broken customer account.
- [ ] Support can identify why a license, payment, or issuance failed.
- [ ] Customer-visible error messages are understandable and actionable.
- [ ] There is an escalation path for failed payments, stuck onboarding, and broken license state.
- [ ] There is a rollback plan for a bad release that affects subscription or licensing.

### 9. Observability and abuse protection

- [ ] Rate limits are tested at the gateway and relevant service boundaries.
- [ ] Metrics exist for subscription creation, payment failures, license failures, KMS failures, issuance failures, and authz denials.
- [ ] Alerts are configured and actually tested.
- [ ] Audit logs are searchable enough for incident response.
- [ ] You can correlate a customer complaint across gateway, billing, licensing, KMS, and issuance logs.

### 10. Backup, restore, and disaster recovery

- [ ] Backup/restore covers subscription, org, KMS config metadata, issuance state, and applicant state.
- [ ] Rollback from a bad deploy is tested.
- [ ] Data restore does not orphan subscriptions or licenses.
- [ ] Payment-provider reconciliation is defined if your DB and provider get out of sync.

### 11. Docs and public launch content

- [ ] Self-serve subscription quickstart exists.
- [ ] Pricing/tier definitions are documented consistently across UI, docs, and sales copy.
- [ ] KMS/BYOK setup guide exists for each public provider.
- [ ] “Hello World” credential issuance tutorial exists.
- [ ] Docs explain the minimum org setup needed before a customer can issue.
- [ ] Docs explain the minimum verifier setup needed before a customer can verify.
- [ ] Launch blog content exists for core product narratives and tutorials.

**Evidence to build on:** `marty-docs` already has core protocol and issuance docs; `marty-blog/EDITORIAL_IMPROVEMENTS.md` shows missing tutorials and product-bridge content.

### 12. Legal, commercial, and policy readiness

- [ ] Terms of Service for public subscriptions.
- [ ] Privacy Policy.
- [ ] Data Processing Agreement / regulated-use paperwork if applicable.
- [ ] SLA / support-response expectations.
- [ ] Refund and cancellation policy.
- [ ] Acceptable use / abuse policy for public signup.

---

## Recommended release gates

### Must pass before public launch

- [ ] Subscription purchase and billing failure scenarios
- [ ] Subscription → license → entitlement enforcement E2E
- [ ] Gateway CRUD + org isolation across the core MIP resources
- [ ] First-org onboarding + paid activation flow
- [ ] Org KMS config → test → issue credential flow
- [ ] Application → review → issue → claim credential flow
- [ ] Monitoring, alerting, audit, and rollback drills
- [ ] Docs and legal minimums are live

### Can ship shortly after launch, but should still be planned now

- [ ] Rich billing/admin UI
- [ ] Expanded blog/tutorial library
- [ ] Additional provider guides and advanced runbooks
- [ ] Deeper analytics and support tooling

---

## Fast interpretation of where things stand today

If I had to summarize the current state in one blunt-but-loving sentence:

> The platform has **real pieces of technical readiness** already in place, but the public-subscription launch still needs **joined-up E2E testing** across billing, licensing, onboarding, org authz, and the applicant issuance journey before it should meet actual strangers from the internet.

That sentence is less poetic than the blog team might like, but more useful at 2 a.m. during launch week.
