# Deployment Guide: KMS Configuration & Remote Signing

## Overview

Step-by-step guide to deploy the KMS configuration and remote signing features to production.

**Prerequisites:**
- PostgreSQL 15+ (for JSONB and async support)
- Python 3.10+
- Access to production database
- Secret management system (AWS Secrets Manager, HashiCorp Vault, or similar)
- TLS certificates for API gateway / load balancer
- Outbound HTTPS access to customer KMS endpoints (AWS, Azure, GCP, HashiCorp Vault)

**Security Documentation:**
- [KMS Security Architecture](KMS_SECURITY_ARCHITECTURE.md) — trust boundaries, threat model, encryption details
- [KMS Disaster Recovery](KMS_DISASTER_RECOVERY.md) — key loss, DB recovery, provider failure runbooks
- [KMS Operations Guide](KMS_OPERATIONS_GUIDE.md) — monitoring, alerts, troubleshooting

**Estimated Time:** 30-45 minutes

---

## Phase 1: Environment Preparation (10 minutes)

### Step 1.1: Generate Encryption Key

Generate a Fernet encryption key for securing KMS credentials:

```bash
# Generate key
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Example output:
# jF8zY3K5N7Q9R1S3T5U7V9W1X3Y5Z7A9B1C3D5E7F9G=
```

**⚠️ CRITICAL:** Store this key securely. Losing it means losing access to all KMS credentials.

### Step 1.2: Store in Secret Management System

**AWS Secrets Manager:**
```bash
aws secretsmanager create-secret \
  --name marty/production/kms-encryption-key \
  --description "Fernet encryption key for KMS credentials" \
  --secret-string "jF8zY3K5N7Q9R1S3T5U7V9W1X3Y5Z7A9B1C3D5E7F9G=" \
  --region us-west-2
```

**HashiCorp Vault:**
```bash
vault kv put secret/marty/production/kms-encryption-key \
  value="jF8zY3K5N7Q9R1S3T5U7V9W1X3Y5Z7A9B1C3D5E7F9G="
```

**Kubernetes Secret:**
```bash
kubectl create secret generic marty-kms-secret \
  --from-literal=encryption-key="jF8zY3K5N7Q9R1S3T5U7V9W1X3Y5Z7A9B1C3D5E7F9G=" \
  --namespace production
```

### Step 1.3: Set Environment Variable

**Docker Compose:**
```yaml
# docker-compose.yml
services:
  api:
    environment:
      KMS_ENCRYPTION_KEY: ${KMS_ENCRYPTION_KEY}
```

**Kubernetes:**
```yaml
# deployment.yaml
env:
  - name: KMS_ENCRYPTION_KEY
    valueFrom:
      secretKeyRef:
        name: marty-kms-secret
        key: encryption-key
```

**Systemd Service:**
```ini
# /etc/systemd/system/marty-api.service
[Service]
Environment="KMS_ENCRYPTION_KEY=jF8zY3K5N7Q9R1S3T5U7V9W1X3Y5Z7A9B1C3D5E7F9G="
```

### Step 1.4: Generate and Set JWT Secret

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set as `KMS_JWT_SECRET` (or `JWT_SECRET`) in the same manner as the encryption key.

### Step 1.5: Set Production Environment Variables

Required for TLS enforcement and security hardening:
```bash
ENVIRONMENT=production          # Enables TLS enforcement (rejects HTTP with 403)
KMS_ENCRYPTION_KEY=<key>        # Fernet encryption key
KMS_JWT_SECRET=<secret>         # JWT signing secret
AUTH_TRUST_PROXY_HEADERS=false  # Only set to true behind a verified API gateway
```

### Step 1.6: Configure TLS at API Gateway

Ensure your reverse proxy / load balancer:
1. Terminates TLS and forwards `X-Forwarded-Proto: https`
2. Strips client-supplied `X-User-ID` and `X-Org-IDs` headers (if `AUTH_TRUST_PROXY_HEADERS=true`)
3. Forwards `X-Forwarded-For` for accurate rate limiting

---

## Phase 2: Database Migration (10 minutes)

### Step 2.1: Backup Database

**⚠️ ALWAYS backup before migrations:**

```bash
# PostgreSQL backup
pg_dump -U marty -d marty_production -F c -f marty_backup_$(date +%Y%m%d_%H%M%S).dump

# Or full backup
pg_dumpall -U postgres > full_backup_$(date +%Y%m%d_%H%M%S).sql
```

### Step 2.2: Review Migration

Review the migration file:

```bash
cat migrations/20260406_add_kms_config_to_organizations.sql
```

Expected changes:
- Add `kms_provider` VARCHAR(50)
- Add `kms_config` JSONB
- Add `kms_credentials_encrypted` TEXT
- Create index on `kms_provider`

### Step 2.3: Apply Migration

**Production Database:**
```bash
# Connect to database
psql -U marty -d marty_production

-- Run migration
\i migrations/20260406_add_kms_config_to_organizations.sql

-- Verify columns exist
\d organizations

-- Expected output should include:
-- kms_provider              | character varying(50)
-- kms_config                | jsonb
-- kms_credentials_encrypted | text
```

**Alternative: Using psql directly:**
```bash
psql -U marty -d marty_production -f migrations/20260406_add_kms_config_to_organizations.sql
```

### Step 2.4: Verify Migration

```sql
-- Check column exists
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'organizations' 
AND column_name IN ('kms_provider', 'kms_config', 'kms_credentials_encrypted');

-- Check index
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'organizations' 
AND indexname = 'idx_organizations_kms_provider';

-- Verify no data corruption
SELECT COUNT(*) FROM organizations;
```

**✅ Checkpoint:** All 3 columns should exist, index created, row count unchanged.

---

## Phase 3: Code Deployment (10 minutes)

### Step 3.1: Deploy Code

**Git Deployment:**
```bash
# On production server
cd /opt/marty
git fetch origin
git checkout main
git pull origin main

# Verify new files exist
ls -l src/subscription/kms_router.py
ls -l src/subscription/kms_config_service.py
ls -l src/subscription/remote_signing_service.py
```

**Docker Deployment:**
```bash
# Build new image
docker build -t marty-api:v2.1.0 .

# Tag for registry
docker tag marty-api:v2.1.0 your-registry.io/marty-api:v2.1.0

# Push to registry
docker push your-registry.io/marty-api:v2.1.0

# Update deployment
kubectl set image deployment/marty-api api=your-registry.io/marty-api:v2.1.0
```

### Step 3.2: Install Dependencies

```bash
# Ensure cryptography package is installed
pip install cryptography>=41.0.0

# Or with uv
uv pip install cryptography>=41.0.0
```

### Step 3.3: Verify Module Imports

```bash
python3 -c "from src.subscription.kms_router import kms_router; print('✅ kms_router imported')"
python3 -c "from src.subscription.kms_config_service import KMSConfigService; print('✅ KMSConfigService imported')"
python3 -c "from src.subscription.remote_signing_service import RemoteSigningService; print('✅ RemoteSigningService imported')"
```

### Step 3.4: Mount Router in Application

**If using FastAPI directly:**

Your main application file should already include the router via the updated test fixtures. If you have a dedicated main.py, ensure it includes:

```python
from src.subscription.kms_router import kms_router

app = FastAPI()
app.include_router(kms_router)
```

**✅ Checkpoint:** All imports succeed, no syntax errors.

---

## Phase 4: Service Restart (5 minutes)

### Step 4.1: Graceful Restart

**Docker Compose:**
```bash
docker-compose restart api
```

**Kubernetes:**
```bash
kubectl rollout restart deployment/marty-api -n production
kubectl rollout status deployment/marty-api -n production
```

**Systemd:**
```bash
sudo systemctl restart marty-api
sudo systemctl status marty-api
```

### Step 4.2: Check Logs

```bash
# Docker
docker-compose logs -f api | grep -i kms

# Kubernetes
kubectl logs -f deployment/marty-api -n production | grep -i kms

# Systemd
sudo journalctl -u marty-api -f | grep -i kms
```

**Expected log messages:**
- Application startup successful
- No import errors
- Routes registered

**✅ Checkpoint:** Service running, no errors in logs.

---

## Phase 5: Validation (10 minutes)

### Step 5.1: Check API Health

```bash
curl -X GET http://your-api.com/health
```

Expected: `200 OK`

### Step 5.2: Test KMS Endpoints

Run the test script:

```bash
python scripts/test_kms_endpoints.py \
  --base-url https://api.example.com \
  --org-id "your-org-id" \
  --token "your-auth-token"
```

**Expected output:**
```
✅ Returns 404 when KMS not configured (expected)
✅ KMS configured successfully (or tier warning)
✅ Credentials properly redacted
```

### Step 5.3: Manual Endpoint Tests

**Check OpenAPI docs:**
```bash
curl https://api.example.com/docs
```

Navigate to `/v1/subscriptions/organizations/{org_id}/kms` endpoints.

**Test GET (unconfigured):**
```bash
curl -X GET "https://api.example.com/v1/subscriptions/organizations/{org_id}/kms" \
  -H "Authorization: Bearer {token}"
```

Expected: `404 Not Found` with message "KMS not configured"

**✅ Checkpoint:** All endpoints respond correctly, no 500 errors.

---

## Phase 6: Monitoring Setup

### Step 6.1: Prometheus Metrics

Metrics are already instrumented and available at:
```
GET /metrics/kms
```

Available metrics:
| Metric | Type | Description |
|--------|------|-------------|
| `kms_operations_total` | Counter | Operations by operation/provider/status |
| `kms_errors_total` | Counter | Errors by error_type/provider |
| `kms_auth_failures_total` | Counter | Auth failures by reason |
| `kms_signing_duration_seconds` | Histogram | Signing latency by provider |
| `kms_operation_duration_seconds` | Histogram | General operation latency |
| `kms_circuit_breaker_state` | Gauge | Circuit breaker state per org (0=closed, 1=half_open, 2=open) |
| `kms_cache_size` | Gauge | Provider cache utilization |

Add the Prometheus scrape config:
```yaml
scrape_configs:
  - job_name: 'marty-kms'
    metrics_path: '/metrics/kms'
    scrape_interval: 15s
    static_configs:
      - targets: ['marty-api:8000']
```

### Step 6.2: Alerts

Import the alert rules from `docs/KMS_OPERATIONS_GUIDE.md`. Key alerts:
- **KMSCircuitBreakerOpen** — provider failure cascade (critical)
- **KMSHighErrorRate** — error rate > 0.5/s for 5 min (warning)
- **KMSSigningLatencyHigh** — P95 > 5s for 5 min (warning)
- **KMSAuthFailureSpike** — possible credential compromise (critical)

### Step 6.3: Audit Logging

All security events are logged via the `kms_audit` logger. Events include:
- KMS configuration changes (provider, org, user)
- Configuration deletions
- Authentication / authorization failures
- Connectivity and signing test results

Configure your log aggregation to capture `kms_audit` logger output.

---

## Phase 7: Documentation & Communication

### Step 7.1: Update Internal Docs

- [ ] Add to internal wiki: "KMS Configuration Guide"
- [ ] Update runbooks: "How to troubleshoot KMS issues"
- [ ] Create dashboards: KMS metrics visualization

### Step 7.2: Communicate to Stakeholders

**Email template:**

```
Subject: New Feature Deployed - Remote Signing with Customer KMS

Team,

We've successfully deployed the KMS configuration feature that allows production tier customers (STARTER, PROFESSIONAL, ENTERPRISE) to use their own Key Management Service (KMS) or Hardware Security Module (HSM) for signing operations.

Key Details:
- Deployment Date: April 6, 2026
- Affected Tiers: STARTER, PROFESSIONAL, ENTERPRISE
- Documentation: https://docs.example.com/kms-configuration
- Support: For issues, contact support@example.com

This feature enables customers to maintain full control over their signing keys while using our credential issuance platform.

Next Steps:
- Monitor KMS metrics dashboard
- Review customer feedback in first 48 hours
- Schedule team training session

Thanks,
Platform Team
```

---

## Rollback Procedure (Emergency)

If issues occur, follow this rollback procedure:

### Step 1: Rollback Code

```bash
# Rollback to previous version
kubectl rollout undo deployment/marty-api -n production

# Or with Docker
docker-compose up -d api:v2.0.0
```

### Step 2: Rollback Database (if needed)

**⚠️ Only if data corruption occurred:**

```bash
psql -U marty -d marty_production -f migrations/20260406_add_kms_config_to_organizations_rollback.sql
```

**Note:** This will **delete** all KMS configurations. Customers will need to reconfigure.

### Step 3: Restore Environment

```bash
# Remove KMS_ENCRYPTION_KEY if causing issues
# Restart service
```

---

## Troubleshooting

### Issue: "KMS_ENCRYPTION_KEY not set"

**Symptom:** Application warns about missing encryption key.

**Fix:**
```bash
# Verify environment variable is set
echo $KMS_ENCRYPTION_KEY

# If not set, retrieve from secret manager and export
export KMS_ENCRYPTION_KEY=$(aws secretsmanager get-secret-value --secret-id marty/production/kms-encryption-key --query SecretString --output text)

# Restart service
```

### Issue: Migration fails with "column already exists"

**Symptom:** `ERROR: column "kms_provider" of relation "organizations" already exists`

**Fix:** Migration already applied, skip to next phase.

### Issue: Import errors after deployment

**Symptom:** `ModuleNotFoundError: No module named 'src.subscription.kms_router'`

**Fix:**
```bash
# Ensure files are deployed
ls -l src/subscription/kms_router.py

# Check Python path
python3 -c "import sys; print('\n'.join(sys.path))"

# Reinstall package if using editable install
pip install -e .
```

### Issue: "Cannot connect to KMS"

**Symptom:** Connectivity tests fail for customer KMS.

**Diagnosis:**
1. Check customer credentials are correct
2. Verify network connectivity (firewall, VPC)
3. Test IAM permissions (AWS) or service principal (Azure)
4. Check KMS service status

---

## Post-Deployment Checklist

- [ ] Database migration applied successfully
- [ ] KMS_ENCRYPTION_KEY environment variable set
- [ ] Code deployed to all instances
- [ ] Service restarted with no errors
- [ ] API health check passing
- [ ] KMS endpoints responding correctly
- [ ] Test script passes all tests
- [ ] Monitoring and alerts configured
- [ ] Documentation updated
- [ ] Team notified
- [ ] Rollback procedure tested (in staging)

---

## Success Criteria

✅ **Deployment is successful if:**
1. All database migrations applied without errors
2. API service running and healthy
3. KMS endpoints return proper responses (200/404)
4. No errors in application logs
5. Test script passes all tests
6. Metrics showing in monitoring dashboard

---

## Next Steps After Deployment

1. **Monitor for 48 hours:** Watch error rates, latency, customer feedback
2. **Customer Onboarding:** Create onboarding materials for customers wanting to configure KMS
3. **Support Training:** Train support team on KMS troubleshooting
4. **Performance Tuning:** Optimize KMS provider caching if needed
5. **Feature Enhancement:** Plan for Azure and GCP provider implementations

---

## Support Contacts

- **Deployment Issues:** devops@example.com
- **Database Issues:** dba@example.com
- **Application Issues:** backend-team@example.com
- **Customer Issues:** support@example.com

---

**Deployment Completed By:** ___________________  
**Date:** ___________________  
**Sign-off:** ___________________
