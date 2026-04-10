# Pre-Deployment Testing Gaps - Quick Reference

**Status:** 🔴 **CRITICAL GAPS IDENTIFIED**  
**Date:** April 6, 2026

## 🚨 BLOCKERS - Must Fix Before Any Deployment

| # | Issue | Impact | Effort |
|---|-------|--------|--------|
| 1 | **No Authentication/Authorization** | Anyone can configure/delete KMS | 1-2 days |
| 2 | **Database Session Not Implemented** | All endpoints return 500 error | 4 hours |
| 3 | **No TLS Enforcement** | Credentials sent in plaintext | 4 hours |

## 🔴 High Priority - Required for Production

| # | Issue | Impact | Effort |
|---|-------|--------|--------|
| 4 | No rate limiting | DoS attacks, cost overruns | 1 day |
| 5 | No audit logging | Compliance violations, no forensics | 1 day |
| 6 | No encryption key rotation | Cannot recover from key compromise | 2 days |
| 7 | Insufficient input validation | Injection attacks, SSRF | 1 day |
| 8 | No timeouts/retry logic | Hung requests, cascading failures | 1 day |
| 9 | Provider cache issues | Stale configs, memory leaks | 1 day |
| 10 | Only mock tests | Real KMS integration untested | 2 days |
| 11 | No load testing | Unknown scalability limits | 1 day |

## Test Coverage Gaps

### Current Test Status
- ✅ Unit tests: 25 test cases (mocked)
- ❌ Integration tests: **0** (all mocks, no real KMS)
- ❌ Security tests: **0**
- ❌ Load tests: **0**
- ❌ End-to-end tests: **0**

### Critical Missing Tests

#### 1. Security Tests (MUST HAVE)
```python
# Authentication
- [ ] Unauthenticated requests rejected (401)
- [ ] Wrong organization access denied (403)
- [ ] Non-admin users cannot configure KMS (403)
- [ ] JWT/session token validation
- [ ] Expired token handling

# Authorization
- [ ] User can only access their organizations
- [ ] Organization membership validation
- [ ] Role-based access (admin vs. member)

# Input Validation
- [ ] SQL injection attempts blocked
- [ ] SSRF via endpoint_url blocked (private IPs)
- [ ] Oversized payloads rejected (>10KB)
- [ ] Invalid key ID formats rejected
- [ ] XSS in metadata fields sanitized

# Credential Security
- [ ] Credentials never appear in logs
- [ ] Credentials never in error messages
- [ ] Credentials never in API responses
- [ ] Encryption/decryption works correctly
```

#### 2. Integration Tests (MUST HAVE)
```python
# Real KMS Providers
- [ ] AWS KMS with localstack
- [ ] HashiCorp Vault with dev server
- [ ] PKCS#11 HSM (if available)
- [ ] Error handling matches real responses

# Database
- [ ] Forward migration succeeds
- [ ] Rollback migration succeeds
- [ ] Data integrity after migration
- [ ] Concurrent transactions handled

# End-to-End Flows
- [ ] Configure KMS → Issue credential → Verify signature
- [ ] Tier upgrade: FREE → STARTER (prompt for KMS)
- [ ] Tier downgrade: STARTER → FREE (disable remote signing)
- [ ] Delete KMS → signing operations fail gracefully
```

#### 3. Performance Tests (SHOULD HAVE)
```python
# Load Testing
- [ ] 100 concurrent signing requests
- [ ] 1000 requests/second sustained
- [ ] Memory usage under load
- [ ] Database connection pool doesn't exhaust
- [ ] Provider cache performance

# Latency
- [ ] P50 latency < 500ms
- [ ] P95 latency < 2s
- [ ] P99 latency < 5s

# Scalability
- [ ] Performance with 1000 organizations
- [ ] Cache hit rate optimization
```

#### 4. Chaos/Resilience Tests (SHOULD HAVE)
```python
# Network Failures
- [ ] KMS provider unreachable → timeout, not hang
- [ ] Slow KMS responses → timeout after 30s
- [ ] Network partition during signing

# KMS Failures
- [ ] Invalid credentials → clear error message
- [ ] Key not found → 404 with helpful message
- [ ] Permission denied → actionable error
- [ ] Rate limit exceeded → exponential backoff

# Database Failures
- [ ] Connection lost → transaction rolled back
- [ ] Deadlock → retry succeeds
- [ ] Constraint violation → clear error

# Edge Cases
- [ ] Concurrent KMS configuration → one succeeds
- [ ] Delete KMS during signing → graceful failure
- [ ] Cache invalidation on config change
```

## Quick Fix Guide

### Fix #1: Add Authentication (1-2 days)
```python
# 1. Add auth dependency
from marty_common.auth_interceptor import AuthContext

async def get_current_user(
    authorization: str = Header(None)
) -> AuthContext:
    if not authorization:
        raise HTTPException(401, "Authentication required")
    # Validate JWT/session token
    return await validate_token(authorization)

# 2. Add org access check
async def verify_org_access(
    org_id: UUID,
    user: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Organization:
    org = await get_organization(org_id, db)
    if not await user_is_org_member(user, org_id, db):
        raise HTTPException(403, "Not authorized")
    return org

# 3. Update all endpoints
@kms_router.post("/{org_id}/kms/configure")
async def configure_kms(
    user: AuthContext = Depends(get_current_user),  # ADD
    org: Organization = Depends(verify_org_access),  # ADD
    ...
):
```

### Fix #2: Implement Database Session (4 hours)
```python
# Option A: Use existing digital identity infrastructure
from digital_identity.infrastructure.persistence.database import get_db_session

# Option B: Implement locally
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    database_url = os.getenv("DATABASE_URL")
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession)
    
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### Fix #3: Enforce TLS (4 hours)
```python
# Add middleware
class EnforceTLSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if os.getenv("ENVIRONMENT") == "production":
            if request.url.scheme != "https":
                return JSONResponse(
                    status_code=403,
                    content={"detail": "HTTPS required"}
                )
        return await call_next(request)

app.add_middleware(EnforceTLSMiddleware)

# Configure HSTS headers
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*.marty.example.com"]
)
```

### Fix #4: Add Rate Limiting (1 day)
```bash
pip install slowapi redis
```

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@kms_router.post("/{org_id}/kms/configure")
@limiter.limit("10/hour")  # 10 config changes per hour
async def configure_kms(...):
    ...
```

### Fix #5: Add Audit Logging (1 day)
```python
from marty_common.security.access_control import AuditLogger

audit_logger.log_event(AuditLogEntry(
    event_type=AuditEvent.CONFIGURATION_CHANGED,
    user_id=user.identity,
    action="kms_configure",
    result="success",
    additional_data={
        "org_id": str(org_id),
        "provider": provider,
    }
))
```

## Testing Roadmap

### Phase 1: Security Tests (Week 1)
- Days 1-2: Authentication/authorization tests
- Days 3-4: Input validation and injection tests  
- Day 5: Credential security audit

### Phase 2: Integration Tests (Week 2)  
- Days 1-2: AWS KMS integration (localstack)
- Day 3: Vault integration
- Day 4: Database migrations
- Day 5: End-to-end credential issuance

### Phase 3: Performance Tests (Week 3)
- Days 1-2: Load testing setup (locust)
- Days 3-4: Run tests and optimize
- Day 5: Document results and SLOs

### Phase 4: Chaos Tests (Week 4)
- Days 1-2: Network failure scenarios
- Days 3-4: KMS provider failures
- Day 5: Edge case testing

## Metrics to Implement

```python
from prometheus_client import Counter, Histogram

# Success/failure tracking
kms_operations = Counter(
    "kms_operations_total",
    "KMS operations",
    ["operation", "provider", "status"]
)

# Latency tracking
kms_signing_duration = Histogram(
    "kms_signing_seconds",
    "Signing duration",
    ["provider"]
)

# Error tracking
kms_errors = Counter(
    "kms_errors_total",
    "KMS errors",
    ["operation", "provider", "error_type"]
)
```

## Pre-Deployment Checklist

### Code
- [ ] All 3 critical issues fixed
- [ ] All 8 high-priority issues fixed
- [ ] Code review completed
- [ ] Security review completed

### Testing
- [ ] Security tests passing (>20 tests)
- [ ] Integration tests passing (>10 tests)
- [ ] Load tests passing (1000 req/s)
- [ ] All edge cases tested

### Documentation
- [ ] Security assumptions documented
- [ ] Threat model created
- [ ] Disaster recovery runbook
- [ ] Encryption key management guide

### Infrastructure
- [ ] TLS certificates configured
- [ ] Rate limiting configured
- [ ] Monitoring dashboards created
- [ ] Alerts configured
- [ ] Audit logging enabled

### Operations
- [ ] Incident response plan
- [ ] Rollback procedure tested
- [ ] Backup/recovery tested
- [ ] On-call team trained

## Estimated Timeline

| Phase | Duration | Blocker? |
|-------|----------|---------|
| Fix critical issues (1-3) | 2-3 days | ✅ YES |
| Fix high priority (4-11) | 5-7 days | ✅ YES |
| Security testing | 3-5 days | ✅ YES |
| Integration testing | 3-5 days | ⚠️ Recommended |
| Load testing | 2-3 days | ⚠️ Recommended |
| Documentation | 2-3 days | ⚠️ Recommended |
| **TOTAL** | **17-26 days** | |

**Minimum viable deployment:** 10-15 days (critical + high priority + security tests)

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Credential theft | HIGH | CRITICAL | Fix auth, TLS, audit logging |
| Unauthorized access | HIGH | CRITICAL | Fix authentication/authorization |
| DoS attack | MEDIUM | HIGH | Add rate limiting |
| KMS outage | MEDIUM | HIGH | Add retry/circuit breaker |
| Data loss | LOW | CRITICAL | Test backups, key management |
| Performance issues | MEDIUM | HIGH | Load testing, optimization |

## References

- **Full Audit:** [docs/KMS_SECURITY_AUDIT.md](docs/KMS_SECURITY_AUDIT.md)
- **Implementation Status:** [COMPLETE_IMPLEMENTATION.md](COMPLETE_IMPLEMENTATION.md)
- **Deployment Guide:** [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)
- **API Documentation:** [docs/KMS_CONFIGURATION_API.md](docs/KMS_CONFIGURATION_API.md)
