# DEVS Tier Subscription - Key Vault Access

## Overview

The **DEVS** tier is a special subscription level designed for developers that provides access to the service provider's key vault for cryptographic signing operations. This tier includes automatic biweekly key rotation to prevent permanent adoption at this level.

## Subscription Tiers Comparison

| Tier | Service Key Vault | Remote Signing | Key Rotation | API Calls/Month | API Keys |
|------|------------------|----------------|--------------|-----------------|----------|
| **FREE** | ❌ | ✅ Required | N/A | 1,000 | 2 |
| **DEVS** | ✅ Allowed | ❌ Not required | Every 14 days | 10,000 | 5 |
| **STARTER** | ❌ | ✅ Required | N/A | 50,000 | 10 |
| **PROFESSIONAL** | ❌ | ✅ Required | N/A | 500,000 | 50 |
| **ENTERPRISE** | ❌ | ✅ Required | N/A | Unlimited | Unlimited |

## DEVS Tier Features

### ✅ What You Get
- Access to service-managed key vault (HashiCorp Vault)
- Automatic key generation and management
- No need to set up your own KMS/HSM
- 10,000 API calls per month
- Up to 5 API keys
- 3 webhook endpoints

### ⚠️ Limitations
- **Mandatory key rotation every 14 days**
- Keys are service-managed (you don't control the vault)
- Not suitable for production workloads
- Signing operations will fail if rotation is overdue

### 🎯 Use Cases
- Development and testing
- Proof-of-concept implementations
- Learning the API
- Integration testing
- Sandbox environments

## Getting Started

### 1. Subscribe to DEVS Tier

```bash
# Create subscription via API
curl -X POST https://api.marty.example.com/v1/subscriptions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "plan": "devs",
    "card_id": null
  }'
```

### 2. Initialize Signing Service

```python
from marty_backend_common.infrastructure.key_vault import (
    build_key_vault_client,
    KeyVaultConfig
)
from src.subscription.signing_service import SigningService

# Service vault configuration (provided by platform)
vault_config = KeyVaultConfig(
    provider="vault",
    vault_addr=os.getenv("VAULT_ADDR"),
    vault_auth_method="token",
)
service_vault = build_key_vault_client(vault_config)

# Initialize signing service
signing_service = SigningService(
    db=db_session,
    service_key_vault=service_vault,
)
```

### 3. Create a Signing Key

```python
# Ensure signing key exists
key_info = await signing_service.ensure_signing_key(
    organization=your_org,
    key_id="my-app-key",
    algorithm="ecdsa-p256",  # or "rsa2048", "ed25519"
)

print(f"Key created: {key_info.key_id}")
print(f"Rotation required: {key_info.rotation_required}")
print(f"Last rotated: {key_info.last_rotated_at}")
```

### 4. Sign Data

```python
# Sign payload
payload = b"data to sign"

try:
    signature = await signing_service.sign(
        organization=your_org,
        key_id="my-app-key",
        payload=payload,
        algorithm="ecdsa-p256",
    )
    
    print(f"Signature: {signature.hex()}")
    
except KeyRotationRequired as e:
    print(f"Key rotation required: {e}")
    # Rotate the key
    new_key = await signing_service.rotate_key(
        organization=your_org,
        key_id="my-app-key",
    )
    print(f"Key rotated. New key ID: {new_key.key_id}")
```

## Key Rotation

### Automatic Rotation Schedule
- **Frequency**: Every 14 days
- **Grace Period**: None (signing blocked immediately after 14 days)
- **Notification**: `KeyRotationRequired` exception raised

### Checking Rotation Status

```python
# Get key information
key_info = await signing_service.get_key_info(
    organization=your_org,
    key_id="my-app-key",
)

if key_info.rotation_required:
    days_since_rotation = (
        datetime.now(timezone.utc) - key_info.last_rotated_at
    ).days
    print(f"⚠️  Key rotation required! ({days_since_rotation} days old)")
else:
    print("✅ Key is up to date")
```

### Manual Key Rotation

```python
# Rotate key before the deadline
new_key = await signing_service.rotate_key(
    organization=your_org,
    key_id="my-app-key",
    algorithm="ecdsa-p256",
)

print(f"Old key: org-{your_org.id}-my-app-key")
print(f"New key: {new_key.key_id}")
```

### Rotation Best Practices

1. **Monitor rotation status** in your application dashboard
2. **Set up alerts** for keys approaching rotation deadline
3. **Rotate during low-traffic periods** to minimize disruption
4. **Update key references** in your application after rotation
5. **Test rotation workflow** in development environment

## Migration Paths

### From DEVS to Production Tier

When you're ready for production, upgrade to STARTER or higher tier:

1. **Set up your own key vault** (AWS KMS, Azure Key Vault, etc.)
2. **Generate keys** in your vault
3. **Configure remote signing** endpoint
4. **Upgrade subscription** to STARTER/PROFESSIONAL/ENTERPRISE
5. **Update application** to use remote signing

```python
# Before (DEVS tier)
signature = await signing_service.sign(
    organization=your_org,
    key_id="my-app-key",
    payload=payload,
)

# After (Production tier with remote signing)
# Configure your own KeyVaultClient pointing to your KMS
your_vault = build_key_vault_client(KeyVaultConfig(
    provider="aws_kms",
    # Your KMS configuration
))

signature = await your_vault.sign(
    key_id="your-kms-key-id",
    payload=payload,
    algorithm="ecdsa-p256",
)
```

## Error Handling

### Common Exceptions

```python
from src.subscription.signing_service import (
    KeyRotationRequired,
    RemoteSigningRequired,
    UnauthorizedKeyVaultAccess,
    SigningError,
)

try:
    signature = await signing_service.sign(
        organization=your_org,
        key_id="my-app-key",
        payload=payload,
    )
    
except KeyRotationRequired as e:
    # Key is older than 14 days
    logger.warning(f"Key rotation required: {e}")
    # Trigger rotation workflow
    await rotate_key_workflow(your_org, "my-app-key")
    
except RemoteSigningRequired as e:
    # Tier doesn't allow service key vault
    logger.error(f"Remote signing required: {e}")
    # Guide user to upgrade and configure their own vault
    
except UnauthorizedKeyVaultAccess as e:
    # Permission denied
    logger.error(f"Unauthorized access: {e}")
    # Check subscription status
    
except SigningError as e:
    # General signing error
    logger.error(f"Signing failed: {e}")
```

### Handling Rotation in Production Code

```python
async def sign_with_auto_rotation(
    signing_service: SigningService,
    organization: Organization,
    key_id: str,
    payload: bytes,
    max_retries: int = 1,
) -> bytes:
    """
    Sign payload with automatic rotation retry.
    
    If signing fails due to rotation requirement, automatically
    rotates the key and retries the operation.
    """
    for attempt in range(max_retries + 1):
        try:
            return await signing_service.sign(
                organization=organization,
                key_id=key_id,
                payload=payload,
            )
        except KeyRotationRequired:
            if attempt < max_retries:
                logger.info(f"Rotating key {key_id} for {organization.id}")
                await signing_service.rotate_key(
                    organization=organization,
                    key_id=key_id,
                )
            else:
                raise
    
    raise SigningError("Failed to sign after rotation")

# Usage
signature = await sign_with_auto_rotation(
    signing_service,
    your_org,
    "my-app-key",
    payload,
)
```

## API Integration

### REST API Endpoints

```bash
# Get signing key info
GET /v1/signing/keys/{key_id}

# Create signing key
POST /v1/signing/keys
{
  "key_id": "my-app-key",
  "algorithm": "ecdsa-p256"
}

# Rotate signing key
POST /v1/signing/keys/{key_id}/rotate

# Sign payload
POST /v1/signing/sign
{
  "key_id": "my-app-key",
  "payload": "base64-encoded-data",
  "algorithm": "ecdsa-p256"
}
```

### Example: FastAPI Integration

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/signing", tags=["signing"])

class SignRequest(BaseModel):
    key_id: str
    payload: bytes
    algorithm: str = "ecdsa-p256"

@router.post("/sign")
async def sign_payload(
    request: SignRequest,
    org: Organization = Depends(get_current_organization),
    signing_service: SigningService = Depends(get_signing_service),
):
    """Sign payload using organization's key."""
    try:
        signature = await signing_service.sign(
            organization=org,
            key_id=request.key_id,
            payload=request.payload,
            algorithm=request.algorithm,
        )
        
        return {
            "signature": signature.hex(),
            "algorithm": request.algorithm,
        }
        
    except KeyRotationRequired as e:
        raise HTTPException(
            status_code=428,  # Precondition Required
            detail={
                "error": "key_rotation_required",
                "message": str(e),
                "action": "rotate_key",
            }
        )
```

## Monitoring and Alerts

### Key Metrics to Track

```python
# Example monitoring integration
from prometheus_client import Counter, Histogram

signing_operations = Counter(
    "signing_operations_total",
    "Total signing operations",
    ["organization", "status"]
)

rotation_operations = Counter(
    "key_rotations_total",
    "Total key rotations",
    ["organization"]
)

key_age_days = Histogram(
    "signing_key_age_days",
    "Age of signing keys in days",
    ["organization"]
)

# In your signing code
def track_signing_metrics(org: Organization, success: bool):
    status = "success" if success else "failure"
    signing_operations.labels(
        organization=org.slug,
        status=status
    ).inc()

# In your rotation code
def track_rotation_metrics(org: Organization):
    rotation_operations.labels(
        organization=org.slug
    ).inc()
```

### Alert Rules

```yaml
# alerts.yaml
groups:
  - name: signing_service
    rules:
      - alert: KeyRotationOverdue
        expr: signing_key_age_days > 14
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Key rotation overdue for {{ $labels.organization }}"
          description: "Signing key is {{ $value }} days old (limit: 14 days)"
      
      - alert: HighSigningFailureRate
        expr: rate(signing_operations_total{status="failure"}[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High signing failure rate for {{ $labels.organization }}"
```

## FAQ

### Q: Can I extend the 14-day rotation period?
**A:** No, the biweekly rotation is enforced for all DEVS tier subscriptions. This is intentional to prevent using DEVS tier for production workloads. Upgrade to a production tier for longer key lifecycles.

### Q: What happens to my signatures after key rotation?
**A:** Old signatures remain valid. Key rotation only affects new signing operations. You should keep a record of which key version signed which data for verification purposes.

### Q: Can I export the private keys?
**A:** No, private keys never leave the service key vault. This is a security feature of the DEVS tier. If you need key export, use a production tier with your own key vault.

### Q: How do I migrate from DEVS to production?
**A:** See the "Migration Paths" section above. You'll need to set up your own key vault and upgrade your subscription tier.

### Q: Can I have multiple keys per organization?
**A:** Yes, you can create multiple signing keys by using different `key_id` values. Each key has its own rotation schedule.

### Q: Is DEVS tier suitable for production?
**A:** No, DEVS tier is designed for development and testing only. Production workloads should use STARTER, PROFESSIONAL, or ENTERPRISE tiers with remote signing.

## Support

For questions or issues:
- 📧 Email: support@marty.example.com
- 💬 Discord: https://discord.gg/marty-dev
- 📚 Documentation: https://docs.marty.example.com
- 🐛 GitHub Issues: https://github.com/marty/issues
