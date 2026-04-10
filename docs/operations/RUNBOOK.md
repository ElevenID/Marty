# Day-2 Operations Runbook

> Operational procedures for Marty platform services.

## 1. Scaling Services

### Horizontal Scaling (Docker Compose)
```bash
docker compose up -d --scale flow-service=3 --scale applicant-service=2
```

### Kubernetes (when deployed)
```bash
kubectl scale deployment flow-service --replicas=3 -n marty
```

**Stateless services** (safe to scale freely):
- `auth`, `flow`, `applicant`, `credential-template`, `presentation-policy`, `verification`, `compliance-profile`, `revocation-profile`

**Stateful / singleton services** (scale with caution):
- `billing` — webhook receiver; ensure only one processes events
- `notification` — gRPC streams are per-instance; clients reconnect on scale-down
- `gateway` — rate limiting uses Redis; local fallback is per-instance

## 2. Database Backup & Restore

### PostgreSQL Backup
```bash
# Full backup
pg_dump -h localhost -U postgres -Fc marty_db > backup_$(date +%Y%m%d).dump

# Per-service database
for db in marty_document_signer marty_csca marty_pkd marty_passport_engine; do
  pg_dump -h localhost -U postgres -Fc "$db" > "${db}_$(date +%Y%m%d).dump"
done
```

### Restore
```bash
pg_restore -h localhost -U postgres -d marty_db --clean backup_20260401.dump
```

### Redis Cache
Redis is used for rate limiting and session caching only. No backup required — cache rebuilds on restart.

## 3. Rollback Procedures

### Service Rollback
```bash
# Docker Compose — revert to previous image
docker compose pull <service>@<previous-digest>
docker compose up -d <service>

# Or use git tag
git checkout v1.2.3
docker compose build <service>
docker compose up -d <service>
```

### Database Migration Rollback
```bash
# Alembic (Python services)
alembic downgrade -1

# Verify
alembic current
```

## 4. Certificate Rotation

### Document Signer Certificate (DSC)
1. Generate new DSC via KMS: `POST /v1/signing-keys` with new key name
2. Update credential templates to reference new `issuer_key_id`
3. Old credentials remain verifiable via old key in key store
4. Deactivate old key after grace period: `PATCH /v1/signing-keys/{id}` → `status: inactive`

### OpenBao Transit Key Rotation
```bash
bao write -f transit/keys/ecdsa-p256/rotate
# New key version is used for signing; old versions still verify
```

### TLS Certificates
```bash
# Check expiry
openssl x509 -enddate -noout -in /path/to/cert.pem

# Renew via ACME / Let's Encrypt
certbot renew --deploy-hook "docker compose restart gateway"
```

## 5. Credential Revocation & Cache Invalidation

### Revoke a Credential
```bash
# Via API
curl -X POST http://localhost:8000/v1/trust-registry/revoke \
  -H "Content-Type: application/json" \
  -d '{"credential_id": "...", "reason": "key_compromise"}'
```

### Force CRL Refresh
```bash
curl -X POST http://localhost:8200/api/v1/admin/crl/refresh \
  -H "X-Admin-API-Key: $TRUST_SVC_ADMIN_API_KEY" \
  -d '{"force_refresh": true}'
```

### Invalidate Trust Snapshot Cache
```bash
curl -X POST http://localhost:8200/api/v1/admin/snapshot/create \
  -H "X-Admin-API-Key: $TRUST_SVC_ADMIN_API_KEY"
```

## 6. Health Monitoring

### Service Health Checks
All services expose `GET /health` returning `{"status": "ok"}`.

```bash
# Check all services
for port in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009; do
  echo -n "Port $port: "
  curl -s "http://localhost:$port/health" | jq -r .status
done
```

### OpenBao Health
```bash
curl -s http://localhost:8200/v1/sys/health | jq .
```

### Keycloak Health
```bash
curl -s http://localhost:8180/health/ready
```

## 7. Log Analysis

### Structured Logging
All services use structured JSON logging. Key fields:
- `service_name` — originating service
- `request_id` — correlation ID (set by `RequestIdMiddleware`)
- `org_id` — tenant organization

### Common Queries
```bash
# Find errors for a specific request
docker compose logs --no-log-prefix | grep "request_id=abc123"

# Find all ERROR-level logs
docker compose logs --no-log-prefix | grep '"level":"ERROR"'

# gRPC failures
docker compose logs --no-log-prefix | grep "gRPC.*failed"
```

## 7. Production Deployment Configuration

The default `docker-compose.yml` is a **development-only** configuration. The following settings **must** be changed for production deployment.

### 7.1 Required Environment Variables

| Variable | Dev Default | Production Requirement |
|---|---|---|
| `SESSION_SECRET` | `dev-session-secret-change-in-production` | Generate with `openssl rand -base64 32` |
| `KEYCLOAK_ADMIN_PASSWORD` | `admin` | Strong password, rotated regularly |
| `KC_DB_PASSWORD` | `keycloak` | Strong password via secrets manager |
| `POSTGRES_PASSWORD` | `postgres` | Strong password via secrets manager |
| `STATUS_LIST_MASTER_KEY` | Hardcoded base64 key | Generate unique key, store in KMS (OpenBao/AWS KMS) |
| `DEMO_ADMIN_PASSWORD` | `Admin123!` | Remove demo users entirely |
| `COOKIE_SECURE` | `false` | `true` (requires HTTPS) |
| `COOKIE_SAMESITE` | `lax` | `strict` |

### 7.2 Keycloak

Replace `start-dev` with production mode:
```yaml
command:
  - start
  - --import-realm
  - --features=organization
  - --hostname=https://auth.yourdomain.com
  - --https-certificate-file=/etc/certs/tls.crt
  - --https-certificate-key-file=/etc/certs/tls.key
```

### 7.3 High Availability

Use the existing HA compose overlays:
```bash
# Redis Sentinel (recommended for HA)
docker compose -f docker-compose.yml -f docker-compose.sentinel.yml up -d

# Redis Cluster (for large-scale deployments)
docker compose -f docker-compose.yml -f docker-compose.cluster.yml up -d
```

PostgreSQL should use a managed service (RDS, Cloud SQL) or a Patroni cluster with streaming replication.

### 7.4 OpenBao / KMS

Dev mode uses an in-memory backend with a fixed root token. For production:
- Deploy OpenBao with Raft storage backend
- Use auto-unseal (AWS KMS, Azure Key Vault, or Transit seal)
- Rotate root token after initial setup
- Configure audit logging

### 7.5 TLS / Reverse Proxy

All services should sit behind a TLS-terminating reverse proxy (nginx, Caddy, or cloud load balancer). Internal service-to-service gRPC calls should use mTLS or run within a trusted network boundary.
