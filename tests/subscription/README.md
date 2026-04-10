# Tier-Based Signing Tests

This test suite verifies the subscription tier-based key vault access control and signing functionality.

## Overview

The subscription system has different tiers with different key management capabilities:

### FREE Tier
- **Can use service key vault**: Yes
- **Service manages keys**: Yes
- **Key rotation**: Weekly (every 7 days)
- **Private key access**: Service only (never exposed to customer)

### DEVS Tier
- **Can use service key vault**: Yes
- **Service manages keys**: Yes
- **Key rotation**: Biweekly (every 14 days)
- **Private key access**: Service only (never exposed to customer)

### Other Tiers (STARTER, PROFESSIONAL, ENTERPRISE)
- **Can use service key vault**: No
- **Remote signing required**: Yes
- **Key vault**: Customer must provide their own (AWS KMS, Azure Key Vault, etc.)
- **Private key access**: Customer only (service never sees private keys)

## Test Coverage

### 1. DEVS Tier Key Vault Access (`TestDevsKeyVaultAccess`)
- ✅ DEVS tier can create keys in service key vault
- ✅ DEVS tier can sign data using service keys
- ✅ Keys are scoped per organization
- ✅ Multiple organizations have isolated keys

### 2. FREE Tier Key Vault Access (`TestFreeTierKeyVaultAccess`)
- ✅ FREE tier can create keys in service key vault
- ✅ FREE tier keys require rotation after 7 days (weekly)
- ✅ Signing blocked when rotation overdue

### 3. Remote Signing Enforcement (`TestRemoteSigningEnforcement`)
- ✅ STARTER tier cannot use service key vault
- ✅ PROFESSIONAL tier cannot use service key vault
- ✅ ENTERPRISE tier cannot use service key vault
- ✅ Production tiers cannot perform signing operations
- ✅ Clear error messages guide users to remote signing

### 3. Biweekly Key Rotation (`TestBiweeklyKeyRotation`)
- ✅ New keys don't require immediate rotation
- ✅ Keys require rotation after 14 days (DEVS tier)
- ✅ Signing blocked when rotation is overdue
- ✅ Key rotation creates new key version
- ✅ Rotation timer resets after rotation
- ✅ Signing works normally after rotation
- ✅ Production tiers have no rotation requirements

### 4. Access Control Logic (`TestKeyVaultAccessControl`)
- ✅ FREE and DEVS plan limits configured correctly
- ✅ Production tiers require remote signing
- ✅ Graceful handling of missing subscriptions

## Running Tests

### Using Make (Recommended)
```bash
# Run all Python tests with proper environment
make pytest
```

### Using Docker Compose
```bash
# Start test dependencies
docker-compose --profile pytest up -d postgres-pytest redis-pytest

# Run specific test file
docker-compose --profile pytest run pytest-runner \
    pytest tests/subscription/test_tier_based_signing.py -v

# Run specific test class
docker-compose --profile pytest run pytest-runner \
    pytest tests/subscription/test_tier_based_signing.py::TestDevsKeyVaultAccess -v

# Run specific test
docker-compose --profile pytest run pytest-runner \
    pytest tests/subscription/test_tier_based_signing.py::TestBiweeklyKeyRotation::test_key_requires_rotation_after_14_days -v
```

### Using pytest directly (if environment is set up)
```bash
# All tests
pytest tests/subscription/test_tier_based_signing.py -v

# Specific test class
pytest tests/subscription/test_tier_based_signing.py::TestRemoteSigningEnforcement -v

# With coverage
pytest tests/subscription/test_tier_based_signing.py --cov=src.subscription.signing_service --cov-report=html
```

## Test Structure

Each test follows this pattern:

1. **Setup**: Create mock organization and subscription
2. **Exercise**: Call the signing service method
3. **Verify**: Assert expected behavior (success or specific exception)
4. **Cleanup**: Handled automatically by pytest fixtures

## Key Test Patterns

### Testing Access Control
```python
@pytest.mark.asyncio
async def test_tier_requires_remote_signing(
    mock_db_session,
    mock_key_vault,
    organization,
    subscription,
):
    service = SigningService(mock_db_session, mock_key_vault)
    
    with pytest.raises(RemoteSigningRequired):
        await service.ensure_signing_key(organization, "test-key")
    
    # Verify service vault was never accessed
    mock_key_vault.ensure_key.assert_not_called()
```

### Testing Key Rotation
```python
@pytest.mark.asyncio
async def test_rotation_enforcement(
    mock_db_session,
    mock_key_vault,
    devs_organization,
    devs_subscription,
):
    service = SigningService(mock_db_session, mock_key_vault)
    
    # Create key
    await service.ensure_signing_key(devs_organization, "test-key")
    
    # Simulate 15 days passing
    org_key_id = f"org-{devs_organization.id}-test-key"
    service._key_rotation_tracker[org_key_id] = (
        datetime.now(timezone.utc) - timedelta(days=15)
    )
    
    # Signing should fail
    with pytest.raises(KeyRotationRequired):
        await service.sign(devs_organization, "test-key", b"payload")
```

## Integration with Production Code

### Service Initialization
```python
from marty_backend_common.infrastructure.key_vault import build_key_vault_client, KeyVaultConfig
from src.subscription.signing_service import SigningService

# Initialize service key vault (for DEVS tier)
vault_config = KeyVaultConfig(
    provider="vault",
    vault_addr="https://vault.example.com",
    vault_auth_method="kubernetes",
)
service_vault = build_key_vault_client(vault_config)

# Initialize signing service
signing_service = SigningService(
    db=db_session,
    service_key_vault=service_vault,
)
```

### Using the Service
```python
# DEVS tier organization
try:
    # Ensure signing key exists
    key_info = await signing_service.ensure_signing_key(
        organization=devs_org,
        key_id="credential-signing",
        algorithm="ecdsa-p256",
    )
    
    # Check if rotation is needed
    if key_info.rotation_required:
        logger.warning(f"Key rotation required for {devs_org.id}")
        key_info = await signing_service.rotate_key(
            organization=devs_org,
            key_id="credential-signing",
        )
    
    # Sign credential
    credential_payload = b"credential data"
    signature = await signing_service.sign(
        organization=devs_org,
        key_id="credential-signing",
        payload=credential_payload,
    )
    
except KeyRotationRequired as e:
    logger.error(f"Key rotation overdue: {e}")
    # Trigger rotation workflow
    
except RemoteSigningRequired as e:
    logger.info(f"Tier requires remote signing: {e}")
    # Guide user to configure their own key vault
```

## Security Considerations

### DEVS Tier
- Keys stored in service-controlled HashiCorp Vault
- Biweekly rotation prevents long-term key compromise
- Keys never exported from vault (remote signing in vault)
- Per-organization key isolation

### Other Tiers
- Service never has access to private keys
- Customers control their own key lifecycle
- Remote signing enforced at API level
- Support for major KMS providers (AWS KMS, Azure Key Vault, GCP KMS)

## Future Enhancements

### Planned Features
- [ ] Persistent key rotation tracking (database-backed)
- [ ] Automated rotation reminders (webhooks/email)
- [ ] Key usage metrics and monitoring
- [ ] Support for multiple algorithms per organization
- [ ] Key archival and history
- [ ] Grace period for rotation (warn before blocking)

### Configuration Options
- [ ] Configurable rotation period per organization
- [ ] Custom rotation policies
- [ ] Emergency key recovery procedures

## Troubleshooting

### Test Failures

**Test fails with "No module named 'marty_backend_common'"**
- Ensure Python path includes the packages directory
- Run tests with proper Docker Compose profile

**Test fails with "Service key vault not configured"**
- Verify `service_key_vault` is provided to `SigningService` in tests
- Check fixture setup in test file

**Test fails with "No active subscription found"**
- Ensure subscription fixture is properly linked to organization
- Verify mock database session returns the subscription

### Common Issues

**Keys not rotating**
- Check system time is correct (rotation based on datetime)
- Verify rotation tracker is being updated
- Check DEVS tier plan limits configuration

**Remote signing errors for DEVS tier**
- Verify subscription plan is correctly set to "devs"
- Check PLAN_LIMITS configuration
- Ensure service key vault is provided

## Related Documentation

- [Subscription Module](../../src/subscription/README.md)
- [Key Vault Implementation](../../packages/marty-common/marty_backend_common/infrastructure/key_vault.py)
- [Square Billing Integration](../../src/subscription/square_service.py)
- [API Key Service](../../src/subscription/api_key_service.py)
