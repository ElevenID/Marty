# RevocationProfile Quick Reference

## For Developers: Using RevocationProfiles

### Quick Start

**1. Use the default profile (zero configuration)**
```json
{
  "revocation_profile_id": null
}
```
When `null`, the Issuance service automatically uses the system default profile with full automation enabled.

**2. Create your own profile**
```bash
curl -X POST http://localhost:8013/v1/revocation-profiles \
  -H "Content-Type: application/json" \
  -d '{
    "organization_id": "org-123",
    "name": "Production Revocation",
    "status": "active",
    "supported_formats": ["sd_jwt_vc", "mdoc"],
    "issuer_config": {
      "status_list_strategy": "auto",
      "update_mode": "sync"
    },
    "verifier_config": {
      "check_mode": "hard_fail"
    },
    "automation_config": {
      "auto_allocate_indices": true,
      "auto_publish": true
    }
  }'
```

**3. Link to Application Template**
```json
{
  "organization_id": "org-123",
  "name": "Employee Badge",
  "credential_template_ids": ["template-456"],
  "trust_profile_id": "trust-789",
  "compliance_profile_id": "compliance-012",
  "revocation_profile_id": "profile-abc"
}
```

**4. Revoke credentials (API unchanged)**
```bash
curl -X POST http://localhost:8005/v1/issuance/credentials/cred-123/revoke \
  -H "Content-Type: application/json" \
  -d '{"reason": "User terminated"}'
```

The Issuance service automatically:
- Looks up the Application Template
- Finds the revocation_profile_id
- Delegates to RevocationProfile service
- Updates the status list
- Returns success

## Configuration Options

### Issuer Config (How credentials are revoked)

```typescript
{
  // Status list management strategy
  "status_list_strategy": "auto" | "manual" | "registry",
  
  // Update processing mode
  "update_mode": "sync" | "async" | "batch",
  
  // For batch mode: how often to process updates
  "batch_interval_seconds": 300,
  
  // Status list rotation
  "enable_rotation": true,
  "rotation_threshold_percent": 80,
  
  // Format support
  "enable_bitstring_status_list": true,  // SD-JWT, W3C VC
  "enable_token_status_list": true,      // mDoc
  "enable_legacy_revocation_list": false
}
```

**Recommendations**:
- Development: `update_mode: "sync"` (immediate)
- Production: `update_mode: "async"` (better performance)
- High volume: `update_mode: "batch"` (efficient)

### Verifier Config (How revocation is checked)

```typescript
{
  // How strict to be about revocation checks
  "check_mode": "hard_fail" | "soft_fail" | "skip",
  
  // Which mechanisms to try (in order)
  "mechanism_priority": ["status_list", "ocsp", "crl"],
  
  // Performance optimization
  "cache_status_lists": true,
  "cache_duration_seconds": 3600,
  
  // Offline grace period
  "offline_grace_period_seconds": 86400,
  
  // Timeouts and retries
  "check_timeout_seconds": 5,
  "max_retries": 2
}
```

**Recommendations**:
- High security: `check_mode: "hard_fail"`
- Mobile/offline: `check_mode: "soft_fail"` with long grace period
- Development: `check_mode: "skip"` (testing)

### Automation Config (What happens automatically)

```typescript
{
  // Automatically assign status list indices to new credentials
  "auto_allocate_indices": true,
  
  // Automatically publish updated status lists
  "auto_publish": true,
  
  // Automatically create status list credentials
  "auto_generate_status_list_credentials": true,
  
  // Use format-specific defaults
  "use_format_defaults": true
}
```

**Recommendations**:
- Start with all `true` (fully automated)
- Disable for custom workflows
- Enterprise: Consider `auto_publish: false` for manual control

## Common Patterns

### Pattern 1: Zero Config (Use Default)
```json
{
  "revocation_profile_id": null
}
```
Best for: Development, prototyping, simple use cases

### Pattern 2: High Security
```json
{
  "issuer_config": {
    "status_list_strategy": "auto",
    "update_mode": "sync",
    "enable_rotation": true
  },
  "verifier_config": {
    "check_mode": "hard_fail",
    "cache_status_lists": false,
    "require_issuer_signature_on_status_list": true
  }
}
```
Best for: Financial credentials, high-value transactions

### Pattern 3: High Performance
```json
{
  "issuer_config": {
    "status_list_strategy": "auto",
    "update_mode": "async",
    "batch_interval_seconds": 60
  },
  "verifier_config": {
    "check_mode": "soft_fail",
    "cache_status_lists": true,
    "cache_duration_seconds": 300
  }
}
```
Best for: High-volume issuance, frequent revocations

### Pattern 4: Offline-Friendly
```json
{
  "verifier_config": {
    "check_mode": "soft_fail",
    "cache_status_lists": true,
    "cache_duration_seconds": 3600,
    "offline_grace_period_seconds": 604800
  }
}
```
Best for: Mobile wallets, intermittent connectivity

### Pattern 5: Manual Control
```json
{
  "issuer_config": {
    "status_list_strategy": "manual",
    "update_mode": "sync"
  },
  "automation_config": {
    "auto_allocate_indices": false,
    "auto_publish": false
  }
}
```
Best for: Custom workflows, regulatory requirements

## API Reference

### Public Endpoints (Admin)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/revocation-profiles` | POST | Create profile |
| `/v1/revocation-profiles?organization_id=X` | GET | List profiles |
| `/v1/revocation-profiles/{id}` | GET | Get profile |
| `/v1/revocation-profiles/{id}/activate` | POST | Activate profile |
| `/v1/revocation-profiles/{id}` | DELETE | Delete profile |

### Internal Endpoints (Service-to-Service)

| Endpoint | Purpose | Caller |
|----------|---------|--------|
| `/internal/revocation-profiles/{id}/process-revocation` | Handle revoke/suspend/reinstate | Issuance |
| `/internal/revocation-profiles/{id}/allocate-index` | Allocate status list index | Issuance |

**Note**: Internal endpoints are NOT exposed in the gateway (security by design).

## Troubleshooting

### Problem: Profile not found
**Symptom**: "RevocationProfile not found" error  
**Solution**: Check profile ID in Application Template, ensure profile exists

### Problem: Revocation fails silently
**Symptom**: Credential status updates but no status list change  
**Solution**: Phase 2 implementation required (Status List Manager integration)

### Problem: Delegation timeout
**Symptom**: 503 error from Issuance service  
**Solution**: Check RevocationProfile service health, restart if needed

### Problem: Wrong mechanism used
**Symptom**: BitstringStatusList used for mDoc  
**Solution**: Update profile's `supported_formats` to include `"mdoc"`

## Migration Guide

### Migrating from inline revocation_policy

**Step 1: Create RevocationProfile**
```bash
curl -X POST /v1/revocation-profiles -d '{
  "organization_id": "org-123",
  "name": "Migrated Profile",
  "issuer_config": {
    "status_list_strategy": "auto",  # From revocation_policy
    "update_mode": "sync"
  },
  "verifier_config": {
    "check_mode": "hard_fail"  # From revocation_policy
  }
}'
```

**Step 2: Update Trust Profile**
```bash
curl -X PATCH /v1/trust-profiles/{id} -d '{
  "revocation_profile_id": "profile-abc"
}'
```

**Step 3: Test**
```bash
curl -X POST /v1/issuance/credentials/{id}/revoke -d '{
  "reason": "Test migration"
}'
```

**Step 4: Verify delegation works**
Check logs for "Delegating to RevocationProfile service"

**Step 5: Remove inline revocation_policy (Phase 3)**
Wait until all profiles migrated, then deprecate field

## Environment Variables

### RevocationProfile Service
```bash
REVOCATION_PROFILE_SERVICE_PORT=8013
```

### Issuance Service
```bash
ISSUANCE_SERVICE_PORT=8005
REVOCATION_PROFILE_SERVICE_URL=http://localhost:8013
```

### Gateway
```bash
GATEWAY_PORT=8000
REVOCATION_PROFILE_SERVICE_URL=http://localhost:8013
```

## Testing

### Unit Test Example
```python
import httpx

async def test_create_profile():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8013/v1/revocation-profiles",
            json={
                "organization_id": "test",
                "name": "Test Profile",
                "status": "draft",
            }
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Test Profile"
```

### Integration Test Example
```python
async def test_revocation_delegation():
    # Create profile
    profile = await create_revocation_profile(...)
    
    # Create application template with profile
    template = await create_application_template(
        revocation_profile_id=profile["id"]
    )
    
    # Issue credential
    credential = await issue_credential(template_id=template["id"])
    
    # Revoke credential (triggers delegation)
    result = await revoke_credential(credential["id"])
    
    assert result["status"] == "revoked"
```

## Performance Tips

1. **Enable Caching**: Set `cache_status_lists: true` for better performance
2. **Use Async Mode**: For high-volume, use `update_mode: "async"`
3. **Batch Updates**: Consider `update_mode: "batch"` for bulk operations
4. **Monitor Latency**: Track delegation time to RevocationProfile service
5. **Scale Horizontally**: Phase 2 will support multiple instances

## Security Best Practices

1. **Restrict Admin API**: Only allow authenticated admins to create/modify profiles
2. **Audit Changes**: Log all profile modifications
3. **Validate Input**: Don't trust client-provided profile configurations
4. **Rate Limit**: Protect against abuse of revocation endpoints
5. **Monitor Anomalies**: Alert on unusual revocation patterns

## FAQ

**Q: Can I use different profiles for different credential types?**  
A: Yes! Link different profiles to different Application Templates.

**Q: What happens if RevocationProfile service is down?**  
A: Graceful degradation: local credential status updates still succeed, status list update retried later.

**Q: Can I change a profile after credentials are issued?**  
A: Yes, but be careful: changes affect all future revocations for credentials using that profile.

**Q: How do I revoke many credentials at once?**  
A: Use `update_mode: "batch"` in the profile, then call revoke for each credential. They'll be batched automatically.

**Q: Can I use my own status list server?**  
A: Yes! Set `status_list_strategy: "registry"` and provide `status_list_base_url`.

---

**Need help?** Check the full documentation in:
- `RevocationProfile_Proposal.md` - Architecture and design
- `RevocationProfile_Implementation_Summary.md` - Implementation details
- `RevocationProfile_Integration_Architecture.md` - Integration flows
- `RevocationProfile_Verification_Report.md` - Test results
