# Production Readiness Remediation Plan

> **Historical record:** This plan predates retirement of the Python
> microservice launcher and image layout. It is not a current production plan.
> Do not deploy its named paths; use immutable Rust service artifacts from the
> `marty-ui` release stack.

## 1. Goal

Deliver a roadmap to close the production gaps called out in the latest review. For each finding we capture the current state, highlight the risk, and outline a pragmatic sequence of changes to land in a production-grade design.

## 2. Storage Modernization

### 2.1 Externalize state

**Current**: Services persist JSON in `DATA_DIR`; e.g. trust lists in `trust_store.json`, CSCA metadata under `data/csca`, passports and DTCs saved per request. This couples availability to a single host and breaks atomicity.

**Direction**:

1. Stand up PostgreSQL (metadata) and an object store (binary payloads) via infrastructure-as-code.
2. Introduce a shared `storage` package wrapping an async ORM (SQLAlchemy 2.0 async) and S3-compatible SDK (boto3/minio-py) exposed through repository interfaces.
3. Refactor per-service repositories to call the storage layer instead of touching the filesystem. Maintain migration scripts (Alembic).
4. Gate roll-out behind configuration flags so development can continue to use local SQLite/MinIO.

### 2.2 Secure key storage

**Current**: Private keys are written to disk under `data/keys` and `data/csca/private_keys`.

**Direction**:

1. Define an abstract `KeyVaultClient` (methods: `generate_key`, `sign`, `get_public_material`). Provide implementations for development (file-backed) and production (HSM/KMS) with configuration driven by `hsm_enabled`.
2. Update CSCA, Document Signer, and future PKD flows to request signing from the vault instead of loading key material into application memory.
3. Audit container images for secrets; remove key generation scripts that write to disk.

## 3. Stateless Service Pattern

**Current**: DTC and passport engines persist artifacts locally before responding.

**Direction**:

1. Rework gRPC handlers to return signed artifacts to the caller and publish persistence requests to storage via queue (see §4).
2. For audit or revocation requirements, create a dedicated `credential-ledger` service that consumes queue events and writes to the database.
3. Ensure all services become horizontally scalable containers with external dependencies passed via environment/service discovery.

## 4. Event Streaming & Messaging

**Current**: Lifecycle events are written to JSON files. No change notifications.

**Direction**:

1. Deploy Kafka (preferred) or RabbitMQ; manage topics such as `credential.issued`, `credential.revoked`, `trust.updated`, `certificate.rotated`.
2. Publish events from CSCA, Document Signer, DTC, and Trust Anchor services immediately after transactional commits.
3. Build consumers for audit logging, notifications, and cache invalidation. Keep payloads schema-factored (Avro/Protobuf) and versioned.

## 5. Transactional Consistency

**Current**: File-based updates (write new JSON then delete old) risk partial writes on crash.

**Direction**:

1. Wrap read-modify-write in database transactions with ACID guarantees; use `SERIALIZABLE` or `REPEATABLE READ` isolation where cross-table consistency is needed.
2. For distributed actions (e.g., signing then persisting), implement an application-level unit of work:  
   - start transaction  
   - request signing  
   - persist metadata + object storage pointer  
   - commit transaction  
   - publish event (or outbox).
3. Adopt the transactional outbox pattern for Kafka publishing.

## 6. Cryptography & Standards Compliance

**Current**: Signing is SHA-256 + Base64 with placeholder verification; BAC/PACE, SOD, and MRZ checks are stubbed.

**Direction**:

1. Use `cryptography`/`pyca` to implement RSA/ECDSA with ICAO-compliant hashing (SHA-256/SHA-384) and SOD ASN.1 structures. Validate MRZ with check digits.
2. Integrate open-source PACE/BAC implementations (e.g., `pypassport` or custom) to derive session keys.
3. Ensure inspection verifies SOD signatures against trust lists, enforces certificate chains, and handles revocation.
4. Add compliance tests against ICAO Doc 9303 vectors.

## 7. PKD Service Implementation

**Current**: `proto/` lacks PKD definitions; `main.py` cannot load PKD service; `src/pkd_service` is standalone demo code only.

**Direction**:

1. Define `pkd_service.proto` (APIs to pull CSCA master lists, subscribe to updates, and publish to relying parties).
2. Implement a production service that:  
   - Ingests master lists from ICAO FTP/HTTP (scheduled job).  
   - Validates signatures and stores artifacts in the trust database/object store.  
   - Exposes gRPC/REST for other services to fetch current trust anchors.
3. Integrate Trust Anchor service to sync from PKD instead of local disk.

## 8. Microservice Separation & Deployment

**Historical state**: Each Python gRPC microservice was intended to have a dedicated
entrypoint. Those launchers and their generic compatibility shim are retired;
current runtime services are Rust-owned and released from `marty-ui`.

**Direction**:

1. Keep deployment ownership in `marty-ui` and prevent references to the retired
   Python launcher paths from returning.
2. Produce one container image per service, share base layers via a monorepo build (e.g., Docker buildx or Bazel).
3. Update CI/CD to build, test, and deploy each service independently; add service-level health checks and Helm charts.

## 9. Validation & Error Handling

**Current**: Many RPCs accept raw bytes without schema validation and manually return status strings.

**Direction**:

1. Use Pydantic/`betterproto` for request validation on the server boundary; provide explicit error enums in proto definitions.
2. Add gRPC interceptors for exception mapping to canonical status codes and structured logging.
3. Document error contracts per service and add contract tests.

## 10. Security Hardening

**Current**: Inter-service calls use `grpc.insecure_channel`; no authentication/mTLS. No RBAC.

**Direction**:

1. Replace insecure channels with mTLS using SPIFFE IDs or service-issued certificates; manage trust bundles via the Trust Anchor service.
2. Front external traffic with an API gateway (e.g., Envoy) enforcing OAuth 2.0 client credentials or mTLS.
3. Introduce per-service RBAC and scoped tokens for inter-service calls.
4. Perform security scans (SAST/DAST, dependency scanning) in CI.

## 11. Performance & Scalability

**Current**: gRPC handlers are synchronous; heavy I/O runs on the main thread.

**Direction**:

1. Adopt `grpc.aio` servers/clients; refactor blocking I/O to async equivalents.
2. Introduce caching layers (Redis) for trust lists, master lists, and frequently accessed certificates.
3. Load-test critical flows and size autoscaling thresholds.

## 12. Milestone Breakdown

1. **Foundations (Weeks 1-3)**: Provision Postgres/Object store/Kafka, land storage abstractions, add secret vault client, enable TLS in development.  
2. **Persistence refactor (Weeks 4-6)**: Migrate Trust Anchor, CSCA, and DTC metadata to database + object store; implement transactional outbox.
3. **Security & Crypto (Weeks 7-10)**: Integrate HSM client, replace signing/verification logic, add mTLS, enforce MRZ checks.
4. **PKD & Trust (Weeks 10-12)**: Ship PKD service, connect Trust Anchor sync, implement cache invalidation via events.
5. **Operational hardening (Weeks 12-14)**: Split services into dedicated deployments, add async servers, introduce comprehensive monitoring and load testing.
6. **Compliance wrap-up (Weeks 14-16)**: Final validation, ICAO compliance tests, penetration testing, runbooks.

## 13. Immediate Next Steps

- Kick off infra tickets for managed Postgres, object storage, Kafka, and a secrets vault.
- Author design docs for the storage abstraction and key vault interface for review.
- Update proto definitions to add error enums and seed PKD service contracts.
- Schedule security architecture review to confirm mTLS + RBAC approach.
