# Marty Unified Licensing Plan

## Goal

One license format, one issuer, all products — verifier app, backend containers, and CLI.

The `marty-verifier/crates/marty-license` JWT format becomes the universal license. Everything extends from it rather than building parallel systems.

---

## Current State (3 disconnected systems)

| System | Location | Built | Missing |
|---|---|---|---|
| **License validation** | `marty-verifier/crates/marty-license/` | Ed25519 JWT validation, hardware binding (BLAKE3), feature gating, grace periods, verification metering, secure storage | No issuer service — `"marty-license-issuer"` is referenced but unbuilt. Only a fake dev script. |
| **Subscription billing** | `marty-subscriptions/` (frontend) + `Marty/src/subscription/` (backend) | Plan tiers, Square integration, API key mgmt, usage tracking, webhook dispatch | Backend routes orphaned (not mounted). Frontend `/v1/billing/*` endpoints have no backend handler. Plan names mismatch. Broken model imports. |
| **Container registry** | `Makefile` + `scripts/` | Build/push to private GHCR | No per-org access tokens. No subscription-gated pull. No license check in container entrypoints. |

### Plan Tier Misalignment

| Frontend (`pricingContent.js`) | Backend (`square_service.py`) | Verifier License |
|---|---|---|
| `sandbox` | `FREE` | `deployment_mode: "development"` |
| `program` | `DEVS` / `STARTER` ??? | — |
| `institution` | `PROFESSIONAL` ??? | — |
| `system` (Sovereign) | `ENTERPRISE` | `deployment_mode: "production"` |

**Canonical tier names going forward:** `sandbox`, `program`, `institution`, `system`

---

## Phases

### Phase 1 — Unified License Schema ✅ COMPLETE

Extend `marty-verifier/crates/marty-license/src/claims.rs` with fields for all products:

| New Field | Type | Purpose |
|---|---|---|
| `plan_tier` | `Option<String>` | `"sandbox" \| "program" \| "institution" \| "system"` |
| `entitled_products` | `Vec<String>` | `["verifier", "document-signer", "passport-engine", ...]` |
| `max_instances` | `HashMap<String, u32>` | Per-product instance caps (`0` = unlimited) |
| `registry_access` | `Option<bool>` | Whether org can pull container images |
| `api_calls_limit` | `Option<u64>` | Monthly API cap (`0` = unlimited) |

Existing fields unchanged — backward compatible. Verifier continues reading what it already uses.

Add `PlanTier` enum and `Product` constants. Add `has_product()` and `max_instances_for()` methods.

### Phase 2 — License Issuer Service ✅ COMPLETE

Built `src/licensing/` module in the Marty backend:

- **`keys.py`** — Ed25519 key pair management. Loads from env vars (`LICENSE_SIGNING_PRIVATE_KEY`), PEM files, or generates ephemeral dev keys. Supports validation-only mode (public key only) for containers.
- **`models.py`** — `License` and `LicenseRevocation` SQLAlchemy 2.0 models with own `Base`. Platform-independent JSONB support.
- **`service.py`** — `LicenseIssuerService` mints Ed25519/EdDSA JWTs, manages revocation list, handles online validation (phone-home). Includes:
  - `DEFAULT_ENTITLEMENTS` per canonical tier (`sandbox`/`program`/`institution`/`system`)
  - `SQUARE_PLAN_TO_TIER` mapping for backward compatibility
  - Auto-supersede of existing licenses on reissue
- **`routes.py`** — Two FastAPI routers:
  - `admin_license_router` (`/v1/admin/licenses`) — issue, revoke, revoke-org, list, get
  - `public_license_router` (`/v1/licenses`) — validate (phone-home), public-key endpoint
- **35 tests** in `tests/licensing/` — keys, issuance, revocation, validation, JWT signature roundtrip, plan mapping, entitlement defaults

### Phase 3 — Python License Validator (for containers) ✅ COMPLETE

Ported essential validation logic from `marty-license` (Rust) to Python:

- **`validator.py`** — Offline-first Ed25519 JWT validation. Loads license from env (`MARTY_LICENSE`) or file paths (`/etc/marty/license.key`). Checks expiry with configurable grace period, product entitlement, feature gating, wildcard support. Optional phone-home to issuer for revocation checks.
- **`middleware.py`** — FastAPI integration layer:
  - Dependencies: `require_license`, `get_license_info`, `require_feature(name)`, `require_product(name)`
  - `LicenseMiddleware`: Starlette middleware for blanket enforcement with exempt paths (`/health`, `/ready`, `/metrics`, `/v1/licenses/*`)
- **`startup.py`** — Container lifecycle integration:
  - `startup_license_check(product_id, strict=True)`: synchronous pre-start validation, exits with `EX_CONFIG`/`EX_NOPERM` on failure
  - `create_licensed_lifespan(product_id)`: async FastAPI lifespan with periodic background re-validation
- **44 tests** — validator (25), middleware (19), covering expiry/grace, product entitlement, feature gating, env loading, phone-home, middleware enforcement

### Phase 4 — Wire Subscription → License Lifecycle ✅ COMPLETE

Connected subscription events to automatic license issuance/revocation:

- **`subscription_bridge.py`** — `SubscriptionLicenseBridge` translates subscription lifecycle events into license operations:
  - `on_subscription_created(org_id, org_name, square_plan)` → maps plan via `SQUARE_PLAN_TO_TIER`, mints JWT with `DEFAULT_ENTITLEMENTS`
  - `on_subscription_upgraded(org_id, org_name, new_square_plan)` → reissues with new tier (old auto-superseded)
  - `on_subscription_canceled(org_id)` → bulk-revokes all org licenses
  - `on_payment_success(org_id, org_name, square_plan)` → refreshes license for new billing cycle (if active)
  - `on_payment_failed(org_id)` → logs warning; license grace period handles the gap
- **`square_service.py`** wired — `SquareService` accepts optional `license_bridge` parameter:
  - `create_subscription()` → calls `on_subscription_created`
  - `cancel_subscription(immediately=True)` → calls `on_subscription_canceled`
  - `upgrade_subscription()` → calls `on_subscription_upgraded`
  - All 5 webhook handlers (`subscription.created/updated/canceled`, `invoice.payment_made/failed`) call appropriate bridge methods
  - All bridge calls wrapped in try/except — license failures never break subscription operations
- **Bug fix**: `src/subscription/routes.py` had `from __future__ import annotations` after runtime code (SyntaxError) — fixed
- **21 tests** — bridge unit tests (9) + SquareService integration tests (12), covering all lifecycle events, plan mapping, error resilience

### Phase 5 — Registry Gating ✅ COMPLETE

Per-org container registry pull credentials tied to license lifecycle:

- **`registry.py`** — `RegistryGatingService` manages per-org pull credentials:
  - `issue_credentials(org_id, license_jti, entitled_products)` → generates scoped token, stores SHA-256 hash, returns plaintext once
  - `revoke_org_credentials(org_id, reason)` → bulk status update to REVOKED
  - `get_org_credential(org_id)` → current active credential metadata
  - `validate_token(username, token)` → proxy validation endpoint (hash-compare, expiry check)
  - `PRODUCT_IMAGE_MAP` maps product IDs → GHCR image names (13 products)
  - Pluggable `RegistryTokenProvider` ABC — `StaticTokenProvider` (random bearer tokens, validated by proxy) ships as default; extensible to GitHub App installation tokens
- **`models.py`** — `RegistryCredential` model and `RegistryCredentialStatus` enum added:
  - Fields: `id`, `org_id`, `license_jti`, `registry_url`, `username`, `token_hash`, `allowed_images` (JSONB), `status`, `issued_at`, `expires_at`, `revoked_at`, `revocation_reason`
- **`subscription_bridge.py`** wired — optional `registry_service` parameter:
  - `on_subscription_created` → issues registry credentials if `registry_access=True` (program/institution/system tiers)
  - `on_subscription_upgraded` → reissues with new image scope
  - `on_subscription_canceled` → revokes all registry credentials
  - Sandbox tier (registry_access=False) skips credential issuance
  - All registry calls wrapped in try/except — failures don't break license operations
- **`routes.py`** — Three new routers:
  - `admin_registry_router` (`/v1/admin/registry`) — issue, revoke, get credential status
  - `registry_proxy_router` (`/v1/registry`) — `POST /validate-token` for pull proxy
  - `configure_license_dependencies()` extended with optional `registry_service_factory`
- **19 tests** — provider (3), service (10), image mapping (2), bridge+registry integration (4)

### Phase 6 — Dockerfile Integration ✅ COMPLETE

License enforcement baked into all container images:

- **`docker/license-entrypoint.sh`** — POSIX shell (`/bin/sh`) entrypoint wrapper for alpine compatibility:
  - Validates `MARTY_PRODUCT_ID` is set (exits `78` if missing)
  - Runs `startup_license_check()` from `src.licensing.startup` before `exec "$@"`
  - `MARTY_LICENSE_STRICT=false` bypasses enforcement for dev/test
  - License loaded from `MARTY_LICENSE` env or `/etc/marty/license.key` file
  - Public key from `LICENSE_SIGNING_PUBLIC_KEY` env or `/etc/marty/license.pub` file
- **5 Dockerfiles updated** with license layer:
  - `src/document_signer/Dockerfile` → `MARTY_PRODUCT_ID=document-signer`
  - `src/marty_plugin/csca_service/Dockerfile` → `MARTY_PRODUCT_ID=csca-service`
  - `src/marty_plugin/inspection_system/Dockerfile` → `MARTY_PRODUCT_ID=inspection-system`
  - `src/marty_plugin/passport_engine/Dockerfile` → `MARTY_PRODUCT_ID=passport-engine`
  - `docker/mmf-plugin.Dockerfile` → `MARTY_PRODUCT_ID=mmf-plugin`
  - Each gets: license-entrypoint.sh copy, `/etc/marty/` mount point (owned by marty user), `ENTRYPOINT` + `CMD` split
- **`document_processing`** — uses `MARTY_PRODUCT_ID` env var but defers to FastAPI `create_licensed_lifespan()` in `app/main.py` (doesn't copy full `src/` tree)
- **Grace period**: 7 days offline for containers (set in `DEFAULT_ENTITLEMENTS` per tier)
- **38 tests** — entrypoint script behavior (5), Dockerfile consistency checks across all services (31), startup integration (2)

---

---

## Gap Audit (post Phase 1–6)

| # | Area | Status | Severity |
|---|---|---|---|
| 1 | License route mounting | Not mounted in any FastAPI app | **CRITICAL** |
| 2 | SquarePlan enum cleanup | Old names intact, shim works | LOW |
| 3 | Usage metering enforcement | `api_calls_limit` never enforced, no `/v1/usage` | MEDIUM |
| 4 | Billing API backend | `src/subscription/routes.py` orphaned, frontend `/v1/billing/*` has no backend | **CRITICAL** |
| 5 | docker-compose license env | Zero license env vars configured | HIGH |
| 6 | CLI licensing | Zero CLI code exists | HIGH |
| 7 | Frontend tier alignment | Tier names correct ✓; blocked by gap 4 | — |
| 8 | Test coverage | No route tests, no E2E chain test | HIGH |

---

### Phase 7 — Route Mounting & Billing API ✅ COMPLETE

Wired all license, registry, and billing routers into the running FastAPI application.

**License route mounting:**
- Added `admin_license_router`, `public_license_router`, `admin_registry_router` imports to `DigitalIdentityPlugin`
- Registered all three in `register_routes()` alongside the existing 32 routers
- Added `_configure_licensing()` method to `plugin.startup()`:
  - Creates `LicenseKeyManager.from_env(allow_dev_keys=True)`
  - Wires `LicenseIssuerService`, `RegistryGatingService` factories
  - Calls `configure_license_dependencies()` — routes return real data instead of 503
  - All wiring wrapped in try/except — licensing is optional

**Billing API backend:**
- Created `src/subscription/billing_routes.py` with `billing_router` (`/v1/billing`):
  - `POST /v1/billing/subscribe` — maps canonical tier → `SquarePlan`, creates via `SquareService`
  - `POST /v1/billing/change-plan` — upgrade/downgrade
  - `POST /v1/billing/cancel` — immediate or at-period-end
  - `GET /v1/billing/subscription` — current status by org
  - `GET /v1/billing/invoices` — fetches from Square API
  - `POST /v1/billing/payment-methods` — add card via Square
  - `GET /v1/billing/payment-methods` — list cards
- `configure_billing_dependencies()` wired in `_configure_licensing()` with `SquareService` + bridge
- `billing_router` registered in plugin's router list
- Exported from `subscription/__init__.py`

**SquarePlan enum cleanup:**
- Replaced `FREE/DEVS/STARTER/PROFESSIONAL/ENTERPRISE` with `SANDBOX/PROGRAM/INSTITUTION/SYSTEM`
- `PLAN_LIMITS` updated: 4 tiers instead of 5 (merged FREE+DEVS into SANDBOX)
- `SQUARE_PLAN_TO_TIER` in `service.py` expanded: canonical names map to themselves + legacy names kept for backward compatibility
- Updated all references across `square_service.py`, `signing_service.py`, `billing_routes.py`, `examples/tier_based_signing_example.py`
- Updated all test files: `test_subscription_bridge.py`, `test_tier_based_signing.py`, `tests/integration/conftest.py`

**Tests (30):**
- `TestSquarePlanCanonical` (10): enum values, no legacy names, PLAN_LIMITS keys match, canonical mapping, _resolve_plan
- `TestBillingDependencyInjection` (3): factory wiring, 503 when unconfigured
- `TestBillingRoutes` (13): subscribe (success, invalid tier, org not found, Square error), change-plan (success, no sub), cancel (at period end, immediately), get subscription (success, 404), invoices, payment methods
- `TestPluginRouteRegistration` (4): router prefixes, expected routes, SQUARE_PLAN_TO_TIER shim

### Phase 8 — Route-Level License Tests ✅ COMPLETE

HTTP-level tests for all license, registry, and billing route handlers.

**`tests/licensing/test_routes.py` (38 tests):**
- `TestIssueLicense` (5): success with required fields, success with all optional fields, missing required → 422, issuer error → 400, internal error → 500
- `TestRevokeLicense` (3): success → 204, not found → 404, default reason
- `TestRevokeOrgLicenses` (2): success with count, zero revoked
- `TestListOrgLicenses` (3): empty list, populated list, `include_inactive` query param
- `TestGetLicense` (2): found → 200, not found → 404
- `TestValidateLicense` (5): valid, revoked, expired, not_found, superseded
- `TestGetPublicKey` (2): returns PEM with algorithm/key_type, crash → 500
- `TestIssueRegistryCredentials` (2): success → 201 with token, internal error → 500
- `TestRevokeRegistryCredentials` (3): success with count, zero exist, custom reason
- `TestGetRegistryCredentialStatus` (2): found, not found → null
- `TestValidateRegistryToken` (4): valid token, invalid → {valid: false}, missing fields → 422, internal error → 500
- `TestDependencyInjection503` (5): all five DI guards return 503 when factories are None

**Bug fix:** `issue_registry_credentials` route had bare `list[str]` param interpreted as body instead of query. Fixed with explicit `Query(...)` annotations.

**Phase 7 billing routes** already tested in `test_phase7_routes_billing.py` (30 tests).

### Phase 9 — Usage Metering & Enforcement ✅ COMPLETE

Enforce `api_calls_limit` from the license JWT and expose usage data.

**Counter store (Redis):**
- Add `UsageMeter` class using Redis `INCR` with monthly TTL keys (`usage:{org_id}:{YYYY-MM}`)
- Fallback to in-memory `defaultdict` counter when Redis unavailable (single-instance only)
- `increment(org_id)` → returns current count
- `get_usage(org_id, month?)` → returns count for given month
- `reset(org_id, month)` → admin reset

**Middleware enforcement:**
- Extend `LicenseMiddleware.dispatch()`:
  - After license validation, read `info.api_calls_limit`
  - If limit > 0, call `usage_meter.increment(org_id)`
  - If count > limit, return `429 Too Many Requests` with `Retry-After` header (end of month)
- Add `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` response headers

**`/v1/usage` endpoint:**
- `GET /v1/usage` — returns current org's usage for current month
- `GET /v1/admin/usage/{org_id}` — admin view of any org's usage
- Response: `{ org_id, month, api_calls_used, api_calls_limit, percent_used }`

**Tests:**
- `test_usage_meter.py` — increment, get, monthly rollover, TTL, in-memory fallback
- `test_usage_enforcement.py` — middleware blocks at limit, passes under limit, unlimited (limit=0) bypasses
- `test_usage_routes.py` — endpoint responses, admin vs org-scoped access

### Phase 10 — Docker-Compose & Dev Environment ✅ COMPLETE

Configure license environment for local development, testing, and production.

**`docker-compose.yml` (dev profile):**
- Add `MARTY_LICENSE_STRICT=false` to all licensed services (bypass for local dev)
- Add `MARTY_PRODUCT_ID` to each service matching Dockerfile defaults
- Add volume mount for `/etc/marty/` from `./docker/dev-license/`

**`docker-compose.yml` (production profile / overrides):**
- Document required env vars: `MARTY_LICENSE`, `LICENSE_SIGNING_PUBLIC_KEY`
- Add secrets/volume mounts for license key files
- Add `MARTY_LICENSE_VALIDATION_URL` pointing to the issuer service

**Dev license tooling:**
- `scripts/generate-dev-license.py` — generates a dev Ed25519 key pair + sandbox license JWT valid for 1 year
- Writes `docker/dev-license/license.key` + `docker/dev-license/license.pub`
- Pre-populated with all products entitled (dev convenience)

**Tests:**
- `test_docker_compose_config.py` — parse `docker-compose.yml`, verify all licensed services have `MARTY_PRODUCT_ID`
- `test_dev_license_generation.py` — run script, verify output files are valid Ed25519 JWT + PEM

### Phase 11 — CLI License Commands ✅ COMPLETE

Add `marty license` subcommands to `marty-cli`.

**Commands:**
- `marty license activate <token>` — store license JWT in config (`~/.marty/license.key`)
- `marty license status` — show current license info (tier, expiry, products, features)
- `marty license validate` — online validation against issuer (`/v1/licenses/validate/{jti}`)
- `marty license deactivate` — remove stored license

**Implementation:**
- `marty-cli/src/commands/license.js` — command handler
- Uses `apiAdapter` for HTTP calls to `/v1/licenses/*`
- License storage via `config.js` (existing config mechanism)
- Pretty-print license details with `output.js` formatters

**Tests:**
- `marty-cli/src/commands/__tests__/license.test.js` — unit tests for each subcommand
- Mock API responses, verify config file read/write, verify output formatting

### Phase 12 — End-to-End Integration Tests ✅ COMPLETE

Full-chain tests proving the licensing system works from subscription to container pull.

**`tests/licensing/test_e2e_chain.py`:**
- **Subscription → License → Registry flow:**
  1. Simulate Square webhook `subscription.created` for "program" tier
  2. Verify `SubscriptionLicenseBridge` issues a license JWT
  3. Verify registry credentials are provisioned with correct image scope
  4. Validate the JWT with `LicenseValidator`
  5. Verify `validate_token()` accepts the issued credential
- **Upgrade flow:**
  1. Start with "program" license
  2. Simulate upgrade to "institution"
  3. Verify old license superseded
  4. Verify new license has expanded entitlements
  5. Verify registry credentials reissued with new scope
- **Cancellation flow:**
  1. Start with active license
  2. Simulate `subscription.canceled` webhook
  3. Verify license revoked
  4. Verify registry credentials revoked
  5. Verify validator rejects the revoked license
- **Payment failure flow:**
  1. Active license with grace period
  2. Simulate `invoice.payment_failed`
  3. Verify license still valid during grace period
  4. Verify license rejected after grace expiry

**`tests/licensing/test_container_startup.py`:**
- Test `startup_license_check()` with valid/expired/wrong-product licenses
- Test `create_licensed_lifespan()` background re-validation
- Test `MARTY_LICENSE_STRICT=false` bypass

---

## Reuse vs New Work

| Component | Reuse | New |
|---|---|---|
| JWT format + Ed25519 | `marty-license` claims schema | Extend with `plan_tier`, `entitled_products`, `max_instances` |
| Validation logic | `marty-license` Rust crate (verifier keeps using it) | Python port for containers |
| Hardware binding | `marty-license` fingerprint module (verifier only) | Not needed for containers |
| Plan tiers + pricing | `pricingContent.js` tier names become canonical | Kill `SquarePlan` enum |
| Billing API | `paymentApi.js` frontend client | Backend endpoints need mounting |
| Square integration | `square_service.py` webhook handling | Wire to license lifecycle |
| Usage metering | `UsageDashboard.jsx` + `record_api_usage()` | Enforce in middleware; build `/v1/usage` |
| Container registry | GHCR private repos + `Makefile` | Per-org token management |
