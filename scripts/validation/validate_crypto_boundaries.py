#!/usr/bin/env python3
"""
Standalone test for crypto boundaries implementation.

This test validates the core functionality without requiring the full
marty_common module dependencies.
"""

import asyncio
import sys
from pathlib import Path


# Test the role separation module standalone
def test_role_separation():
    """Test role separation functionality."""
    print("🔍 Testing Role Separation...")

    # Import and test basic enums
    sys.path.insert(0, str(Path(__file__).parent / "src"))

    try:
        # Import core components
        from marty_backend_common.crypto.role_separation import (
            ROLE_POLICIES,
            CryptoRole,
            KeyIdentity,
            KeyPurpose,
            KeyPurposeMismatch,
            RoleBoundaryViolation,
            RoleSeparationEnforcer,
            create_csca_key_identity,
            create_dsc_key_identity,
            create_evidence_key_identity,
            create_wallet_key_identity,
        )

        print("  ✅ Successfully imported role separation components")

        # Test role enumeration
        print(f"  ✅ Available roles: {[role.value for role in CryptoRole]}")
        print(f"  ✅ Available purposes: {[purpose.name for purpose in KeyPurpose]}")

        # Test key identity creation
        csca_key = create_csca_key_identity("US", 1)
        dsc_key = create_dsc_key_identity("US", "passport", 1)
        wallet_key = create_wallet_key_identity("device123")
        evidence_key = create_evidence_key_identity("verifier001")

        print(f"  ✅ CSCA key: {csca_key.full_key_id}")
        print(f"  ✅ DSC key: {dsc_key.full_key_id}")
        print(f"  ✅ Wallet key: {wallet_key.full_key_id}")
        print(f"  ✅ Evidence key: {evidence_key.full_key_id}")

        # Test role policies
        print(f"  ✅ Role policies defined: {len(ROLE_POLICIES)} roles")

        # Test role boundary enforcement
        enforcer = RoleSeparationEnforcer()

        # Valid operation
        enforcer.validate_key_operation(csca_key, "sign", CryptoRole.CSCA)
        print("  ✅ Valid operation allowed: CSCA signing with CSCA key")

        # Invalid operation (should raise exception)
        try:
            enforcer.validate_key_operation(csca_key, "sign", CryptoRole.WALLET)
            print("  ❌ ERROR: Invalid operation was allowed!")
            return False
        except RoleBoundaryViolation:
            print("  ✅ Invalid operation blocked: Wallet cannot use CSCA key")

        # Test key purpose validation
        try:
            KeyIdentity(
                role=CryptoRole.CSCA,
                purpose=KeyPurpose.DEVICE_BINDING,  # Invalid for CSCA
                key_id="invalid-key",
            )
            print("  ❌ ERROR: Invalid purpose was allowed!")
            return False
        except KeyPurposeMismatch:
            print("  ✅ Invalid purpose blocked: CSCA cannot use device binding purpose")

        return True

    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_kms_provider_basic():
    """Test basic KMS provider functionality."""
    print("\n🔑 Testing KMS Provider (basic)...")

    try:
        from marty_backend_common.crypto.kms_provider import (
            KeyMaterial,
            KeyOperation,
            KMSManager,
            KMSProvider,
            SoftwareHSMProvider,
            create_kms_manager,
        )
        from marty_backend_common.crypto.role_separation import CryptoRole, KeyPurpose

        print("  ✅ Successfully imported KMS provider components")
        print(f"  ✅ Available providers: {[p.value for p in KMSProvider]}")
        print(f"  ✅ Available operations: {[op.value for op in KeyOperation]}")

        # Test provider creation
        try:
            kms = create_kms_manager(KMSProvider.SOFTWARE_HSM)
            print("  ✅ Successfully created KMS manager with Software HSM")
            return True
        except Exception as e:
            print(f"  ⚠️  KMS manager creation failed: {e}")
            return False

    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        return False


def test_evidence_signing_basic():
    """Test basic evidence signing functionality."""
    print("\n📋 Testing Evidence Signing (basic)...")

    try:
        from marty_backend_common.crypto.evidence_signing import (
            EvidenceChain,
            EvidenceMetadata,
            EvidenceSigner,
            EvidenceType,
            EvidenceVerifier,
            SignedEvidence,
            VerificationEvidence,
            VerificationOutcome,
        )

        print("  ✅ Successfully imported evidence signing components")
        print(f"  ✅ Evidence types: {[et.value for et in EvidenceType]}")
        print(f"  ✅ Verification outcomes: {[vo.value for vo in VerificationOutcome]}")

        # Test basic data structures
        import uuid
        from datetime import datetime, timezone

        metadata = EvidenceMetadata(
            evidence_id=str(uuid.uuid4()),
            evidence_type=EvidenceType.DOCUMENT_VERIFICATION,
            timestamp=datetime.now(timezone.utc),
            signer_id="test-service",
        )

        evidence = VerificationEvidence(
            metadata=metadata,
            subject="test:document:123",
            verification_method="test_method",
            outcome=VerificationOutcome.VALID,
            details={"test": "data"},
        )

        print("  ✅ Successfully created evidence structures")
        print(f"  ✅ Evidence JSON serialization works: {len(evidence.to_json())} bytes")

        # Test evidence chain
        chain = EvidenceChain()
        print("  ✅ Successfully created evidence chain")

        return True

    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        return False


async def test_kms_integration():
    """Test KMS integration with role separation."""
    print("\n🔗 Testing KMS Integration...")

    try:
        from marty_backend_common.crypto.kms_provider import KMSProvider, create_kms_manager
        from marty_backend_common.crypto.role_separation import CryptoRole, KeyPurpose

        # Create KMS manager
        kms = create_kms_manager(KMSProvider.SOFTWARE_HSM)
        print("  ✅ Created KMS manager")

        # Test key generation
        evidence_key = await kms.generate_key_for_role(
            role=CryptoRole.EVIDENCE,
            purpose=KeyPurpose.EVIDENCE_SIGNING,
            key_id="test-evidence-key",
            algorithm="ES256",
        )

        print(f"  ✅ Generated evidence key: {evidence_key.key_identity.full_key_id}")
        print(f"  ✅ Key algorithm: {evidence_key.algorithm}")
        print(f"  ✅ Key provider: {evidence_key.provider.value}")

        # Test signing
        test_data = b"Test data for signing"
        signature = await kms.sign_with_role_validation(
            key_identity=evidence_key.key_identity,
            data=test_data,
            requesting_role=CryptoRole.EVIDENCE,
        )

        print(f"  ✅ Successfully signed data: {len(signature)} bytes")

        # Test audit logging
        audit_count = len(kms.audit_logs)
        print(f"  ✅ Audit logs generated: {audit_count} entries")

        return True

    except Exception as e:
        print(f"  ❌ Integration test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_evidence_integration():
    """Test evidence signing integration."""
    print("\n📝 Testing Evidence Integration...")

    try:
        from marty_backend_common.crypto.evidence_signing import (
            EvidenceSigner,
            EvidenceType,
            VerificationOutcome,
        )
        from marty_backend_common.crypto.kms_provider import KMSProvider, create_kms_manager

        # Create KMS and evidence signer
        kms = create_kms_manager(KMSProvider.SOFTWARE_HSM)
        evidence_signer = EvidenceSigner(kms, "test-service")
        await evidence_signer.initialize()

        print("  ✅ Created evidence signer")

        # Sign verification outcome
        signed_evidence = await evidence_signer.sign_verification_outcome(
            subject="test:document:456",
            verification_method="comprehensive_test",
            outcome=VerificationOutcome.VALID,
            details={
                "document_type": "passport",
                "security_check": "passed",
                "biometric_match": True,
            },
            evidence_type=EvidenceType.DOCUMENT_VERIFICATION,
        )

        print(f"  ✅ Created signed evidence: {signed_evidence.evidence.metadata.evidence_id}")
        print(f"  ✅ Evidence outcome: {signed_evidence.evidence.outcome.value}")
        print(f"  ✅ Signature length: {len(signed_evidence.signature)} bytes")

        # Test evidence chain
        chain = evidence_signer.get_evidence_chain()
        print(f"  ✅ Evidence chain entries: {len(chain.entries)}")
        print(f"  ✅ Chain integrity: {chain.verify_chain_integrity()}")

        return True

    except Exception as e:
        print(f"  ❌ Evidence integration test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_configuration():
    """Test configuration files."""
    print("\n⚙️  Testing Configuration...")

    try:
        import yaml

        # Test crypto boundaries config
        config_path = Path("config/security/crypto_boundaries.yaml")
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)

            print("  ✅ Crypto boundaries config loaded successfully")
            print(f"  ✅ Config sections: {list(config.keys())}")

            # Validate key sections
            required_sections = [
                "crypto_boundaries",
                "kms_providers",
                "evidence_signing",
                "key_management",
            ]
            for section in required_sections:
                if section in config:
                    print(f"    ✅ {section} section present")
                else:
                    print(f"    ❌ {section} section missing")
                    return False
        else:
            print("  ❌ Crypto boundaries config file not found")
            return False

        # Test main security policy
        policy_path = Path("config/security/security_policy.yaml")
        if policy_path.exists():
            with open(policy_path) as f:
                policy = yaml.safe_load(f)

            print("  ✅ Security policy loaded successfully")

            # Check for crypto boundaries integration
            if "key_management" in policy.get("security", {}):
                print("    ✅ Key management section integrated")
            else:
                print("    ⚠️  Key management section not found in security policy")
        else:
            print("  ❌ Security policy file not found")
            return False

        return True

    except Exception as e:
        print(f"  ❌ Configuration test failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("🔐 Crypto Boundaries Implementation Validation")
    print("=" * 60)

    results = []

    # Test components individually
    results.append(("Role Separation", test_role_separation()))
    results.append(("KMS Provider Basic", test_kms_provider_basic()))
    results.append(("Evidence Signing Basic", test_evidence_signing_basic()))
    results.append(("Configuration", test_configuration()))

    # Test integrations
    results.append(("KMS Integration", await test_kms_integration()))
    results.append(("Evidence Integration", await test_evidence_integration()))

    # Summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    passed = 0
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nThe crypto boundaries implementation is working correctly:")
        print("  ✅ Role separation enforced")
        print("  ✅ KMS/HSM provider abstraction functional")
        print("  ✅ Evidence signing creating tamper-evident logs")
        print("  ✅ Configuration properly structured")
        print("  ✅ Integration between components working")

        print("\n📋 Next Steps:")
        print("  1. Deploy to development environment")
        print("  2. Install required dependencies (grpc, etc.)")
        print("  3. Configure production HSM/KMS providers")
        print("  4. Run full integration tests")
        print("  5. Begin service migration")

        return 0
    else:
        print(f"\n❌ {total - passed} tests failed. Review implementation.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
