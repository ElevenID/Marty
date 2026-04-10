# KMS Remote Signing Security Audit
**Date:** April 6, 2026  
**Status:** 🔴 **CRITICAL ISSUES FOUND - NOT PRODUCTION READY**  
**Auditor:** GitHub Copilot

## Executive Summary

The Remote Signing and Trust Anchor Upload implementation has **critical security gaps** that must be addressed before public deployment. While the core cryptographic design is sound (Fernet encryption, proper key separation), the REST API layer lacks essential security controls.

**Blocking Issues:** 3  
**High Priority:** 8  
**Medium Priority:** 6  
**Low Priority:** 4

---

## 🚨 CRITICAL - BLOCKING DEPLOYMENT

### 1. No Authentication or Authorization on KMS Endpoints

**Severity:** 🔴 **CRITICAL**  
**Location:** [src/subscription/kms_router.py](src/subscription/kms_router.py)

**Issue:**
The KMS router has **NO authentication or authorization** checks. Any user with network access can:
- Configure KMS for any organization
- View KMS configurations
- Delete KMS settings
- Test signing operations

**Evidence:**
```python
# Line 100 - Database session dependency is a stub
async def get_db_session() -> AsyncSession:
    """Get database session."""
    # TODO: Implement proper database session dependency
    raise NotImplementedError("Database session dependency not configured")

# Line 169 - No user authentication
async def configure_organization_kms(
    org_id: UUID,
    config_request: KMSConfigRequest,
    org: Organization = Depends(get_organization),  # No auth check
    kms_service: KMSConfigService = Depends(get_kms_config_service),
) -> KMSConfigResponse:
```

**Attack Scenarios:**
1. **Unauthorized KMS Takeover:** Attacker configures malicious KMS for victim organization
2. **Credential Theft:** Attacker reads encrypted credentials (even if encrypted at rest)
3. **Denial of Service:** Attacker deletes KMS config, breaking production signing
4. **Privilege Escalation:** FREE tier user configures KMS for their org (tier check happens but no user auth)

**Required Actions:**
- [ ] Implement authentication middleware (JWT, session, or Cedar auth)
- [ ] Add authorization checks (org membership + role validation)
- [ ] Use existing `AuthContext` infrastructure from `marty_common.auth_interceptor`
- [ ] Integrate Cedar policies for fine-grained access control
- [ ] Audit log all KMS configuration changes

**Existing Security Infrastructure:**
```python
# Found in marty_common/authorization.py - NOT USED IN KMS ROUTER
from marty_common.authorization import (
    AuthorizationContext,
    PolicyEngine,
    require,
)

# Example usage pattern found in other services:
@require(permission="kms:configure", resource="organization")
async def configure_organization_kms(...):
    ...
```

**Recommended Fix:**
```python
from marty_common.auth_interceptor import AuthContext
from marty_common.authorization import require

# Add authentication dependency
async def get_current_user(
    authorization: str = Header(None),
    x_user_id: str = Header(None),
) -> AuthContext:
    """Verify user authentication and return context."""
    if not authorization and not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    # Validate JWT or session token
    # Return authenticated user context
    ...

# Add authorization check
async def verify_org_access(
    org_id: UUID,
    user: AuthContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Organization:
    """Verify user has access to organization."""
    org = await get_organization(org_id, db)
    
    # Check organization membership
    if not await user_is_org_member(user.identity, org_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this organization",
        )
    
    # Check role permissions (admin/owner for KMS configuration)
    if not await user_has_permission(user, org_id, "kms:configure", db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for KMS configuration",
        )
    
    return org

# Updated endpoint
@kms_router.post("/{org_id}/kms/configure")
async def configure_organization_kms(
    org_id: UUID,
    config_request: KMSConfigRequest,
    user: AuthContext = Depends(get_current_user),  # ⭐ ADD THIS
    org: Organization = Depends(verify_org_access),  # ⭐ ADD THIS
    kms_service: KMSConfigService = Depends(get_kms_config_service),
) -> KMSConfigResponse:
    ...
```

---

### 2. Database Session Dependency Not Implemented

**Severity:** 🔴 **CRITICAL**  
**Location:** [src/subscription/kms_router.py](src/subscription/kms_router.py#L100-L104)

**Issue:**
The `get_db_session()` dependency raises `NotImplementedError`. All KMS endpoints will fail at runtime.

**Evidence:**
```python
async def get_db_session() -> AsyncSession:
    """Get database session."""
    # TODO: Implement proper database session dependency
    raise NotImplementedError("Database session dependency not configured")
```

**Impact:**
- **All KMS endpoints are non-functional**
- Returns HTTP 500 on every request
- Cannot retrieve organizations or persist KMS configurations

**Required Actions:**
- [ ] Implement database session dependency using existing patterns
- [ ] Integration test actual database operations (not mocked)
- [ ] Verify transaction handling (commit/rollback)

**Recommended Fix:**
```python
# Use existing database manager infrastructure
from digital_identity.infrastructure.persistence.database import get_db_session

# OR implement locally:
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session with proper lifecycle."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    # Get database URL from config
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ConfigurationError("DATABASE_URL not configured")
    
    # Create engine and session
    engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

---

### 3. TLS/HTTPS Not Enforced for Credential Transmission

**Severity:** 🔴 **CRITICAL**  
**Location:** API deployment configuration

**Issue:**
Credentials are sent in POST request bodies. Without TLS enforcement, credentials are transmitted in plaintext over the network.

**Attack Scenario:**
Man-in-the-middle attacker intercepts POST request to `/v1/subscriptions/organizations/{org_id}/kms/configure` and captures:
- AWS Access Key ID + Secret Access Key
- Azure Key Vault credentials
- HSM PIN codes

**Required Actions:**
- [ ] Enforce HTTPS at application level (reject HTTP)
- [ ] Add middleware to verify TLS connection
- [ ] Configure HSTS headers
- [ ] Document TLS requirements in deployment guide
- [ ] Add TLS certificate validation tests

**Recommended Fix:**
```python
# Add middleware to reject non-TLS connections
from starlette.middleware.base import BaseHTTPMiddleware

class EnforceTLSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # In production, require HTTPS
        if os.getenv("ENVIRONMENT") == "production":
            if request.url.scheme != "https":
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "HTTPS required for KMS operations"},
                )
        return await call_next(request)

# Add to FastAPI app
app.add_middleware(EnforceTLSMiddleware)
```

---

## 🔴 HIGH PRIORITY

### 4. No Rate Limiting on KMS Configuration Endpoints

**Severity:** 🔴 **HIGH**  
**Impact:** DoS attacks, brute force, resource exhaustion

**Issue:**
No rate limiting on sensitive operations:
- KMS configuration attempts (could brute force valid org IDs)
- Connectivity tests (could overwhelm external KMS)
- Signing tests (costly KMS API calls)

**Required Actions:**
- [ ] Implement rate limiting middleware (e.g., SlowAPI, redis-based)
- [ ] Per-user rate limits: 10 config changes/hour
- [ ] Per-org rate limits: 100 signing tests/hour
- [ ] Global rate limit: 1000 KMS operations/minute

**Recommended Fix:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@kms_router.post("/{org_id}/kms/configure")
@limiter.limit("10/hour")  # 10 config changes per hour per IP
async def configure_organization_kms(...):
    ...

@kms_router.post("/{org_id}/kms/test-signing")
@limiter.limit("100/hour")  # 100 signing tests per hour
async def test_organization_signing(...):
    ...
```

---

### 5. No Audit Logging for KMS Configuration Changes

**Severity:** 🔴 **HIGH**  
**Impact:** Compliance violations, no forensic capability

**Issue:**
No audit trail for:
- Who configured KMS (user identity)
- When KMS was configured/modified/deleted
- What credentials were provided (metadata only, not values)
- Failed configuration attempts

**Required Actions:**
- [ ] Integrate with existing `AuditLogger` from `marty_common.security.access_control`
- [ ] Log all KMS configuration changes
- [ ] Log failed authentication/authorization attempts
- [ ] Log credential access (decryption events)
- [ ] Structured logging with correlation IDs

**Recommended Fix:**
```python
from marty_common.security.access_control import AuditLogger, AuditEvent

async def configure_organization_kms(
    org_id: UUID,
    config_request: KMSConfigRequest,
    user: AuthContext = Depends(get_current_user),
    org: Organization = Depends(verify_org_access),
    kms_service: KMSConfigService = Depends(get_kms_config_service),
    audit_logger: AuditLogger = Depends(get_audit_logger),
) -> KMSConfigResponse:
    try:
        # Configuration logic...
        
        # Audit log success
        audit_logger.log_event(AuditLogEntry(
            event_type=AuditEvent.CONFIGURATION_CHANGED,
            user_id=user.identity,
            username=user.claims.get("username"),
            action="kms_configure",
            result="success",
            additional_data={
                "organization_id": str(org_id),
                "provider": config_request.provider,
                "region": config_request.config.get("region"),
            },
        ))
        
        return response
    except Exception as e:
        # Audit log failure
        audit_logger.log_event(AuditLogEntry(
            event_type=AuditEvent.CONFIGURATION_CHANGED,
            user_id=user.identity if user else None,
            action="kms_configure",
            result="failure",
            error_message=str(e),
            risk_level="high",
        ))
        raise
```

---

### 6. Encryption Key Management - No Rotation Strategy

**Severity:** 🔴 **HIGH**  
**Impact:** Compromised encryption key = all KMS credentials exposed

**Issue:**
- `KMS_ENCRYPTION_KEY` loaded from environment variable
- No key rotation mechanism
- No key backup/recovery procedure
- What happens if key is lost? (All credentials unrecoverable)
- What happens if key is compromised? (Need to re-encrypt all credentials)

**Required Actions:**
- [ ] Document encryption key backup procedure
- [ ] Implement key rotation mechanism (re-encrypt all credentials)
- [ ] Add key version tracking in database
- [ ] Multiple key support (old + new during rotation)
- [ ] Emergency key rotation runbook

**Recommended Implementation:**
```python
# Database schema update
ALTER TABLE organizations ADD COLUMN kms_key_version INTEGER DEFAULT 1;

# Key rotation service
class EncryptionKeyRotation:
    async def rotate_keys(
        self,
        old_key: bytes,
        new_key: bytes,
        db: AsyncSession,
    ) -> None:
        """Rotate all encrypted KMS credentials."""
        old_cipher = Fernet(old_key)
        new_cipher = Fernet(new_key)
        
        # Get all organizations with KMS configured
        result = await db.execute(
            select(Organization).where(
                Organization.kms_credentials_encrypted != None
            )
        )
        orgs = result.scalars().all()
        
        for org in orgs:
            # Decrypt with old key
            credentials_json = old_cipher.decrypt(
                org.kms_credentials_encrypted.encode()
            )
            
            # Re-encrypt with new key
            org.kms_credentials_encrypted = new_cipher.encrypt(
                credentials_json
            ).decode()
            org.kms_key_version = 2  # Increment version
        
        await db.commit()
```

---

### 7. No Input Validation for Malicious Payloads

**Severity:** 🔴 **HIGH**  
**Impact:** Injection attacks, buffer overflows, resource exhaustion

**Issue:**
Limited validation on:
- KMS configuration sizes (could submit multi-GB JSON)
- Key IDs (could contain SQL injection attempts, command injection)
- Endpoint URLs (could point to internal services - SSRF)
- Provider-specific fields (no strict validation)

**Required Actions:**
- [ ] Add strict size limits (max 10KB for config, 1KB for key IDs)
- [ ] Validate key ID format per provider (regex patterns)
- [ ] Validate endpoint URLs (whitelist domains, block private IPs)
- [ ] Schema validation with Pydantic strict mode
- [ ] Fuzz testing with malicious inputs

**Recommended Fix:**
```python
from pydantic import BaseModel, Field, validator, HttpUrl
from typing import Literal
import re
import ipaddress
from urllib.parse import urlparse

class KMSConfigRequest(BaseModel):
    provider: Literal[
        "aws_kms",
        "azure_key_vault", 
        "gcp_kms",
        "hashicorp_vault",
        "pkcs11_hsm",
        "software_hsm"
    ]  # Strict enum
    
    credentials: dict[str, Any] = Field(
        ...,
        max_length=10240,  # Max 10KB
        description="Provider credentials"
    )
    
    config: dict[str, Any] = Field(
        ...,
        max_length=10240,  # Max 10KB
        description="Provider configuration"
    )
    
    @validator("config")
    def validate_config(cls, v, values):
        """Validate provider-specific configuration."""
        provider = values.get("provider")
        
        # Validate endpoint URL if present
        if "endpoint_url" in v:
            endpoint = v["endpoint_url"]
            
            # Parse URL
            parsed = urlparse(endpoint)
            
            # Block private IPs (SSRF protection)
            try:
                ip = ipaddress.ip_address(parsed.hostname)
                if ip.is_private or ip.is_loopback:
                    raise ValueError(
                        "Endpoint URL cannot point to private IP addresses"
                    )
            except ValueError:
                pass  # Not an IP, likely a domain name
            
            # Require HTTPS for external endpoints
            if parsed.scheme != "https":
                raise ValueError("Endpoint URL must use HTTPS")
        
        # Validate key_id format
        if "key_id" in v:
            key_id = v["key_id"]
            
            # Size limit
            if len(key_id) > 1024:
                raise ValueError("Key ID exceeds maximum length")
            
            # Provider-specific validation
            if provider == "aws_kms":
                # AWS KMS ARN or key ID format
                aws_pattern = r"^(arn:aws:kms:[a-z0-9-]+:\d{12}:key/)?[a-f0-9-]+$"
                if not re.match(aws_pattern, key_id):
                    raise ValueError("Invalid AWS KMS key ID format")
        
        return v
    
    class Config:
        # Strict mode - reject extra fields
        extra = "forbid"
```

---

### 8. No Timeout or Retry Logic for KMS Operations

**Severity:** 🔴 **HIGH**  
**Impact:** Hung requests, cascading failures, poor user experience

**Issue:**
- No timeouts on KMS provider operations (could hang indefinitely)
- No retry logic for transient failures
- No circuit breaker for repeated failures
- Synchronous blocking calls could exhaust thread pool

**Required Actions:**
- [ ] Add timeouts to all external KMS calls (5-30 seconds)
- [ ] Implement exponential backoff retry (3 attempts)
- [ ] Add circuit breaker pattern (use `pybreaker`)
- [ ] Async/await for all KMS operations
- [ ] Graceful degradation when KMS unavailable

**Recommended Fix:**
```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import asyncio

class RemoteSigningService:
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    )
    async def sign(
        self,
        organization: Organization,
        key_id: str,
        payload: bytes,
        algorithm: str = "ES256",
        requesting_role: CryptoRole = CryptoRole.DOCUMENT_SIGNER,
    ) -> bytes:
        """Sign with retry and timeout."""
        try:
            # Get manager
            manager = await self.get_manager(organization)
            
            # Sign with timeout
            signature = await asyncio.wait_for(
                manager.sign(
                    key_identity=KeyIdentity(key_id=key_id),
                    payload=payload,
                    purpose=KeyPurpose.DOCUMENT_SIGNING,
                    requesting_role=requesting_role,
                ),
                timeout=30.0,  # 30 second timeout
            )
            
            return signature
            
        except asyncio.TimeoutError:
            self.logger.error(
                f"KMS signing timeout for org {organization.id}"
            )
            raise RemoteSigningError(
                "KMS signing operation timed out. "
                "Please check your KMS connectivity."
            )
        except ConnectionError as e:
            self.logger.error(
                f"KMS connection error for org {organization.id}: {e}"
            )
            raise RemoteSigningError(
                "Failed to connect to KMS. Please verify your configuration."
            )
```

---

### 9. Provider Cache - No Invalidation or TTL

**Severity:** 🔴 **HIGH**  
**Impact:** Stale configurations, credential leaks in memory

**Issue:**
```python
# RemoteSigningService caches providers indefinitely
self._provider_cache: dict[UUID, KMSProviderInterface] = {}
```

Problems:
- If KMS config is deleted, cached provider still used
- If credentials are rotated, old credentials still in cache
- Memory leak if many organizations configure KMS
- No cache eviction policy

**Required Actions:**
- [ ] Implement cache TTL (expire after 1 hour)
- [ ] Cache invalidation on config update/delete
- [ ] LRU cache with size limit (max 100 providers)
- [ ] Explicit cache clear API for admins

**Recommended Fix:**
```python
from cachetools import TTLCache
from datetime import datetime, timedelta

class RemoteSigningService:
    def __init__(self, db: AsyncSession, kms_config_service: KMSConfigService):
        self.db = db
        self.kms_config_service = kms_config_service
        
        # TTL cache: max 100 entries, 1 hour TTL
        self._provider_cache = TTLCache(maxsize=100, ttl=3600)
        self._manager_cache = TTLCache(maxsize=100, ttl=3600)
        self._lock = asyncio.Lock()
    
    async def clear_cache(self, organization_id: UUID) -> None:
        """Clear cache for organization (e.g., after config change)."""
        async with self._lock:
            self._provider_cache.pop(organization_id, None)
            self._manager_cache.pop(organization_id, None)

# Update KMS config service to clear cache
class KMSConfigService:
    async def configure_kms(self, organization: Organization, ...):
        # ... configuration logic ...
        
        # Clear provider cache after config change
        if hasattr(self, "remote_signing_service"):
            await self.remote_signing_service.clear_cache(organization.id)
    
    async def delete_kms_config(self, organization: Organization):
        # ... deletion logic ...
        
        # Clear provider cache after deletion
        if hasattr(self, "remote_signing_service"):
            await self.remote_signing_service.clear_cache(organization.id)
```

---

### 10. No Integration Tests with Real KMS Providers

**Severity:** 🔴 **HIGH**  
**Impact:** Unexpected failures in production, API incompatibilities

**Issue:**
All tests use mocks. No validation that:
- AWS KMS integration actually works
- Credential formatting is correct
- Error handling matches real KMS responses
- Performance is acceptable

**Required Actions:**
- [ ] Add integration tests with real KMS (use test keys)
- [ ] AWS KMS integration test (use localstack or test account)
- [ ] HashiCorp Vault integration test (use dev server)
- [ ] Load testing with concurrent signing requests
- [ ] Chaos testing (network failures, timeouts)

**Test Infrastructure Needed:**
```python
# tests/integration/test_aws_kms_integration.py
import pytest
import boto3
from moto import mock_kms

@pytest.mark.integration
@pytest.mark.aws
@mock_kms
async def test_aws_kms_real_integration():
    """Test with mocked AWS KMS (moto library)."""
    # Create KMS client
    client = boto3.client("kms", region_name="us-east-1")
    
    # Create test key
    key_response = client.create_key(
        Description="Test key for Marty integration tests",
        KeyUsage="SIGN_VERIFY",
        KeySpec="ECC_NIST_P256",
    )
    key_id = key_response["KeyMetadata"]["KeyId"]
    
    # Test organization configuration
    org = await create_test_organization(tier="STARTER")
    
    config_service = KMSConfigService(db_session)
    await config_service.configure_kms(
        organization=org,
        provider="aws_kms",
        credentials={
            "access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        },
        config=KMSProviderConfig(
            provider="aws_kms",
            region="us-east-1",
            key_id=key_id,
        ),
    )
    
    # Test signing
    remote_signing = RemoteSigningService(db_session, config_service)
    signature = await remote_signing.sign(
        organization=org,
        key_id=key_id,
        payload=b"test payload",
    )
    
    assert signature is not None
    assert len(signature) > 0
```

---

### 11. No Load Testing or Performance Benchmarks

**Severity:** 🔴 **HIGH**  
**Impact:** Unknown scalability limits, potential production outages

**Issue:**
No testing of:
- Concurrent signing requests
- Database connection pool exhaustion
- KMS API rate limits
- Memory usage with many organizations

**Required Actions:**
- [ ] Load test with locust or k6 (1000 req/sec)
- [ ] Profile memory usage under load
- [ ] Test database connection pool behavior
- [ ] Measure KMS operation latency (p50, p95, p99)
- [ ] Identify bottlenecks and optimize

**Load Test Script:**
```python
# tests/performance/test_kms_load.py
from locust import HttpUser, task, between

class KMSLoadTest(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        """Setup - authenticate and get org ID."""
        self.org_id = "test-org-uuid"
        self.token = "test-auth-token"
    
    @task(10)
    def test_get_kms_config(self):
        """Read KMS config (common operation)."""
        self.client.get(
            f"/v1/subscriptions/organizations/{self.org_id}/kms",
            headers={"Authorization": f"Bearer {self.token}"},
        )
    
    @task(5)
    def test_connectivity(self):
        """Test KMS connectivity."""
        self.client.get(
            f"/v1/subscriptions/organizations/{self.org_id}/kms/test-connectivity",
            headers={"Authorization": f"Bearer {self.token}"},
        )
    
    @task(1)
    def test_signing(self):
        """Test remote signing (expensive operation)."""
        self.client.post(
            f"/v1/subscriptions/organizations/{self.org_id}/kms/test-signing",
            json={
                "key_id": "test-key-id",
                "test_payload": "test data",
            },
            headers={"Authorization": f"Bearer {self.token}"},
        )

# Run: locust -f tests/performance/test_kms_load.py --host=https://api.marty.example
```

---

## ⚠️ MEDIUM PRIORITY

### 12. Migration Backwards Compatibility Not Tested

**Severity:** ⚠️ **MEDIUM**  
**Impact:** Failed rollback in production emergency

**Issue:**
- Forward migration tested implicitly
- Rollback migration never executed in tests
- No verification that existing data survives migration

**Required Actions:**
- [ ] Test migration on copy of production database
- [ ] Test rollback migration
- [ ] Verify data integrity after rollback
- [ ] Add migration validation to CI/CD

---

### 13. No Monitoring or Alerting Configuration

**Severity:** ⚠️ **MEDIUM**  
**Impact:** No visibility into production issues

**Issue:**
No metrics, dashboards, or alerts for:
- KMS configuration success/failure rates
- Signing operation latency
- Error rates by provider
- Credential decryption failures

**Required Actions:**
- [ ] Add Prometheus metrics
- [ ] Create Grafana dashboards
- [ ] Configure alerts (error rate > 5%, latency > 5s)
- [ ] Document SLOs (99.9% availability, <2s latency)

**Recommended Metrics:**
```python
from prometheus_client import Counter, Histogram, Gauge

# Metrics
kms_config_operations = Counter(
    "kms_config_operations_total",
    "Total KMS configuration operations",
    ["operation", "provider", "status"],
)

kms_signing_duration = Histogram(
    "kms_signing_duration_seconds",
    "Time spent signing with KMS",
    ["provider", "algorithm"],
)

kms_active_providers = Gauge(
    "kms_active_providers",
    "Number of organizations with active KMS configuration",
    ["provider"],
)

# Usage
async def configure_kms(...):
    try:
        # ... config logic ...
        kms_config_operations.labels(
            operation="configure",
            provider=provider,
            status="success",
        ).inc()
    except Exception:
        kms_config_operations.labels(
            operation="configure",
            provider=provider,
            status="error",
        ).inc()
        raise
```

---

### 14. Credentials Visible in Logs or Error Messages

**Severity:** ⚠️ **MEDIUM**  
**Impact:** Credential leaks in log aggregation systems

**Issue:**
Need to audit all logging statements to ensure credentials never logged.

**Required Actions:**
- [ ] Audit all logger calls for credential leakage
- [ ] Add credential redaction to Logger formatter
- [ ] Never log full exception tracebacks containing credentials
- [ ] Sanitize error messages returned to clients

**Recommended Fix:**
```python
import logging
import re

class CredentialRedactingFilter(logging.Filter):
    """Remove credentials from log records."""
    
    PATTERNS = [
        (re.compile(r"(access_key_id['\"]:\s*['\"])[^'\"]+"), r"\1***REDACTED***"),
        (re.compile(r"(secret_access_key['\"]:\s*['\"])[^'\"]+"), r"\1***REDACTED***"),
        (re.compile(r"(password['\"]:\s*['\"])[^'\"]+"), r"\1***REDACTED***"),
        (re.compile(r"(token['\"]:\s*['\"])[^'\"]+"), r"\1***REDACTED***"),
    ]
    
    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg:
            for pattern, replacement in self.PATTERNS:
                record.msg = pattern.sub(replacement, str(record.msg))
        return True

# Add to root logger
logging.getLogger().addFilter(CredentialRedactingFilter())
```

---

### 15. No Disaster Recovery Procedure

**Severity:** ⚠️ **MEDIUM**  
**Impact:** Extended downtime in catastrophic failure

**Issue:**
No documented or tested procedures for:
- Encryption key loss (all credentials unrecoverable)
- Database corruption
- Mass KMS configuration deletion
- Cascading KMS provider failures

**Required Actions:**
- [ ] Document disaster recovery runbook
- [ ] Backup encryption keys securely (HSM or key management service)
- [ ] Regular database backups with encryption key backups
- [ ] Test recovery procedures quarterly

---

### 16. Edge Cases in Tier Downgrade/Upgrade

**Severity:** ⚠️ **MEDIUM**  
**Impact:** Orphaned KMS configurations, signing failures

**Issue:**
What happens when:
- Organization downgrades from STARTER → FREE (KMS config orphaned?)
- Organization upgrades from FREE → STARTER (prompted to configure KMS?)
- Subscription expires (fall back to service vault?)

**Required Actions:**
- [ ] Define tier transition behavior
- [ ] Implement graceful degradation (keep config, disable signing)
- [ ] Add tests for tier transitions
- [ ] Document user experience during transitions

---

### 17. Concurrent Modification Conflicts

**Severity:** ⚠️ **MEDIUM**  
**Impact:** Lost updates, inconsistent state

**Issue:**
Two admin users could simultaneously:
- Configure KMS (last write wins, no warning)
- Delete KMS while signing operation in progress
- Update config while connectivity test running

**Required Actions:**
- [ ] Add optimistic locking (version field in database)
- [ ] Test concurrent operations
- [ ] Return HTTP 409 Conflict on version mismatch

**Recommended Fix:**
```sql
-- Add version column
ALTER TABLE organizations ADD COLUMN kms_config_version INTEGER DEFAULT 1;

-- Update with version check
UPDATE organizations
SET kms_provider = 'aws_kms',
    kms_config = '...',
    kms_config_version = kms_config_version + 1
WHERE id = $1 AND kms_config_version = $2;
-- If 0 rows updated, version mismatch = conflict
```

---

### 18. No Documentation for Security Assumptions

**Severity:** ⚠️ **MEDIUM**  
**Impact:** Misconfigurations, security gaps

**Issue:**
Missing documentation:
- Assumed network security (private VPC?)
- Required IAM permissions for AWS KMS
- Firewall rules for HSM access
- Credential storage security model

**Required Actions:**
- [ ] Create security architecture document
- [ ] Document trust boundaries
- [ ] Create threat model
- [ ] Document security assumptions explicitly

---

## 📋 LOW PRIORITY

### 19. Test Script Has Secrets in Command Line

**Severity:** 📋 **LOW**  
**Location:** [scripts/test_kms_endpoints.py](scripts/test_kms_endpoints.py)

**Issue:**
Example usage shows secrets in command line:
```bash
python scripts/test_kms_endpoints.py --token "secret-token"
```

Command line arguments are visible in process lists (`ps aux`), system logs, shell history.

**Required Actions:**
- [ ] Support environment variables for secrets
- [ ] Support credentials from file (.env or config)
- [ ] Update documentation examples

---

### 20. No Metrics on Encryption/Decryption Performance

**Severity:** 📋 **LOW**  

**Issue:**
Fernet encryption overhead not measured. Could be bottleneck with large credential payloads.

**Required Actions:**
- [ ] Add metrics for encrypt/decrypt operations
- [ ] Benchmark with various payload sizes

---

### 21. API Response Inconsistency

**Severity:** 📋 **LOW**  

**Issue:**
Inconsistent field naming:
- Some responses use `configured_at` (timestamp)
- Others omit timestamps entirely
- No consistent error response format

**Required Actions:**
- [ ] Standardize response schemas
- [ ] Always include timestamps
- [ ] Consistent error format (RFC 7807 Problem Details)

---

### 22. No Internationalization

**Severity:** 📋 **LOW**  

**Issue:**
Error messages hard-coded in English. No i18n support.

**Required Actions:**
- [ ] Add i18n framework (if required)
- [ ] Translate error messages
- [ ] Support Accept-Language header

---

## Testing Recommendations

### Critical Tests to Add Before Deployment

#### Security Tests
```python
# tests/security/test_kms_auth.py

async def test_unauthenticated_request_rejected():
    """Verify unauthenticated requests are rejected."""
    response = client.post(
        f"/v1/subscriptions/organizations/{org_id}/kms/configure",
        json=kms_config,
        # NO Authorization header
    )
    assert response.status_code == 401

async def test_wrong_org_access_denied():
    """Verify users cannot access other organizations."""
    user_a_token = authenticate_user("user_a")
    org_b_id = create_organization(owner="user_b")
    
    response = client.post(
        f"/v1/subscriptions/organizations/{org_b_id}/kms/configure",
        json=kms_config,
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert response.status_code == 403

async def test_sql_injection_in_org_id():
    """Test SQL injection protection."""
    response = client.get(
        "/v1/subscriptions/organizations/'; DROP TABLE organizations; --/kms",
    )
    assert response.status_code in [400, 404]  # Not 500

async def test_ssrf_in_endpoint_url():
    """Prevent SSRF attacks via endpoint_url."""
    response = client.post(
        f"/v1/subscriptions/organizations/{org_id}/kms/configure",
        json={
            "provider": "aws_kms",
            "credentials": {...},
            "config": {
                "endpoint_url": "http://169.254.169.254/latest/meta-data/",  # AWS metadata
            },
        },
    )
    assert response.status_code == 400
    assert "private" in response.json()["detail"].lower()
```

#### Integration Tests
```python
# tests/integration/test_kms_real_providers.py

@pytest.mark.integration
async def test_aws_kms_end_to_end():
    """Full flow with real AWS KMS (or localstack)."""
    # Configure KMS
    # Issue credential
    # Verify signature
    pass

@pytest.mark.integration
async def test_credential_issuance_with_remote_signing():
    """Test full credential issuance flow."""
    # Create STARTER tier organization
    # Configure KMS
    # Issue credential via digital identity service
    # Verify credential uses remote signing
    # Validate signature
    pass
```

#### Performance Tests
```python
# tests/performance/test_concurrent_signing.py

async def test_concurrent_signing_requests():
    """Test 100 concurrent signing requests."""
    tasks = [
        remote_signing_service.sign(org, key_id, f"payload_{i}".encode())
        for i in range(100)
    ]
    
    start = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    duration = time.time() - start
    
    # Verify all succeeded
    assert all(isinstance(r, bytes) for r in results)
    
    # Performance assertion (< 5s for 100 requests)
    assert duration < 5.0
```

---

## Deployment Checklist

Before deploying to production:

- [ ] **CRITICAL #1:** Implement authentication/authorization
- [ ] **CRITICAL #2:** Implement database session dependency
- [ ] **CRITICAL #3:** Enforce TLS/HTTPS
- [ ] **HIGH #4:** Add rate limiting
- [ ] **HIGH #5:** Add audit logging
- [ ] **HIGH #6:** Document encryption key management
- [ ] **HIGH #7:** Add input validation
- [ ] **HIGH #8:** Add timeouts and retry logic
- [ ] **HIGH #9:** Fix provider cache issues
- [ ] **HIGH #10:** Add integration tests with real KMS
- [ ] **HIGH #11:** Perform load testing
- [ ] Run full security audit
- [ ] Penetration testing
- [ ] Code review by security team
- [ ] Document all security assumptions
- [ ] Create incident response runbook
- [ ] Set up monitoring and alerting
- [ ] Test disaster recovery procedures

---

## Secure Deployment Architecture

Recommended production setup:

```
┌─────────────────────────────────────────────────┐
│                    Internet                      │
└───────────────────┬─────────────────────────────┘
                    │ HTTPS only
                    ▼
          ┌──────────────────┐
          │   API Gateway    │ ← Rate limiting, WAF
          │  + TLS Termination│
          └─────────┬────────┘
                    │ Internal TLS
                    ▼
          ┌──────────────────┐
          │   FastAPI App    │ ← Authentication, Authorization
          │  (KMS Router)    │    Input validation
          └─────────┬────────┘
                    │
        ┌───────────┴──────────┐
        │                      │
        ▼                      ▼
┌────────────────┐   ┌─────────────────┐
│  PostgreSQL    │   │ Customer KMS    │
│  (Encrypted)   │   │ (AWS/Azure/GCP) │
└────────────────┘   └─────────────────┘
        │
        │ Backup to
        ▼
┌────────────────────┐
│ Encrypted Backups  │
│ (includes key backup)│
└────────────────────┘
```

---

## Summary

**Overall Assessment:** 🔴 **NOT PRODUCTION READY**

The implementation has solid cryptographic foundations but **critical security gaps** in the API layer. The three blocking issues (no auth, broken database dependency, no TLS enforcement) must be fixed before any production deployment.

**Estimated Remediation Effort:**
- Critical issues (1-3): 2-3 days
- High priority (4-11): 5-7 days
- Medium priority (12-18): 3-4 days
- **Total: 10-14 days** with 1 engineer

**Risk Level:** **HIGH** - Do not deploy without fixing at least the 3 critical and 8 high-priority issues.

---

**Next Steps:**
1. Review this audit with security team
2. Prioritize fixes (start with authentication)
3. Add comprehensive security tests
4. Schedule penetration testing
5. Create security documentation
6. Re-audit after fixes

