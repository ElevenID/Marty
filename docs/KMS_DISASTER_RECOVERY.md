# KMS Disaster Recovery Guide

## Overview

This guide covers recovery procedures for KMS subsystem failures including encryption key loss, database corruption, provider outages, and credential compromise.

---

## Scenario 1: KMS Encryption Key Loss

**Impact**: All stored KMS credentials become undecryptable. No remote signing operations possible.

### Immediate Actions

1. **Do not restart services** — running instances may still have decrypted credentials in memory/cache (TTL up to 1 hour).
2. **Check backup key stores** — recover `KMS_ENCRYPTION_KEY` from secrets manager (e.g., AWS Secrets Manager, HashiCorp Vault).
3. **Check `KMS_ENCRYPTION_KEY_PREVIOUS`** — if the lost key was the primary and the previous key is available, it can still decrypt (MultiFernet chain).

### Recovery Steps

If the key cannot be recovered:

1. Generate a new Fernet key:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
2. Set `KMS_ENCRYPTION_KEY` to the new key.
3. **All existing encrypted credentials are now unrecoverable.** Each organization must re-configure their KMS:
   - Notify affected organizations.
   - Organizations re-submit credentials via `POST /{org_id}/kms/configure`.
4. Monitor `kms_errors_total{error_type="decryption"}` for orgs that haven't reconfigured.

### Prevention

- Store `KMS_ENCRYPTION_KEY` in a managed secrets service with automated backup.
- Maintain `KMS_ENCRYPTION_KEY_PREVIOUS` during all key rotations.
- Document key values in a secure, offline backup.

---

## Scenario 2: Database Loss / Corruption

**Impact**: Organization KMS configuration and encrypted credentials lost.

### Immediate Actions

1. Activate read-only mode or disable KMS endpoints.
2. Assess database backup availability.

### Recovery Steps

1. **Restore from backup** — use the most recent PostgreSQL backup that includes the `organization` table with `kms_provider`, `kms_config`, and `kms_credentials_encrypted` columns.
2. **Verify encryption key compatibility** — ensure the `KMS_ENCRYPTION_KEY` matches the key used when the backup was created. If a key rotation occurred after the backup, set the backup-era key as `KMS_ENCRYPTION_KEY_PREVIOUS`.
3. **Run key rotation** — after restore, rotate credentials to ensure they're encrypted with the current primary key:
   ```python
   from src.subscription.kms_config_service import KMSConfigService
   service = KMSConfigService(db_session)
   stats = await service.rotate_all_credentials()
   print(f"Rotated: {stats['rotated']}, Failed: {stats['failed']}")
   ```
4. **Validate** — call `GET /{org_id}/kms` for each configured org to confirm config is readable.

### If No Backup Available

1. Organizations must re-configure KMS via `POST /{org_id}/kms/configure`.
2. Track re-configuration progress via `kms_operations_total{operation="configure"}` metric.

---

## Scenario 3: Customer KMS Provider Outage

**Impact**: Signing operations fail for affected organizations. Circuit breaker opens after 5 consecutive failures.

### Detection

- `kms_circuit_breaker_state` gauge: `2` = open (outage detected).
- `kms_errors_total{error_type="timeout"}` or `{error_type="connection"}` spiking.
- `kms_signing_duration_seconds` P99 exceeding 30s (timeout boundary).

### Immediate Actions

1. **No action needed for circuit breaker** — it automatically prevents cascading failures and will probe recovery after 60 seconds.
2. **Notify affected organization** — the issue is with their KMS provider.
3. **Check provider status pages**:
   - AWS KMS: https://health.aws.amazon.com
   - Azure Key Vault: https://status.azure.com
   - GCP Cloud KMS: https://status.cloud.google.com

### Recovery

Circuit breaker recovery is automatic:
1. After 60 seconds, circuit enters HALF_OPEN state.
2. Next signing request is a probe — if it succeeds, circuit closes.
3. If probe fails, circuit re-opens for another 60 seconds.

To force cache refresh after provider recovery:
```
DELETE /{org_id}/kms  (then re-configure)
```
Or wait for TTL cache expiry (1 hour).

---

## Scenario 4: Credential Compromise

**Impact**: An organization's KMS provider credentials have been leaked.

### Immediate Actions

1. **Revoke credentials at the provider** — rotate access keys in AWS IAM, Azure AD, GCP, etc.
2. **Delete configuration** — `DELETE /{org_id}/kms` clears encrypted credentials and cached providers.
3. **Rotate encryption key** — in case the database was compromised:
   ```bash
   # Generate new key
   NEW_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
   # Set as primary, move current to previous
   export KMS_ENCRYPTION_KEY_PREVIOUS=$KMS_ENCRYPTION_KEY
   export KMS_ENCRYPTION_KEY=$NEW_KEY
   ```
4. **Run bulk rotation** to re-encrypt all other orgs' credentials with the new key.
5. **Audit logs** — review `kms_audit` logs for unauthorized access around the compromise window.

---

## Scenario 5: Application Rollback

**Impact**: Need to disable KMS subsystem entirely.

### Rollback Steps

1. **Comment out router inclusion** in `src/digital_identity/plugin/__init__.py`:
   ```python
   # app.include_router(kms_router)
   ```
2. **Roll back database migration** if schema changes were made.
3. **Fallback all tiers to service key vault** — organizations revert to the platform-managed signing service.
4. **Restart services** — new instances will not mount KMS endpoints.

### Post-Rollback

- Monitor for 404 errors from clients still calling KMS endpoints.
- Communicate the rollback to affected organizations.
- Retain encrypted credentials in the database for re-enablement.

---

## Recovery Time Objectives

| Scenario | RTO Target | Notes |
|----------|-----------|-------|
| Encryption key loss (recoverable) | 15 minutes | Restore from secrets manager |
| Encryption key loss (unrecoverable) | Days | Requires each org to re-configure |
| Database restore | 1–4 hours | Depends on backup infrastructure |
| Provider outage | Automatic | Circuit breaker handles recovery |
| Credential compromise | 30 minutes | Revoke + rotate + delete |
| Full rollback | 10 minutes | Comment out router, restart |

## Backup Requirements

| Asset | Backup Frequency | Retention | Storage |
|-------|-----------------|-----------|---------|
| `KMS_ENCRYPTION_KEY` | On creation/rotation | Indefinite | Secrets manager + offline |
| `KMS_ENCRYPTION_KEY_PREVIOUS` | On rotation | Until next rotation + 30 days | Secrets manager |
| PostgreSQL (organization table) | Daily + WAL streaming | 30 days | Encrypted offsite |
| Audit logs (`kms_audit`) | Continuous | 1 year minimum | Log aggregation service |
