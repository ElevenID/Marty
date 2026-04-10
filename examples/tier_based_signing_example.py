"""
Example: Using Tier-Based Signing Service

This example demonstrates how to use the signing service with different
subscription tiers and handle key rotation for DEVS tier.

Run with:
    python examples/tier_based_signing_example.py
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone

# Mock implementations for demonstration
class MockKeyVault:
    """Mock key vault for demonstration."""
    
    def __init__(self):
        self.keys = {}
    
    async def ensure_key(self, key_id: str, algorithm: str) -> None:
        if key_id not in self.keys:
            self.keys[key_id] = {
                "algorithm": algorithm,
                "created_at": datetime.now(timezone.utc),
            }
            print(f"  ✅ Created key: {key_id} ({algorithm})")
    
    async def sign(self, key_id: str, payload: bytes, algorithm: str) -> bytes:
        if key_id not in self.keys:
            raise ValueError(f"Key not found: {key_id}")
        print(f"  ✅ Signed {len(payload)} bytes with key: {key_id}")
        return b"mock_signature_" + key_id.encode()


async def example_devs_tier_workflow():
    """Example workflow for DEVS tier with service key vault."""
    print("\n" + "="*60)
    print("DEVS TIER WORKFLOW - Service Key Vault")
    print("="*60 + "\n")
    
    from src.subscription.models import Organization, Subscription, SubscriptionStatus
    from src.subscription.signing_service import (
        SigningService,
        KeyRotationRequired,
    )
    from uuid import uuid4
    
    # Create DEVS organization
    devs_org = Organization(
        id=uuid4(),
        name="DEVS Test Org",
        slug="devs-test",
        settings={},
        created_at=datetime.now(timezone.utc),
    )
    
    # Mock subscription
    devs_subscription = Subscription(
        id=uuid4(),
        organization_id=devs_org.id,
        plan="devs",
        status=SubscriptionStatus.ACTIVE,
        api_calls_limit=10000,
        api_calls_used=0,
        created_at=datetime.now(timezone.utc),
    )
    
    # Mock DB session
    class MockDB:
        async def execute(self, query):
            class Result:
                def scalar_one_or_none(self):
                    return devs_subscription
            return Result()
    
    # Initialize service
    mock_vault = MockKeyVault()
    mock_db = MockDB()
    signing_service = SigningService(mock_db, mock_vault)
    
    print("1. Creating signing key for DEVS tier...")
    key_info = await signing_service.ensure_signing_key(
        organization=devs_org,
        key_id="app-key",
        algorithm="ecdsa-p256",
    )
    print(f"   Key ID: {key_info.key_id}")
    print(f"   Type: {key_info.key_type.value}")
    print(f"   Rotation required: {key_info.rotation_required}")
    
    print("\n2. Signing data with service key...")
    payload = b"Important credential data"
    signature = await signing_service.sign(
        organization=devs_org,
        key_id="app-key",
        payload=payload,
    )
    print(f"   Signature: {signature.hex()[:40]}...")
    
    print("\n3. Simulating 15 days passing...")
    org_key_id = f"org-{devs_org.id}-app-key"
    old_date = datetime.now(timezone.utc) - timedelta(days=15)
    signing_service._key_rotation_tracker[org_key_id] = old_date
    print(f"   Key last rotated: {old_date.date()}")
    
    print("\n4. Checking if rotation is required...")
    key_info = await signing_service.get_key_info(devs_org, "app-key")
    if key_info.rotation_required:
        print("   ⚠️  Key rotation REQUIRED (> 14 days old)")
    
    print("\n5. Attempting to sign with expired key...")
    try:
        await signing_service.sign(
            organization=devs_org,
            key_id="app-key",
            payload=payload,
        )
    except KeyRotationRequired as e:
        print(f"   ❌ {e}")
    
    print("\n6. Rotating the key...")
    new_key = await signing_service.rotate_key(
        organization=devs_org,
        key_id="app-key",
        algorithm="ecdsa-p256",
    )
    print(f"   New key ID: {new_key.key_id}")
    print(f"   Rotation required: {new_key.rotation_required}")
    
    print("\n7. Signing with rotated key...")
    # Extract version from new key ID
    new_key_name = new_key.key_id.split("/")[-1]  # Get the full key name
    signature = await signing_service.sign(
        organization=devs_org,
        key_id=new_key_name.replace(f"org-{devs_org.id}-", ""),
        payload=payload,
        force_rotation_check=False,  # Skip check since we just rotated
    )
    print(f"   ✅ Signature: {signature.hex()[:40]}...")
    
    print("\n✅ DEVS tier workflow completed successfully!\n")


async def example_starter_tier_workflow():
    """Example workflow for STARTER tier with remote signing."""
    print("\n" + "="*60)
    print("STARTER TIER WORKFLOW - Remote Signing Required")
    print("="*60 + "\n")
    
    from src.subscription.models import Organization, Subscription, SubscriptionStatus
    from src.subscription.signing_service import (
        SigningService,
        RemoteSigningRequired,
    )
    from uuid import uuid4
    
    # Create STARTER organization
    starter_org = Organization(
        id=uuid4(),
        name="Starter Test Org",
        slug="starter-test",
        settings={},
        created_at=datetime.now(timezone.utc),
    )
    
    # Mock subscription
    starter_subscription = Subscription(
        id=uuid4(),
        organization_id=starter_org.id,
        plan="starter",
        status=SubscriptionStatus.ACTIVE,
        api_calls_limit=50000,
        api_calls_used=0,
        created_at=datetime.now(timezone.utc),
    )
    
    # Mock DB session
    class MockDB:
        async def execute(self, query):
            class Result:
                def scalar_one_or_none(self):
                    return starter_subscription
            return Result()
    
    # Initialize service
    mock_vault = MockKeyVault()
    mock_db = MockDB()
    signing_service = SigningService(mock_db, mock_vault)
    
    print("1. Attempting to create signing key for STARTER tier...")
    try:
        await signing_service.ensure_signing_key(
            organization=starter_org,
            key_id="app-key",
            algorithm="ecdsa-p256",
        )
    except RemoteSigningRequired as e:
        print(f"   ❌ {e}")
    
    print("\n2. STARTER tier must use remote signing")
    print("   You need to:")
    print("   - Set up your own key vault (AWS KMS, Azure Key Vault, etc.)")
    print("   - Configure remote signing endpoint")
    print("   - Manage your own key lifecycle")
    
    print("\n3. Example remote signing setup:")
    print("   ```python")
    print("   # Configure your own key vault")
    print("   from marty_backend_common.infrastructure.key_vault import (")
    print("       build_key_vault_client,")
    print("       KeyVaultConfig,")
    print("   )")
    print()
    print("   your_vault_config = KeyVaultConfig(")
    print("       provider='aws_kms',")
    print("       # Your AWS KMS configuration")
    print("   )")
    print("   your_vault = build_key_vault_client(your_vault_config)")
    print()
    print("   # Use your vault for signing")
    print("   signature = await your_vault.sign(")
    print("       key_id='your-kms-key-id',")
    print("       payload=payload,")
    print("       algorithm='ecdsa-p256',")
    print("   )")
    print("   ```")
    
    print("\n✅ STARTER tier workflow demonstration completed!\n")


async def example_tier_comparison():
    """Compare features across different tiers."""
    print("\n" + "="*60)
    print("TIER COMPARISON")
    print("="*60 + "\n")
    
    from src.subscription.square_service import PLAN_LIMITS, SquarePlan
    
    print(f"{'Tier':<15} {'Service KV':<12} {'Remote Sign':<13} {'API Calls':<12} {'API Keys':<10}")
    print("-" * 65)
    
    for plan in [SquarePlan.SANDBOX, SquarePlan.PROGRAM,
                 SquarePlan.INSTITUTION, SquarePlan.SYSTEM]:
        limits = PLAN_LIMITS[plan]
        
        service_kv = "✅ Yes" if limits.can_use_service_key_vault else "❌ No"
        remote_sign = "✅ Required" if limits.requires_remote_signing else "❌ No"
        api_calls = f"{limits.api_calls_per_month:,}" if limits.api_calls_per_month != -1 else "Unlimited"
        api_keys = str(limits.api_keys) if limits.api_keys != -1 else "Unlimited"
        
        print(f"{plan.value.upper():<15} {service_kv:<12} {remote_sign:<13} {api_calls:<12} {api_keys:<10}")
    
    print("\n📝 Key Points:")
    print("   • DEVS tier: Use service key vault with 14-day rotation")
    print("   • Other tiers: Must use remote signing with your own KMS")
    print("   • Service never sees private keys for non-DEVS tiers")
    print()


async def main():
    """Run all examples."""
    print("\n" + "="*60)
    print("TIER-BASED SIGNING SERVICE EXAMPLES")
    print("="*60)
    
    # Run tier comparison
    await example_tier_comparison()
    
    # Run DEVS tier workflow
    await example_devs_tier_workflow()
    
    # Run STARTER tier workflow
    await example_starter_tier_workflow()
    
    print("="*60)
    print("All examples completed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
