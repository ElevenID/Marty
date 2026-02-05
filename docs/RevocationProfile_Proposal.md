# RevocationProfile Abstraction Proposal

## Executive Summary

**Problem:** Revocation management complexity is currently scattered across Trust Profiles, issuance services, and verification logic. Organizations must understand OCSP, CRL, StatusList2021, BitstringStatusList, TokenStatusList, and format-specific mechanisms to configure revocation properly.

**Solution:** Introduce **RevocationProfile** as a new sub-abstraction within the Digital Identity model that hides complexity, enables automation, and provides format-agnostic revocation configuration.

---

## Current State Analysis

### Scattered Concerns

1. **Trust Profile** (port 8004): Contains `RevocationPolicy` with:
   - `check_mode`: HARD_FAIL, SOFT_FAIL, SKIP
   - `check_ocsp`: bool
   - `check_crl`: bool
   - `check_status_list`: bool
   - `offline_grace_period_hours`, `cache_duration_hours`

2. **Issuance Service** (port 8005): Manages credential lifecycle:
   - POST `/credentials/{id}/revoke`
   - POST `/credentials/{id}/suspend`
   - POST `/credentials/{id}/reinstate`
   - GET `/credentials/{id}/status`

3. **Status List Manager** (marty-ui/src/revocation):
   - `StatusListFormat`: TOKEN_STATUS_LIST (mDoc/CWT), BITSTRING_STATUS_LIST (SD-JWT VC)
   - Index allocation, bitstring management
   - GZIP/DEFLATE compression
   - Publishing logic

4. **Verification Logic** (marty-core/marty-verification):
   - StatusList2021Entry
   - BitstringStatusListEntry
   - RevocationList2020
   - OCSP/CRL checking for X.509 certificates

### Key Pain Points

1. **Format Complexity**: Different mechanisms for different formats
   - mDoc → TokenStatusList (CBOR, 8-bit)
   - SD-JWT → BitstringStatusList (gzip, 1-bit)
   - W3C VC → StatusList2021 or RevocationList2020
   - X.509 → OCSP/CRL
   - Open Badges → BitstringStatusListEntry

2. **Issuer Burden**: Issuers must:
   - Allocate status list indices
   - Publish status lists at stable URLs
   - Update lists synchronously or async
   - Handle format-specific encoding
   - Manage list growth and rotation

3. **Verifier Configuration**: Verifiers must understand:
   - Which mechanisms are supported
   - Fallback behavior when checks fail
   - Cache strategies for offline operation
   - Format-specific parsing

4. **No Centralized Revocation Registry**: Status lists are issuer-hosted; no cross-issuer discovery

---

## Proposed Solution: RevocationProfile

### Core Concept

**RevocationProfile** is a reusable revocation configuration that abstracts format-specific mechanisms and provides automation for both issuers and verifiers.

**Relationship to Trust Profile:**
- Trust Profile → references → RevocationProfile (many-to-one)
- Multiple Trust Profiles can share a RevocationProfile
- RevocationProfile owned by organization, Trust Profile links to it

**Ownership:**
- Issuers create RevocationProfiles for credentials they issue
- Verifiers reference RevocationProfiles in Trust Profiles
- System provides default profiles for standard compliance

---

## RevocationProfile Structure

### Domain Model

```python
@dataclass
class RevocationProfile:
    """
    RevocationProfile - format-agnostic revocation configuration.
    
    Hides complexity of OCSP/CRL/StatusList and provides automation
    for both issuers (publishing) and verifiers (checking).
    """
    id: str
    organization_id: str
    name: str
    description: str | None
    status: RevocationProfileStatus  # DRAFT, ACTIVE, SUSPENDED
    
    # === ISSUER CONFIGURATION ===
    # How credentials are revoked (issuer-side)
    issuer_config: IssuerRevocationConfig
    
    # === VERIFIER CONFIGURATION ===
    # How revocation is checked (verifier-side)
    verifier_config: VerifierRevocationConfig
    
    # === AUTOMATION SETTINGS ===
    # Auto-configuration and defaults
    automation_config: RevocationAutomationConfig
    
    # Format support (derived from credential formats)
    supported_formats: list[CredentialFormat]
    
    created_at: datetime
    updated_at: datetime


@dataclass
class IssuerRevocationConfig:
    """Configuration for credential issuers."""
    
    # Status list management
    status_list_strategy: StatusListStrategy  # AUTO, MANUAL, REGISTRY
    status_list_base_url: str | None  # Where to publish status lists
    status_list_size: int = 131072  # Default 16KB bitstring
    
    # Update behavior
    update_mode: UpdateMode  # SYNC, ASYNC_QUEUE, BATCH
    batch_interval_seconds: int = 300  # For BATCH mode
    
    # List rotation
    enable_rotation: bool = True
    rotation_threshold_percent: int = 80  # Rotate at 80% capacity
    
    # Formats to support
    enable_bitstring_status_list: bool = True  # W3C SD-JWT/VC
    enable_token_status_list: bool = True      # IETF mDoc/CWT
    enable_legacy_revocation_list: bool = False  # RevocationList2020


@dataclass
class VerifierRevocationConfig:
    """Configuration for credential verifiers."""
    
    # Check behavior
    check_mode: RevocationCheckMode  # HARD_FAIL, SOFT_FAIL, SKIP
    
    # Mechanism priority (try in order)
    mechanism_priority: list[RevocationMechanism]  # e.g., [STATUS_LIST, OCSP, CRL]
    
    # Caching for offline operation
    cache_status_lists: bool = True
    cache_duration_seconds: int = 3600
    offline_grace_period_seconds: int = 86400  # 24 hours
    
    # Timeout/retry
    check_timeout_seconds: int = 5
    max_retries: int = 2
    
    # Trust requirements
    require_issuer_signature_on_status_list: bool = True
    allow_third_party_registries: bool = False


@dataclass
class RevocationAutomationConfig:
    """Automation settings to reduce manual configuration."""
    
    # Auto-allocate indices when issuing credentials
    auto_allocate_indices: bool = True
    
    # Auto-publish status lists after updates
    auto_publish: bool = True
    
    # Auto-generate status list credentials (VC wrapper)
    auto_generate_status_list_credentials: bool = True
    
    # Auto-discover revocation endpoints from credential
    auto_discover_endpoints: bool = True
    
    # Format-specific defaults
    use_format_defaults: bool = True  # Use spec-recommended defaults per format


class RevocationMechanism(str, Enum):
    """Revocation check mechanisms."""
    STATUS_LIST = "status_list"  # W3C/IETF status lists
    OCSP = "ocsp"                # Online Certificate Status Protocol
    CRL = "crl"                  # Certificate Revocation List
    REGISTRY = "registry"        # Third-party revocation registry
    

class StatusListStrategy(str, Enum):
    """How status lists are managed."""
    AUTO = "auto"        # Fully automated (system manages everything)
    MANUAL = "manual"    # Issuer manages indices and publishing
    REGISTRY = "registry"  # Delegate to external registry service


class UpdateMode(str, Enum):
    """How status list updates are processed."""
    SYNC = "sync"            # Update immediately (blocking)
    ASYNC_QUEUE = "async"    # Queue updates, process async
    BATCH = "batch"          # Batch updates at intervals
```

---

## API Design

### New Endpoints

```
# RevocationProfile CRUD
POST   /v1/revocation-profiles
GET    /v1/revocation-profiles?organization_id={id}
GET    /v1/revocation-profiles/{id}
PUT    /v1/revocation-profiles/{id}
DELETE /v1/revocation-profiles/{id}
POST   /v1/revocation-profiles/{id}/activate

# Status list operations (automated by profile)
GET    /v1/revocation-profiles/{id}/status-lists
POST   /v1/revocation-profiles/{id}/status-lists/{format}/publish
GET    /v1/revocation-profiles/{id}/status-lists/{format}/allocate-index

# Credential revocation (now references profile)
POST   /v1/revocation-profiles/{id}/revoke
  body: { credential_id, reason, credential_format }
POST   /v1/revocation-profiles/{id}/suspend
POST   /v1/revocation-profiles/{id}/reinstate
GET    /v1/revocation-profiles/{id}/check
  query: credential_id, format

# Verification endpoint (format-agnostic)
POST   /v1/revocation-profiles/{id}/verify-status
  body: { credential_status_field, credential_format, issuer_did }
```

### Trust Profile Integration

```python
@dataclass
class TrustProfile:
    # ... existing fields ...
    
    # NEW: Reference to RevocationProfile
    revocation_profile_id: str | None = None
    
    # DEPRECATED: Remove inline revocation_policy
    # revocation_policy: RevocationPolicy  # <- REMOVE
```

### Application Template Integration

```python
@dataclass
class ApplicationTemplate:
    # ... existing fields ...
    
    # NEW: Reference to RevocationProfile for issued credentials
    revocation_profile_id: str | None = None
```

---

## Automation Examples

### Example 1: Auto-Managed Revocation (Zero Config)

**Issuer creates Application Template with revocation:**

```json
POST /v1/application-templates
{
  "name": "mDL Issuance",
  "organization_id": "org-123",
  "credential_template_ids": ["ct-mdl-v1"],
  "revocation_profile_id": "rp-auto-mdl"
}
```

**RevocationProfile `rp-auto-mdl` (system default):**

```json
{
  "id": "rp-auto-mdl",
  "name": "Auto mDL Revocation",
  "status": "active",
  "issuer_config": {
    "status_list_strategy": "auto",
    "status_list_base_url": "https://status.dmv.example.com/mdl",
    "update_mode": "sync",
    "enable_token_status_list": true
  },
  "verifier_config": {
    "check_mode": "hard_fail",
    "mechanism_priority": ["status_list"],
    "cache_status_lists": true
  },
  "automation_config": {
    "auto_allocate_indices": true,
    "auto_publish": true,
    "auto_generate_status_list_credentials": true,
    "use_format_defaults": true
  }
}
```

**Workflow (fully automated):**

1. Issue credential → system auto-allocates index from status list
2. Credential includes `credentialStatus` field with index
3. Revoke → `POST /v1/revocation-profiles/rp-auto-mdl/revoke`
4. System updates status list bitstring synchronously
5. System publishes updated status list to configured URL
6. Verifiers check status using cached or fresh status list

**Issuer effort: ZERO configuration beyond selecting profile**

---

### Example 2: High-Volume Batch Revocation

**RevocationProfile for airline pre-boarding:**

```json
{
  "id": "rp-preboard-batch",
  "name": "Pre-Boarding Batch Revocation",
  "issuer_config": {
    "status_list_strategy": "auto",
    "update_mode": "batch",
    "batch_interval_seconds": 60,  // Update every minute
    "enable_bitstring_status_list": true
  },
  "verifier_config": {
    "check_mode": "soft_fail",  // Don't block boarding if check unavailable
    "cache_duration_seconds": 300,  // 5-minute cache
    "offline_grace_period_seconds": 3600  // 1-hour offline grace
  }
}
```

**Benefits:**
- Batch updates reduce publishing overhead
- Soft-fail ensures gates don't halt on network issues
- Offline grace period enables operation during connectivity loss

---

### Example 3: Verifier Trust Profile with Revocation

**Trust Profile for airport gate:**

```json
{
  "id": "tp-airport-gate",
  "name": "Airport Gate Trust",
  "organization_id": "org-airport",
  "revocation_profile_id": "rp-preboard-batch",
  "supported_formats": ["sd_jwt_vc", "mdoc"],
  "validation_rules": { ... },
  "time_policy": { ... }
}
```

**Verification flow:**
1. Gate presents credential with `credentialStatus` field
2. Presentation Policy references `tp-airport-gate`
3. Verification service loads `rp-preboard-batch`
4. Checks revocation using profile's `verifier_config`
5. Uses cached status list if available (5-min TTL)
6. Falls back to soft-fail if check times out
7. Returns verification result with revocation status

---

## Migration Path

### Phase 1: Introduce RevocationProfile (Non-Breaking)

1. Add RevocationProfile entity and service (port 8013)
2. Keep existing `revocation_policy` in Trust Profile (deprecated)
3. Add optional `revocation_profile_id` to Trust Profile
4. Verification logic checks both (profile takes precedence)

### Phase 2: Migrate Existing Configurations

1. Script to convert `revocation_policy` → RevocationProfile
2. Create default profiles for common patterns
3. Update Trust Profiles to reference profiles

### Phase 3: Remove Legacy (Breaking)

1. Remove inline `revocation_policy` from Trust Profile
2. Make `revocation_profile_id` required for Trust Profiles with revocation
3. Update API documentation

---

## Implementation Checklist

### New Service: RevocationProfile Service (port 8013)

- [ ] Domain model (RevocationProfile, configs)
- [ ] Repository (in-memory → PostgreSQL)
- [ ] CRUD endpoints
- [ ] Default profile templates
- [ ] Integration with Trust Profile service

### Updated Services

- [ ] **Trust Profile**: Add `revocation_profile_id` field
- [ ] **Issuance Service**: Reference RevocationProfile for lifecycle operations
- [ ] **Presentation Policy**: Load RevocationProfile via Trust Profile
- [ ] **Status List Manager**: Accept RevocationProfile config

### Gateway API

- [ ] Add `/v1/revocation-profiles` routes
- [ ] Update `/v1/trust-profiles` schema
- [ ] Add verification endpoint wrapper

### Documentation

- [ ] Update Digital Identity model white paper
- [ ] API reference for RevocationProfile
- [ ] Migration guide
- [ ] Best practices guide

---

## Benefits Summary

### For Issuers

✅ **Simplified Configuration**: Select profile instead of understanding OCSP/CRL/StatusList
✅ **Automation**: Auto-allocate indices, auto-publish lists, auto-handle formats
✅ **Reusability**: One profile for multiple credential templates
✅ **Compliance**: System profiles ensure spec compliance

### For Verifiers

✅ **Unified Interface**: Check revocation regardless of format
✅ **Offline Support**: Automatic caching with configurable grace periods
✅ **Fallback Logic**: Graceful degradation when checks unavailable
✅ **Performance**: Cached status lists reduce network overhead

### For Operators

✅ **Visibility**: Centralized revocation configuration
✅ **Auditing**: Track all revocation events by profile
✅ **Scaling**: Batch mode for high-volume scenarios
✅ **Flexibility**: Manual override when needed

---

## Open Questions

1. **Registry Integration**: Should we support third-party revocation registries (e.g., blockchain-based)?
2. **Status List Rotation**: How to handle credential references to old status list URLs?
3. **Multi-Tenant**: How to isolate status lists per organization while allowing shared profiles?
4. **Versioning**: How to version RevocationProfiles and handle changes?

---

## Recommendation

**Proceed with Phase 1 implementation:**

1. Introduce RevocationProfile as new entity (port 8013)
2. Add optional reference in Trust Profile (non-breaking)
3. Implement automation for issuance service
4. Create system default profiles for common patterns

**Success Criteria:**

- Zero-config revocation for new issuers using default profiles
- Format-agnostic revocation checking in verification
- <100ms overhead for cached status list checks
- Offline operation for 24+ hours with grace period

**Timeline Estimate:** 2-3 weeks for Phase 1 implementation
