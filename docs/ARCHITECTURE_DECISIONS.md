# Architecture Decisions

> Decisions recorded during architecture remediation (2026-03-30 – 2026-04-01).

## Dependency Injection

**Decision**: No DI library needed. Services standardize on FastAPI's built-in `Depends()` pattern (already used in auth, trust_profile, verification). ~32 dependencies across 8 categories (gRPC clients, repos, DB engines, Redis, use cases, Cedar, external adapters, trackers) are all app-scoped singletons — too simple to justify a container.

## Proto Naming Convention

**Decision**: `marty-ui` uses `marty.ui.<name>.v1`, `marty-credentials` uses `marty.*.*`. New services use `marty.ui.<name>.v1`. Existing protos unchanged to avoid breaking gRPC clients.

## Python Dependency Pinning

**Decision**: Both repos use `pyproject.toml` with version ranges. Lock files (`uv.lock` / `poetry.lock`) are deployment-specific. CI uses pinned Docker images with deterministic installs. `marty-credentials` cannot lock due to private `marty-msf` dependency; `marty-ui` has no `pyproject.toml`.

## Revocation Status List Endpoints

**Decision**: Revocation status list endpoints are intentionally public per W3C Bitstring Status List v1.0 and IETF Token Status List (draft-14). Rate limiting applied at infrastructure layer (reverse proxy / CDN). ETag-based caching already in place.

## Error Response Envelope

**Decision**: All services standardize on MIP envelope format (`{"error", "error_description", "message_id"}`). Gateway `proxy_request()` normalizes downstream `{"detail": ...}` errors into this format. MIP-format responses from downstream pass through unchanged. `MartyError` global exception handler serializes through `mip_error_response()`.

## Service Decomposition Thresholds

**Decision**: Files under ~1,200 lines are acceptable as single-domain aggregates in one file. `flow/main.py` (~3,700 lines) is the actively developed OID4VP orchestration file — further decomposition deferred. `applicant/main.py` (~1,800 lines), `presentation_policy/main.py` (~1,600 lines) accepted as tightly coupled domains.

## Key Management (BYOK)

**Decision**: OpenBao (Apache 2.0 Vault fork) is the platform's KMS. Transit secrets engine signs without exposing private keys. Existing Vault enum values and config transfer directly since OpenBao shares the Vault API. Key naming: `cred:issuer:{org_id}:{key_id}` → `cred-issuer-{org_id}-{key_id}` (Transit keys can't contain colons).

## Gateway Shared Service Factory

**Decision**: `create_service_app()` standardizes middleware init for 12 of 13 services. Gateway kept bespoke due to unique proxy/middleware requirements. Consistent middleware order: CORS → RequestId → RequestLogging. `/health` + OTel/metrics wired automatically.

## SD-JWT External Signing

**Decision**: SD-JWT now supports external signing via the `CredentialSigner` trait, matching JWT-VC and mDoc. No fork of `sd-jwt-rs` was needed — disclosure generation (salt, SHA-256 hash, `_sd` array construction) is implemented directly in `sd_jwt.rs`, and `SDJWTVerifier` from `sd-jwt-rs` continues to handle verification. Three new public functions: `prepare_sd_jwt()` builds the header/payload/disclosures without signing, `assemble_sd_jwt()` attaches a raw signature, and `sign_sd_jwt_with_signer()` orchestrates the prepare→sign→assemble flow. The existing `sign_sd_jwt(&IssuerKey, ...)` path is unchanged for backward compatibility.

**Upstream strategy**: `sd-jwt-rs` 0.7 from crates.io is used only for `SDJWTVerifier` (verification) and `SDJWTIssuer` (legacy local-key path). Since disclosure generation is our own code, we are decoupled from upstream signing API changes. If a future `sd-jwt-rs` release adds native external signer support, we can migrate to it without API changes — `PreparedSdJwt` and `CredentialSigner` remain stable.

## Legacy Apps

**Decision**: `Marty/src/marty_plugin/legacy_apps/` has been removed. The only actively deployed service (`open-badges`) was migrated to `marty_plugin/open_badges/__main__.py` with a standalone bootstrap. The PYTHONPATH hack in docker-compose.yml was eliminated. The 9 other service entrypoints were thin wrappers around implementations in `marty_plugin/lib/` which remain in place.
