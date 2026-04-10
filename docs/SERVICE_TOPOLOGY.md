# Cross-Repo Service Topology & Deployment Guide

> Generated 2026-04-01. Covers all repos in the Marty workspace.

---

## Repository Overview

| Repo | Role |
|------|------|
| `Marty` | Backend Python monolith (gRPC engines, trust services, notifications) |
| `marty-ui` | FastAPI microservices mesh (identity, auth, gateway, issuance) |
| `marty-core` | Rust verification library + Python bindings (marty-verification, marty-crypto) |
| `marty-credentials` | Rust credential library (SD-JWT, mDoc, status list) + marty-rs Python FFI |
| `marty-verifier` | Tauri desktop verifier application |
| `marty-authenticator` | Flutter mobile wallet (iOS/Android) |
| `marty-microservices-framework` (MMF) | Python service framework (DI, auth, middleware, base service patterns) |
| `marty-integration-tests` | End-to-end pytest test suite |
| `marty-protocol` | Protocol specification + Cedar policy definitions |
| `longfellow-zk` | Zero-knowledge proof library (C++/Go) |

---

## marty-ui Microservices

All services live under `marty-ui/services/`. They communicate via gRPC internally and expose REST externally.

### Port Map

| Service | Docker hostname | HTTP port | gRPC port | Env var overrides |
|---------|----------------|-----------|-----------|-------------------|
| **gateway** | `gateway` | 8000 | — | `GATEWAY_PORT` |
| **auth** | `auth` | 8001 | 9001 | `AUTH_SERVICE_PORT`, `AUTH_GRPC_PORT` |
| **organization** | `organization` | 8002 | 9002 | `ORGANIZATION_SERVICE_PORT`, `ORG_GRPC_PORT` |
| **credential-template** | `credential-template` | 8003 | 9003 | `CREDENTIAL_TEMPLATE_SERVICE_PORT`, `CT_GRPC_PORT` |
| **trust-profile** | `trust-profile` | 8004 | — | `TRUST_PROFILE_SERVICE_PORT` |
| **issuance** | `issuance` | 8005 | 9005 | `ISSUANCE_SERVICE_PORT`, `ISSUANCE_GRPC_TARGET` |
| **applicant** | `applicant` | 8006 | — | `APPLICANT_SERVICE_PORT` |
| **notification** | `notification` | 8007 | 9007 | `NOTIFICATION_SERVICE_PORT`, `NOTIF_GRPC_PORT` |
| **compliance-profile** | `compliance-profile` | 8008 | — | `COMPLIANCE_PROFILE_SERVICE_PORT` |
| **presentation-policy** | `presentation-policy` | 8009 | 9009 | `PRESENTATION_POLICY_SERVICE_PORT`, `PP_GRPC_PORT` |
| **deployment-profile** | `deployment-profile` | 8010 | — | `DEPLOYMENT_PROFILE_SERVICE_PORT` |
| **flow** | `flow` | 8011 | 9011 | `FLOW_SERVICE_PORT`, `FLOW_GRPC_PORT` |
| **verification** | `verification` | 8012 | 9017 | `VERIFICATION_SERVICE_PORT`, `VERIF_GRPC_PORT` |
| **revocation-profile** | `revocation-profile` | 8013 | 9013 | `REVOCATION_PROFILE_SERVICE_PORT`, `RP_GRPC_PORT` |
| **device-registration** | `device-registration` | 8014 | — | `DEVICE_REGISTRATION_SERVICE_PORT` |
| **event-stream** | `event-stream` | 8015 | 9015 | `EVENT_STREAM_SERVICE_PORT`, `EVENT_STREAM_GRPC_PORT` |
| **billing** | `billing` | 8016 | — | `BILLING_SERVICE_PORT` |

### Infrastructure services

| Service | Docker hostname | Port | Image |
|---------|----------------|------|-------|
| PostgreSQL | `postgres` | 5432 | `postgres:15-alpine` |
| Redis | `redis` | 6379 | `redis:7-alpine` |
| Keycloak | `keycloak` | 8180 | `quay.io/keycloak/keycloak:25.0` |
| OpenBao | `openbao` | 8200 | `quay.io/openbao/openbao:2` |
| Envoy proxy | `envoy` | 9901 | Configured via `envoy_proto_descriptor` |
| Mailpit (dev SMTP) | `mailpit` | 1025/8025 | `axllent/mailpit:v1.21` |

### Inter-service gRPC call graph (marty-ui)

```
gateway ──► auth         (9001)  AuthService
        ──► organization (9002)  OrganizationService
        ──► credential-template (9003)  CredentialTemplateService
        ──► flow         (9011)  FlowService
        ──► event-stream (9015)  EventStreamService
        ──► presentation-policy (9009)  PresentationPolicyService

flow    ──► credential-template (9003)
        ──► presentation-policy (9009)
        ──► issuance     (9005, HTTP 8005/v1/issuance/initiate)
        ──► organization (9002)

verification ──► presentation-policy (9009)
             ──► issuance (9005)

auth    ──► organization (9002)
        ──► flow         (9011)

notification ──► organization (9002)
```

---

## Marty Backend (Python gRPC engines)

Lives in `Marty/src/marty_plugin/lib/`. Exposes gRPC services consumed by the `document-signer` and `oid4vc-api` Docker containers.

| Service | Default port | gRPC service name |
|---------|-------------|-------------------|
| document-signer | 8082 | `DocumentSignerService` |
| passport-engine | 8084 | `PassportEngineService` |
| inspection-system | 8083 | `InspectionSystemService` |
| PKD service | internal | `PKDService` |
| DTC engine | internal | `DTCEngineService` |
| consistency-engine | 50051 (gRPC) / 8080 (HTTP) | `ConsistencyEngineService` |
| trust-svc (REST) | 8200 (configurable) | REST API, no gRPC |
| OID4VC API | 8090 | `oid4vc-api` Docker service |

### Marty Docker services (`docker-compose.yml`)

| Service | Exposes | Description |
|---------|---------|-------------|
| `document-signer` | 8082 | SOD/DTC signing via DSC |
| `open-badges` | configurable | Open Badges issuance |
| `oid4vc-api` | 8090 | OID4VCI/OID4VP issuer |
| `wallet` | — | marty-authenticator (Flutter app container) |
| `wallet-simulator` | — | Nginx-based simulator |
| `keycloak` | 8180 | Identity provider |
| `postgres` | 5432 | Primary database |
| `redis` | 6379 | Session + cache store |
| `seed` | — | One-shot database seeder |
| `openbao` | 8200 | KMS Transit engine |

---

## marty-credentials (Rust)

Provides Python FFI via `marty-rs` bindings:

| Crate | Function |
|-------|----------|
| `marty-mdoc` | ISO 18013-5 mDoc issuance + verification |
| `marty-sd-jwt` | SD-JWT issuance (`prepare_sd_jwt_credential`, `assemble_sd_jwt_credential`) |
| `marty-status-list` | RFC 9278 status list management |
| `marty-oid4vci` | OID4VCI server-side protocol |
| `marty-rs` (Python FFI) | `_marty_rs` bindings: `issue_emrtd_passport`, `oid4vci_prepare_credential`, `oid4vci_assemble_credential`, `prepare_mdoc_for_hsm`, `complete_mdoc_with_signature` |

---

## marty-core (Rust)

| Crate | Function |
|-------|----------|
| `marty-verification` | X.509 chain validation, CRL parsing, KeyUsage checks |
| `marty-crypto` | CRL builder, ECDSA/RSA primitives |
| `marty-iso18013` | ISO 18013-5 session transcript, PACE |
| `marty-biometrics` | Liveness detection |
| `marty-bindings` | Python extension module (`_marty_verification`) |

---

## Key Management Architecture

```
Environment   Provider                  Attestation
──────────    ──────────────────────    ───────────
production    AWS KMS (CloudHSM)        ✓ (ENFORCE_HSM_ATTESTATION=true)
staging       OpenBao Transit           ✗ (trusted server boundary)
development   OpenBao / SoftwareHSM    ✗ (ENFORCE_HSM_ATTESTATION=false)
testing       FileBasedProvider         ✗
```

Roles requiring attestation (`require_attestation: true` in `config/security/crypto_boundaries.yaml`):
- **CSCA** — Country Signing CA keys
- **DSC** — Document Signer Certificate keys

DSC provisioning flow:
1. `ensure_document_signer_certificate()` checks the cert repository  
2. If no cert: calls `_build_dsc_via_kms(kms_provider, ...)` when KMS is configured  
3. `_build_dsc_via_kms` retrieves public key from KMS, builds TBSCertificate, signs via KMS (private key never leaves KMS), assembles final DER  
4. Falls back to legacy `_build_dsc_with_rust()` (local key from KeyVault) when `kms_provider=None`

Configure:
```bash
# OpenBao (staging/dev)
export BAO_ADDR=http://openbao:8200
export BAO_TOKEN=<token>

# AWS KMS (production)
export AWS_DEFAULT_REGION=us-east-1
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
# Pass to create_kms_manager(KMSProvider.AWS_KMS, region_name="us-east-1", key_prefix="marty/")

# PKCS#11 (on-premise HSM)
# Pass to create_kms_manager(KMSProvider.PKCS11_HSM, library_path="/usr/lib/softhsm/libsofthsm2.so", token_label="marty", user_pin="...")
```

---

## Auth Service Rate Limiting

Auth endpoints are protected by a per-IP sliding-window rate limiter (30 req/min default):

```bash
AUTH_RATE_LIMIT_RPM=30   # requests per minute per IP (default)
```

Covered endpoints: `/v1/auth/login`, `/v1/auth/register`, `/v1/auth/callback`, `/v1/auth/credential-login/*`

---

## Presentation Policy Sync Endpoint

The `/v1/identity/sync` endpoint requires a signed license JWT:

```bash
LICENSE_JWT_SECRET=<shared-secret>     # required; endpoint returns 503 if unset
LICENSE_JWT_ALGORITHM=HS256            # default
```

The JWT must contain an `org_id` (or `organization_id`) claim. Returned policies are filtered to that org.

---

## Database Per Service

Each marty-ui service has its own schema in the shared PostgreSQL instance:

| Service | Schema / DB name default |
|---------|--------------------------|
| auth | `marty_dev` |
| organization | `marty_dev` |
| credential-template | `marty_credentials` |
| trust-profile | `marty_dev` |
| presentation-policy | `marty_dev` |
| flow | `marty_dev` |
| billing | `marty_credentials` |
| revocation-profile | `marty_dev` |
| device-registration | `marty_dev` |
| compliance-profile | `marty_dev` |
| deployment-profile | `marty_dev` |

All use `DatabaseManager(DatabaseConfig.from_env("<service>"))` with `asyncpg` driver.

Run migrations:
```bash
cd marty-ui/services
python run_all_migrations.py   # applies all service schemas
```

---

## marty-integration-tests

Runs against the full Docker stack. Requires:
```bash
make start    # starts docker-compose.yml in marty-ui + Marty
make test     # pytest tests/integration/
```

Key test suites:
- `test_wallet_oid4vci_gateway.py` — OID4VCI issuance (SD-JWT + mDoc)
- `test_complete_lifecycle.py` — full MDL lifecycle including revocation
- `test_marty_wallet.py` — wallet SD-JWT format dispatch

---

## Quick Start

```bash
# 1. Start infrastructure
cd marty-ui && docker compose up postgres redis keycloak openbao -d

# 2. Apply migrations
docker compose run --rm db-migrate

# 3. Start all services
docker compose up --build

# 4. (Optional) Start Marty backend
cd Marty && docker compose up --build

# 5. Verify
curl http://localhost:8000/health      # gateway
curl http://localhost:8001/health      # auth
```

Environment template: `marty-ui/.env.example`
