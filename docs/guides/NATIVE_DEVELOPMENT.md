# Development ownership and UI qualification

This compatibility repository does not host the retired Python `ui_app` or
nested Python/React development stack. Use the current
[marty-ui setup guide](https://github.com/ElevenID/marty-ui/blob/main/DEVELOPMENT_SETUP.md)
and that repository's workflows for the React UI, Rust services, gateway,
identity provider, databases and service configuration. Native security kernels
belong to [marty-core](https://github.com/ElevenID/marty-core); wallet/device
acceptance belongs with the UI, authenticator and integration owners.

The orphan `tests/ui` fixture/bootstrap bundle is retired. It imported the
missing Python UI, enabled mock fallbacks, and advertised test modules/runner
that are absent. Its bootstrap installed unpinned packages/browsers and rewrote
checkout test/editor settings. No real browser suite is removed. The unused
Python Playwright dependency and mypy entry retire with their only consumers;
the UI owner's browser tooling remains separate. Use this repository's root
Makefile for retained package/native compatibility checks.

## Browser acceptance requirements

The old scaffolds described intended coverage, not demonstrated implementation.
Reconcile these requirements with current UI/Rust owners and real acceptance
before claiming the matrix is complete:

- Admin, CSCA, document signer, mDoc, DTC, PKD, trust-anchor and mDL navigation,
  forms, validation, results and lifecycle operations. Exercise success and
  rejection/error states with authenticated role and tenant boundaries.
- Synthetic passport and mDL claims, issuer/subject/trust metadata and validity;
  DTC emergency-travel, visitor and temporary-resident scenarios with relevant
  purpose, sponsor, contact and bounded-validity inputs. Do not copy fixed
  identities or expired sample dates as production defaults.
- Cross-service transitions, asynchronous responses, slow/unavailable services,
  repeat/retry behavior and safe cleanup. Mock component tests are useful but
  must not turn service failure into successful verification or issuance.
- Desktop/tablet/mobile layouts, keyboard/screen-reader accessibility, browser
  coverage and measured performance/load limits. Keep fast subsets distinct
  from the full workflow/device matrix.
- Real holder consent, wallet presentation and verification, revocation and
  managed-KMS signing/lifecycle rejection. Neither a displayed success message
  nor a simulated device qualifies interoperability.
- Bounded diagnostic screenshots/traces/reports with secret and identity
  redaction, retention and deterministic teardown. Keep generated browser and
  acceptance artifacts outside version control.

Local development still needs realistic, isolated identity/session/database
infrastructure, scoped credentials, verified ingress/TLS and responsive service
feedback. The removed MMF path mounts, proxy file paths, fixed demo passwords
and old Docker/Make commands are not configuration to restore.

## Onboarding resume acceptance remains open

The uncalled Python/curl resume reproducers and their old guide targeted retired
registration/login and onboarding-complete routes. Removing them does not prove
that the historical false-403 bug is fixed. A mocked existing-organization
component test alone does not qualify the current deployed flow.

Use the current UI and Rust organization/authentication contracts in a disposable
isolated tenant to exercise this journey:

1. A vendor creates an organization at the first onboarding step and progresses
   without completing the whole flow. Verify actual identity-provider membership
   and persisted onboarding progress rather than trusting UI selection alone.
2. Log out, invalidate the old session, and log in as the same user. Restore the
   organization selection and progress from authorized server state.
3. Resume settings and later steps without a false authorization failure or
   duplicate organization. Repeated saves/retries must preserve the correct
   membership and completion state.
4. A different user or nonmember selecting that organization must remain denied.
   Stale or mismatched session claims must not bypass current membership/tenant
   checks. Qualify identity-provider/session propagation and reconciliation,
   including partial failures and the distinction between progress and completion.
5. Observe safe, correlated outcomes without printing passwords, cookie/token
   prefixes or invitation codes; clean up created accounts, sessions and tenant
   records through the owning services.

Current service/unit/component checks, deployed browser acceptance and real
identity-provider timing cover different boundaries. Keep the remaining gaps
explicit until the owning acceptance suite demonstrates this whole journey.
