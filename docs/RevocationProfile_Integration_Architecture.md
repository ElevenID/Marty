# RevocationProfile Integration Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Gateway (8000)                           │
│  Public API: /v1/revocation-profiles (CRUD for admins)         │
│  Public API: /v1/issuance/credentials/{id}/revoke (unchanged)  │
└─────────────┬───────────────────────────────────┬───────────────┘
              │                                   │
              │ Proxy                             │ Proxy
              ▼                                   ▼
┌─────────────────────────┐         ┌─────────────────────────────┐
│ RevocationProfile (8013)│         │    Issuance (8005)          │
│  - Public: CRUD         │◄────────┤  - Credential lifecycle     │
│  - Internal: process    │ Delegate│  - Looks up profile_id      │
│  - Internal: allocate   │         │  - Delegates to             │
│                         │         │    RevocationProfile        │
└─────────────────────────┘         └─────────────────────────────┘
              │                                   │
              │ Format detection                  │ Template lookup
              ▼                                   ▼
┌─────────────────────────┐         ┌─────────────────────────────┐
│ Status List Manager     │         │ Application Template        │
│  - TokenStatusList      │         │  - revocation_profile_id    │
│  - BitstringStatusList  │         │  - Links to profile         │
│  - StatusList2021       │         └─────────────────────────────┘
└─────────────────────────┘                       │
                                                  │ References
                                                  ▼
                                    ┌─────────────────────────────┐
                                    │    Trust Profile (8004)     │
                                    │  - revocation_profile_id    │
                                    │  - revocation_policy (old)  │
                                    └─────────────────────────────┘
```

## Request Flow: Revoke Credential

### External Request (User/Client)
```http
POST /v1/issuance/credentials/cred123/revoke HTTP/1.1
Host: api.marty.dev
Content-Type: application/json

{
  "reason": "Employee terminated"
}
```

### Step-by-Step Flow

1. **Gateway receives request**
   - Route: `/v1/issuance` → Issuance service (8005)
   - Proxies to: `http://localhost:8005/v1/issuance/credentials/cred123/revoke`

2. **Issuance service processes**
   ```python
   async def revoke_credential(credential_id, request):
       # Get credential from repository
       cred = await repo.get_credential(credential_id)
       
       # Get application template to find profile
       template_id = cred.credential_template_id
       template = _templates.get(template_id)
       revocation_profile_id = template.get("revocation_profile_id", "default")
       
       # Delegate to RevocationProfile service
       await _delegate_to_revocation_profile(
           credential_id=credential_id,
           action="revoke",
           reason=request.reason,
       )
       
       # Update local state
       cred.status = CredentialStatus.REVOKED
       await repo.save_credential(cred)
   ```

3. **Delegation to RevocationProfile**
   ```python
   async def _delegate_to_revocation_profile(credential_id, action, reason):
       async with httpx.AsyncClient() as client:
           response = await client.post(
               f"http://localhost:8013/internal/revocation-profiles/{profile_id}/process-revocation",
               json={
                   "credential_id": credential_id,
                   "action": action,  # "revoke", "suspend", "reinstate"
                   "credential_format": "sd_jwt",  # Detected from credential
                   "status_list_index": 42,  # From credential
                   "reason": reason,
               }
           )
           return response.json()
   ```

4. **RevocationProfile processes**
   ```python
   @router.post("/internal/revocation-profiles/{profile_id}/process-revocation")
   async def process_revocation(profile_id: str, request: ProcessRevocationRequest):
       profile = await repo.get_profile(profile_id)
       
       # Determine format-specific handling
       if request.credential_format == "sd_jwt":
           mechanism = RevocationMechanism.BITSTRING_STATUS_LIST
       elif request.credential_format == "mdoc":
           mechanism = RevocationMechanism.TOKEN_STATUS_LIST
       
       # Apply automation config
       if profile.automation_config.sync_updates:
           # Update immediately
           await update_status_list(request.status_list_index, action)
       else:
           # Queue for batch processing
           await queue_revocation(request)
       
       if profile.automation_config.auto_publish:
           # Publish updated status list
           await publish_status_list(credential_format)
       
       return {"success": True, "mechanism": mechanism}
   ```

5. **Response to client**
   ```json
   {
     "id": "cred123",
     "status": "revoked",
     "status_updated_at": "2024-01-15T10:30:00Z",
     "reason": "Employee terminated"
   }
   ```

## Request Flow: Create Revocation Profile

### External Request (Admin)
```http
POST /v1/revocation-profiles HTTP/1.1
Host: api.marty.dev
Content-Type: application/json

{
  "name": "Enterprise Revocation",
  "status": "active",
  "issuer_config": {
    "status_list_strategy": "AUTO",
    "update_mode": "SYNC"
  },
  "verifier_config": {
    "check_mode": "HARD_FAIL"
  },
  "automation_config": {
    "auto_allocate_indices": true,
    "auto_publish": true
  }
}
```

### Flow

1. **Gateway proxies to RevocationProfile service**
   - Route: `/v1/revocation-profiles` → RevocationProfile (8013)
   - Proxies to: `http://localhost:8013/v1/revocation-profiles`

2. **RevocationProfile service creates profile**
   ```python
   @router.post("")
   async def create_revocation_profile(request: RevocationProfileCreate):
       profile = RevocationProfile(
           name=request.name,
           status=RevocationProfileStatus(request.status),
           issuer_config=IssuerRevocationConfig(**request.issuer_config),
           verifier_config=VerifierRevocationConfig(**request.verifier_config),
           automation_config=RevocationAutomationConfig(**request.automation_config),
       )
       await repo.save_profile(profile)
       return profile
   ```

3. **Response to admin**
   ```json
   {
     "id": "profile-123",
     "name": "Enterprise Revocation",
     "status": "active",
     "issuer_config": {...},
     "verifier_config": {...},
     "automation_config": {...},
     "created_at": "2024-01-15T10:00:00Z"
   }
   ```

## Data Model Integration

### Application Template Links to RevocationProfile

```json
{
  "id": "template-456",
  "name": "Employee Badge",
  "organization_id": "org-123",
  "credential_template_ids": ["cred-template-789"],
  "trust_profile_id": "trust-012",
  "compliance_profile_id": "compliance-345",
  "revocation_profile_id": "profile-123",  // NEW
  "created_at": "2024-01-15T09:00:00Z"
}
```

### Trust Profile Links to RevocationProfile

```json
{
  "id": "trust-012",
  "name": "Enterprise Trust",
  "organization_id": "org-123",
  "trust_sources": [...],
  "validation_rules": {...},
  "revocation_policy": {...},  // DEPRECATED
  "revocation_profile_id": "profile-123",  // NEW
  "time_policy": {...},
  "created_at": "2024-01-15T08:00:00Z"
}
```

## Service Communication Matrix

| From Service       | To Service         | Endpoint                                   | Auth   | Purpose                          |
|--------------------|--------------------|--------------------------------------------|--------|----------------------------------|
| Gateway            | RevocationProfile  | `/v1/revocation-profiles/*`                | Public | Admin CRUD operations            |
| Gateway            | Issuance           | `/v1/issuance/credentials/{id}/revoke`     | Public | Credential lifecycle             |
| Issuance           | RevocationProfile  | `/internal/revocation-profiles/{id}/...`   | Internal | Delegation for revocation       |
| RevocationProfile  | Status List Mgr    | (future) `/update-status-list`             | Internal | Update status lists              |

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
ISSUANCE_SERVICE_URL=http://localhost:8005
```

## Error Handling

### Graceful Degradation

If RevocationProfile service is unavailable:

```python
try:
    result = await _delegate_to_revocation_profile(...)
except httpx.HTTPError as e:
    logger.warning("RevocationProfile service unavailable, using local revocation")
    result = None

# Local update still happens
cred.status = CredentialStatus.REVOKED
await repo.save_credential(cred)
```

This ensures the credential is marked as revoked locally even if the RevocationProfile service is down. The status list update can be retried later.

## Security Considerations

### Internal Endpoints

Internal endpoints (`/internal/revocation-profiles/*`) should:
- NOT be exposed in gateway routing
- Use service-to-service authentication (future: mutual TLS, API keys)
- Only be accessible from trusted services

### Access Control

Public endpoints (`/v1/revocation-profiles`) should:
- Require admin authentication
- Enforce organization-level permissions
- Audit all profile changes

## Monitoring & Observability

### Key Metrics

1. **RevocationProfile Service**:
   - Profiles created/activated/deleted
   - Process-revocation calls (count, latency)
   - Index allocation calls
   - Status list updates (success/failure)

2. **Issuance Service**:
   - Revocation requests (by reason)
   - Delegation success/failure rate
   - Fallback activations

3. **Gateway**:
   - RevocationProfile endpoint usage
   - Proxy latency to backend services

### Logging

Each service logs:
- Request/response for delegation calls
- Profile lookups and cache hits
- Status list update operations
- Error conditions and fallbacks

## Deployment

### Docker Compose

```yaml
services:
  revocation-profile:
    build: ./services/revocation-profile
    ports:
      - "8013:8013"
    environment:
      - SERVICE_PORT=8013
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8013/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  issuance:
    build: ./services/issuance
    ports:
      - "8005:8005"
    environment:
      - SERVICE_PORT=8005
      - REVOCATION_PROFILE_SERVICE_URL=http://revocation-profile:8013
    depends_on:
      - revocation-profile

  gateway:
    build: ./services/gateway
    ports:
      - "8000:8000"
    environment:
      - GATEWAY_PORT=8000
      - REVOCATION_PROFILE_SERVICE_URL=http://revocation-profile:8013
      - ISSUANCE_SERVICE_URL=http://issuance:8005
    depends_on:
      - revocation-profile
      - issuance
```

## Future Enhancements

### Phase 2: Status List Integration

```python
# In RevocationProfile service
async def process_revocation(profile_id, request):
    profile = await repo.get_profile(profile_id)
    
    # Call Status List Manager
    async with httpx.AsyncClient() as client:
        await client.post(
            "http://status-list-manager:8014/update",
            json={
                "format": request.credential_format,
                "index": request.status_list_index,
                "status": "revoked",
                "publish": profile.automation_config.auto_publish,
            }
        )
```

### Phase 3: Async Queue

```python
# In RevocationProfile service
if profile.issuer_config.update_mode == UpdateMode.ASYNC_QUEUE:
    # Enqueue for batch processing
    await redis_queue.lpush(
        f"revocations:{credential_format}",
        json.dumps({
            "credential_id": request.credential_id,
            "index": request.status_list_index,
            "action": request.action,
            "timestamp": datetime.utcnow().isoformat(),
        })
    )
```

## Conclusion

The RevocationProfile integration successfully decouples revocation concerns from credential issuance while maintaining backward compatibility. The hybrid delegation pattern allows seamless evolution without breaking changes to external APIs.
