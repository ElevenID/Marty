# KMS Operations Guide

## Monitoring Setup

### Prometheus Metrics Endpoint

KMS metrics are exposed at:
```
GET /metrics/kms
```
Returns Prometheus text format (`text/plain; version=0.0.4`) from a dedicated `CollectorRegistry` (isolated from other subsystems).

### Available Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `kms_operations_total` | Counter | `operation`, `provider`, `status` | Total KMS operations (configure, delete, sign, test) |
| `kms_errors_total` | Counter | `error_type`, `provider` | Error count by type (timeout, connection, decryption, etc.) |
| `kms_auth_failures_total` | Counter | `reason` | Authentication/authorization failures |
| `kms_signing_duration_seconds` | Histogram | `provider` | Signing latency (buckets: 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30s) |
| `kms_operation_duration_seconds` | Histogram | `operation` | General operation latency (buckets: 0.01–5s) |
| `kms_active_providers` | Gauge | `provider` | Number of active provider instances |
| `kms_circuit_breaker_state` | Gauge | `org_id` | Circuit breaker state (0=closed, 1=half_open, 2=open) |
| `kms_cache_size` | Gauge | — | Current provider cache size |

### Prometheus Scrape Config

```yaml
scrape_configs:
  - job_name: 'marty-kms'
    metrics_path: '/metrics/kms'
    scrape_interval: 15s
    static_configs:
      - targets: ['marty-api:8000']
```

---

## Alert Configuration

### Recommended Alerts

```yaml
groups:
  - name: kms_alerts
    rules:
      # High error rate
      - alert: KMSHighErrorRate
        expr: rate(kms_errors_total[5m]) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "KMS error rate elevated"
          description: "{{ $labels.error_type }} errors for {{ $labels.provider }}: {{ $value }}/s"

      # Circuit breaker open
      - alert: KMSCircuitBreakerOpen
        expr: kms_circuit_breaker_state == 2
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "KMS circuit breaker open for org {{ $labels.org_id }}"
          description: "Remote signing disabled due to repeated provider failures"

      # Signing latency spike
      - alert: KMSSigningLatencyHigh
        expr: histogram_quantile(0.95, rate(kms_signing_duration_seconds_bucket[5m])) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "KMS signing P95 latency > 5s"

      # Auth failure spike
      - alert: KMSAuthFailureSpike
        expr: rate(kms_auth_failures_total[5m]) > 1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Elevated KMS auth failures ({{ $value }}/s)"
          description: "Possible credential compromise or misconfiguration"

      # Cache saturation
      - alert: KMSCacheFull
        expr: kms_cache_size > 90
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "KMS provider cache near capacity ({{ $value }}/100)"
```

---

## Grafana Dashboard

### Recommended Panels

**Row 1: Overview**
- Operations/sec: `rate(kms_operations_total[5m])` grouped by `operation`
- Error rate: `rate(kms_errors_total[5m])` grouped by `error_type`
- Auth failures: `rate(kms_auth_failures_total[5m])` grouped by `reason`

**Row 2: Latency**
- Signing P50/P95/P99: `histogram_quantile(0.5/0.95/0.99, rate(kms_signing_duration_seconds_bucket[5m]))`
- Operation latency heatmap: `kms_operation_duration_seconds_bucket`

**Row 3: Infrastructure**
- Circuit breaker states: `kms_circuit_breaker_state` table by `org_id`
- Cache utilization: `kms_cache_size` / 100
- Active providers: `kms_active_providers` by `provider`

---

## Troubleshooting

### Problem: Signing Failures

**Symptoms**: `kms_errors_total` increasing, `kms_operations_total{status="error"}` spiking.

**Diagnosis**:
1. Check error type: `kms_errors_total` labels reveal `timeout`, `connection`, or provider-specific errors.
2. Check circuit breaker: `kms_circuit_breaker_state` — if `2` (open), the provider has had 5+ consecutive failures.
3. Check provider health: verify the customer's KMS is reachable from the Marty network.
4. Check logs: `kms_audit` logger entries with `ERROR` level.

**Resolution**:
- If provider outage: wait for circuit breaker recovery (60s auto-probe).
- If credential issue: org must re-configure via `POST /{org_id}/kms/configure`.
- If timeout: check network latency; consider increasing `operation_timeout` (default 30s).

### Problem: Authentication Failures

**Symptoms**: `kms_auth_failures_total` increasing, 401/403 responses.

**Diagnosis**:
1. Check failure reason label: `expired_token`, `invalid_token`, `missing_credentials`, `org_access_denied`.
2. For `expired_token`: client JWT has expired — check clock sync.
3. For `invalid_token`: JWT secret mismatch — verify `KMS_JWT_SECRET` matches the issuer.
4. For `org_access_denied`: org_id in URL path not in JWT `org_ids` claim.

**Resolution**:
- Verify `KMS_JWT_SECRET` is consistent across all services.
- Check NTP sync if tokens expire prematurely.
- Verify the requesting user has the org_id in their JWT claims.

### Problem: High Latency

**Symptoms**: `kms_signing_duration_seconds` P95 > 2s.

**Diagnosis**:
1. Check which provider is slow: filter by `provider` label.
2. Check cache hit rate: if `kms_cache_size` is low, providers are being re-created frequently.
3. Check retry activity: retries add 1–10s per attempt (up to 3 attempts).

**Resolution**:
- Network latency to provider: check from the Marty host with `curl -o /dev/null -w "%{time_total}" <endpoint>`.
- Increase cache TTL if credential rotation is infrequent.
- Review provider-side rate limits.

### Problem: Rate Limit Errors (429)

**Symptoms**: Clients receiving 429 Too Many Requests.

**Diagnosis**:
- Check which endpoint is rate-limited (configure=10/hr, read=100/hr, signing test=50/hr).
- Check if requests are from legitimate automation or abuse.

**Resolution**:
- For legitimate high-volume: adjust rate limits in `kms_router.py` `@limiter.limit()` decorators.
- For abuse: block at the API gateway/WAF level.

---

## Routine Operations

### Key Rotation

Rotate the KMS encryption key without downtime:

1. Generate new key:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
2. Set environment variables:
   ```bash
   export KMS_ENCRYPTION_KEY_PREVIOUS=$KMS_ENCRYPTION_KEY
   export KMS_ENCRYPTION_KEY=<new-key>
   ```
3. Restart services (MultiFernet will decrypt with old key, encrypt with new key on next write).
4. Run bulk rotation:
   ```python
   stats = await kms_config_service.rotate_all_credentials()
   # stats: {rotated: N, skipped: N, failed: N, errors: [...]}
   ```
5. Verify: `stats['failed'] == 0`.
6. After 30 days, remove `KMS_ENCRYPTION_KEY_PREVIOUS`.

### Cache Management

- Cache TTL: 1 hour (automatic expiry).
- Manual clear (single org): `DELETE /{org_id}/kms` clears config and cache.
- Full cache clear: requires service restart.

### Health Checks

- `POST /{org_id}/kms/test-connectivity` — verifies provider reachability.
- `POST /{org_id}/kms/test-signing` — end-to-end signing test.
- `GET /metrics/kms` — verifies metrics subsystem is operational.

### Log Queries

All KMS audit events use the `kms_audit` logger. Example queries:

```
# All config changes
logger:kms_audit AND message:"KMS configured"

# All auth failures
logger:kms_audit AND (message:"JWT" OR message:"authorization")

# All deletions
logger:kms_audit AND message:"KMS config deleted"

# Signing results
logger:kms_audit AND message:"signing test"
```
