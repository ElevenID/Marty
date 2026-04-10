# KMS Security Architecture

## Overview

The Key Management Service (KMS) subsystem allows enterprise-tier organizations to bring their own HSM or cloud KMS for document signing operations. This document describes the trust model, threat mitigations, and security boundaries.

## Trust Boundaries

```
┌─────────────────────────────────────────────────────────┐
│ Marty API Gateway (TLS Termination)                     │
│   ├─ X-Forwarded-Proto → EnforceTLSMiddleware           │
│   └─ JWT / X-User-ID headers → get_authenticated_user() │
├─────────────────────────────────────────────────────────┤
│ KMS Router (rate-limited, input-validated)               │
│   ├─ Org authorization (JWT org_ids ∩ path org_id)       │
│   ├─ SSRF validator (DNS resolution of endpoint URLs)    │
│   └─ Credential encryption (Fernet → DB)                 │
├─────────────────────────────────────────────────────────┤
│ RemoteSigningService (circuit breaker, retry, cache)     │
│   └─ Per-org signing via customer KMS providers          │
├──────────────┬──────────────────────────────────────────┤
│ PostgreSQL   │ Customer KMS (external)                   │
│ (encrypted   │   ├─ AWS KMS                              │
│  credentials)│   ├─ Azure Key Vault                      │
│              │   ├─ GCP Cloud KMS                        │
│              │   ├─ HashiCorp Vault                      │
│              │   ├─ PKCS#11 HSM                          │
│              │   └─ Software HSM                         │
└──────────────┴──────────────────────────────────────────┘
```

### Boundary 1: External Client → API Gateway

- TLS termination at the gateway/load balancer.
- `EnforceTLSMiddleware` rejects plain HTTP in production (403).
- HSTS header: `max-age=31536000; includeSubDomains`.

### Boundary 2: API Gateway → KMS Router

- **JWT authentication** — HMAC (`HS256` default) via `KMS_JWT_SECRET`. Validates `sub` claim, extracts `org_ids`.
- **Trusted proxy headers** — optional fallback (`AUTH_TRUST_PROXY_HEADERS=true`); reads `X-User-ID` / `X-Org-IDs`. Only enable behind a verified gateway that strips client-supplied headers.
- **Organization authorization** — path `org_id` must appear in the authenticated user's `org_ids` list. Returns 403 otherwise.

### Boundary 3: KMS Router → Database

- Credentials encrypted with `cryptography.fernet.MultiFernet` before storage.
- Encryption keys from `KMS_ENCRYPTION_KEY` (primary) and `KMS_ENCRYPTION_KEY_PREVIOUS` (rotation).
- Credentials are **never** returned in API responses (`get_kms_config_safe()`).

### Boundary 4: RemoteSigningService → Customer KMS

- Network calls to customer-controlled infrastructure.
- 30-second operation timeout.
- Circuit breaker (5-failure threshold, 60s recovery) prevents cascading failures.
- Retry with exponential backoff (3 attempts, 1–10s).
- TTL cache (1 hour, max 100 providers) reduces credential-fetch frequency.

## Threat Model

| Threat | Mitigation | Residual Risk |
|--------|-----------|---------------|
| **Credential theft from DB** | Fernet-encrypted at rest; key in env var, not DB | Compromise of `KMS_ENCRYPTION_KEY` exposes all stored credentials |
| **SSRF via endpoint_url** | DNS resolution check blocks private/loopback/link-local IPs; HTTPS required in production | TOCTOU: DNS may resolve differently at check vs. use time |
| **JWT forgery** | HMAC signature verification; secret rotation possible | Shared secret (HS256) — consider RS256 for distributed deployments |
| **Org-level privilege escalation** | Path org_id validated against JWT org_ids claim | `org_ids=None` grants unrestricted access (admin use only) |
| **DoS / abuse** | slowapi rate limiting per endpoint (10–100/hour); circuit breaker per org | Shared-IP rate limiting behind proxy; configure `X-Forwarded-For` trust |
| **Proxy header spoofing** | `AUTH_TRUST_PROXY_HEADERS` off by default | If enabled without proper header stripping, any client can impersonate |
| **Stale cached credentials** | TTL 1 hour, explicit invalidation on config delete | Up to 1 hour of stale state after external credential rotation |
| **Provider failure cascade** | Circuit breaker opens after 5 consecutive failures | Half-open probes may fail during extended outages |

## Encryption Details

### Credential Encryption (Fernet / MultiFernet)

- **Algorithm**: AES-128-CBC with HMAC-SHA256 (Fernet spec).
- **Key format**: URL-safe base64-encoded 256-bit value.
- **At rest**: `organization.kms_credentials_encrypted` column stores Fernet token (base64).
- **Key rotation**: `MultiFernet` chain — encrypts with primary key, decrypts with any key. `rotate_credentials()` re-encrypts per-org; `rotate_all_credentials()` iterates all orgs.

### Signing Algorithms

- Default: `ES256` (ECDSA P-256 with SHA-256).
- Configurable per organization via `algorithm` field.

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `POST /{org_id}/kms/configure` | 10/hour |
| `GET /{org_id}/kms` | 100/hour |
| `DELETE /{org_id}/kms` | 10/hour |
| `POST /{org_id}/kms/test-connectivity` | 20/hour |
| `POST /{org_id}/kms/test-signing` | 50/hour |

## Input Validation

- **Provider**: strict `Literal` type — only `aws_kms`, `azure_key_vault`, `gcp_kms`, `hashicorp_vault`, `pkcs11_hsm`, `software_hsm`.
- **Credentials & config**: max 10 KB each; `extra="forbid"` rejects unknown fields.
- **Key IDs**: max 1 KB.
- **AWS KMS ARN**: regex validated.
- **Azure Key Vault URL**: regex validated.
- **Region**: alphanumeric + hyphens, max 50 chars.
- **Endpoint URLs**: SSRF-checked with DNS resolution.

## Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `KMS_ENCRYPTION_KEY` | Production | (generates temp key with warning) | Primary Fernet encryption key |
| `KMS_ENCRYPTION_KEY_PREVIOUS` | No | None | Previous key for rotation |
| `KMS_JWT_SECRET` / `JWT_SECRET` | Production | None (503 if missing) | JWT HMAC secret |
| `KMS_JWT_ALGORITHM` | No | `HS256` | JWT algorithm |
| `AUTH_TRUST_PROXY_HEADERS` | No | `false` | Enable proxy header auth |
| `ENVIRONMENT` | No | `development` | TLS enforcement mode |
| `DATABASE_URL` | No | `postgresql+asyncpg://...localhost:5432/marty` | Database connection |

## Audit Logging

All security-relevant events are logged via the `kms_audit` logger:

- KMS configuration changes (provider, org, user)
- KMS configuration deletions
- Authentication failures (expired token, invalid signature, missing credentials)
- Organization authorization failures (org_id mismatch)
- Connectivity test results
- Signing test results
- SSRF validation failures
- Rate limit violations
