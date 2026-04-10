#!/usr/bin/env python3
"""
Crypto Boundaries Implementation Demonstration

This script demonstrates the key features of the new crypto boundaries
and key management implementation:

1. Role separation enforcement
2. KMS/HSM provider abstraction
3. Evidence signing for audit trails
"""

import asyncio
import sys
from pathlib import Path

# Add the src directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from marty_backend_common.crypto.evidence_signing import (
    EvidenceSigner,
    EvidenceType,
    EvidenceVerifier,
    VerificationOutcome,
)
from marty_backend_common.crypto.kms_provider import KMSProvider, create_kms_manager
from marty_backend_common.crypto.role_separation import (
    CryptoRole,
    KeyPurpose,
    RoleBoundaryViolation,
    create_csca_key_identity,
    create_dsc_key_identity,
    create_evidence_key_identity,
    create_wallet_key_identity,
)


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")


async def demonstrate_role_separation():
    """Demonstrate role separation enforcement."""
    print_section("ROLE SEPARATION DEMONSTRATION")

    # Create different role key identities
    csca_key = create_csca_key_identity("US", 1)
    dsc_key = create_dsc_key_identity("US", "passport", 1)
    wallet_key = create_wallet_key_identity("device123")
    evidence_key = create_evidence_key_identity("verifier001")

    print(f"CSCA Key ID: {csca_key.full_key_id}")
    print(f"DSC Key ID: {dsc_key.full_key_id}")
    print(f"Wallet Key ID: {wallet_key.full_key_id}")
    print(f"Evidence Key ID: {evidence_key.full_key_id}")

    # Demonstrate role boundary enforcement
    from marty_backend_common.crypto.role_separation import RoleSeparationEnforcer

    enforcer = RoleSeparationEnforcer()

    print("\n✅ Valid operations:")
    try:
        enforcer.validate_key_operation(csca_key, "sign", CryptoRole.CSCA)
        print("  - CSCA can sign with CSCA key")

        enforcer.validate_key_operation(wallet_key, "sign", CryptoRole.WALLET)
        print("  - Wallet can sign with wallet key")

        # Public key sharing for verification
        enforcer.validate_key_sharing(
            CryptoRole.DSC, CryptoRole.VERIFIER, KeyPurpose.SIGNATURE_VERIFICATION
        )
        print("  - DSC public key can be shared with verifier")

    except RoleBoundaryViolation as e:
        print(f"  ❌ Unexpected violation: {e}")

    print("\n❌ Blocked operations (role boundary violations):")
    try:
        enforcer.validate_key_operation(csca_key, "sign", CryptoRole.WALLET)
        print("  - ERROR: Should have blocked wallet using CSCA key!")
    except RoleBoundaryViolation:
        print("  ✅ Correctly blocked: Wallet cannot use CSCA key")

    try:
        enforcer.validate_key_sharing(
            CryptoRole.CSCA, CryptoRole.VERIFIER, KeyPurpose.CERTIFICATE_SIGNING
        )
        print("  - ERROR: Should have blocked CSCA private key sharing!")
    except RoleBoundaryViolation:
        print("  ✅ Correctly blocked: CSCA private key cannot be shared")


async def demonstrate_kms_provider():
    """Demonstrate KMS/HSM provider functionality."""
    print_section("KMS/HSM PROVIDER DEMONSTRATION")

    # Create KMS manager with software HSM for demo
    kms = create_kms_manager(KMSProvider.SOFTWARE_HSM)

    print("Created KMS manager with Software HSM provider")

    # Generate keys for different roles
    print("\n🔑 Generating keys for different roles:")

    # CSCA key (would require HSM in production)
    csca_key = await kms.generate_key_for_role(
        role=CryptoRole.CSCA,
        purpose=KeyPurpose.CERTIFICATE_SIGNING,
        key_id="csca-demo-001",
        algorithm="RSA2048",
        issuer_identifier="DEMO",
        allow_software=True,  # Override HSM requirement for demo
    )
    print(f"  ✅ Generated CSCA key: {csca_key.key_identity.full_key_id}")

    # DSC key
    dsc_key = await kms.generate_key_for_role(
        role=CryptoRole.DSC,
        purpose=KeyPurpose.DOCUMENT_SIGNING,
        key_id="dsc-demo-001",
        algorithm="ES256",
        issuer_identifier="DEMO",
        allow_software=True,
    )
    print(f"  ✅ Generated DSC key: {dsc_key.key_identity.full_key_id}")

    # Wallet key
    wallet_key = await kms.generate_key_for_role(
        role=CryptoRole.WALLET,
        purpose=KeyPurpose.DEVICE_BINDING,
        key_id="wallet-demo-001",
        algorithm="ES256",
        device_identifier="demo-device",
    )
    print(f"  ✅ Generated Wallet key: {wallet_key.key_identity.full_key_id}")

    # Evidence signing key
    evidence_key = await kms.generate_key_for_role(
        role=CryptoRole.EVIDENCE,
        purpose=KeyPurpose.EVIDENCE_SIGNING,
        key_id="evidence-demo-001",
        algorithm="ES256",
    )
    print(f"  ✅ Generated Evidence key: {evidence_key.key_identity.full_key_id}")

    # Demonstrate signing with role validation
    print("\n🖊️  Signing operations with role validation:")

    data_to_sign = b"Demo document data to be signed"

    # Valid signing operation
    dsc_signature = await kms.sign_with_role_validation(
        key_identity=dsc_key.key_identity, data=data_to_sign, requesting_role=CryptoRole.DSC
    )
    print(f"  ✅ DSC signed data (signature length: {len(dsc_signature)} bytes)")

    # Test role boundary violation in signing
    try:
        await kms.sign_with_role_validation(
            key_identity=dsc_key.key_identity,
            data=data_to_sign,
            requesting_role=CryptoRole.WALLET,  # Wrong role!
        )
        print("  ❌ ERROR: Should have blocked cross-role signing!")
    except RoleBoundaryViolation:
        print("  ✅ Correctly blocked: Wallet cannot sign with DSC key")

    # Demonstrate public key access for verification
    print("\n🔍 Public key access for verification:")

    dsc_public_key = await kms.get_public_key_for_verification(
        key_identity=dsc_key.key_identity, requesting_role=CryptoRole.VERIFIER
    )
    print(f"  ✅ Verifier accessed DSC public key ({len(dsc_public_key)} bytes)")

    # Show audit logs
    print(f"\n📊 Audit logs generated: {len(kms.audit_logs)} entries")
    for i, log in enumerate(kms.audit_logs[-3:], 1):  # Show last 3 entries
        print(
            f"  {i}. {log.operation.value} on {log.key_identity.role.value} key - {'SUCCESS' if log.success else 'FAILED'}"
        )

    return kms, evidence_key


async def demonstrate_evidence_signing(kms, evidence_key_material):
    """Demonstrate evidence signing for audit trails."""
    print_section("EVIDENCE SIGNING DEMONSTRATION")

    # Create evidence signer
    evidence_signer = EvidenceSigner(kms, "demo-verification-service")
    await evidence_signer.initialize()

    print("Created evidence signer for verification service")

    # Create evidence for document verification
    print("\n📋 Creating signed evidence for document verification:")

    verification_details = {
        "document_type": "passport",
        "issuing_country": "US",
        "document_number": "123456789",
        "security_features_checked": ["mrz", "chip", "visual_security"],
        "biometric_verification": "passed",
        "trust_chain_validation": "valid",
        "policy_compliance": "compliant",
    }

    signed_evidence = await evidence_signer.sign_verification_outcome(
        subject="passport:US:123456789",
        verification_method="comprehensive_multi_factor_verification",
        outcome=VerificationOutcome.VALID,
        details=verification_details,
        evidence_type=EvidenceType.DOCUMENT_VERIFICATION,
    )

    print(f"  ✅ Created signed evidence: {signed_evidence.evidence.metadata.evidence_id}")
    print(f"  📝 Evidence outcome: {signed_evidence.evidence.outcome.value}")
    print(f"  🔒 Signature algorithm: {signed_evidence.signature_algorithm}")
    print(f"  📅 Timestamp: {signed_evidence.signature_timestamp}")

    # Create audit log evidence
    print("\n📊 Creating audit log evidence:")

    audit_evidence = await evidence_signer.create_audit_log_evidence(
        operation="document_verification",
        actor="verification-service",
        resource="passport:US:123456789",
        outcome="success",
        details={
            "verification_duration_ms": 1250,
            "security_level": "high",
            "compliance_frameworks": ["ICAO", "FIPS_140_2"],
        },
    )

    print(f"  ✅ Created audit evidence: {audit_evidence.evidence.metadata.evidence_id}")

    # Demonstrate evidence chain integrity
    print("\n🔗 Evidence chain integrity:")

    chain = evidence_signer.get_evidence_chain()
    is_chain_valid = chain.verify_chain_integrity()
    print(f"  📊 Total evidence entries: {len(chain.entries)}")
    print(f"  ✅ Chain integrity: {'VALID' if is_chain_valid else 'INVALID'}")

    # Show evidence chaining
    if len(chain.entries) >= 2:
        entry1 = chain.entries[0]
        entry2 = chain.entries[1]
        print(f"  🔗 Entry 1 hash: {entry1.evidence_hash[:16]}...")
        print(
            f"  🔗 Entry 2 chain hash: {entry2.evidence.metadata.chain_hash[:16] if entry2.evidence.metadata.chain_hash else 'None'}..."
        )

    # Verify evidence signatures
    print("\n🔍 Evidence verification:")

    evidence_verifier = EvidenceVerifier(kms)

    # Verify individual evidence
    is_evidence_valid = await evidence_verifier.verify_evidence(signed_evidence)
    print(f"  ✅ Document evidence signature: {'VALID' if is_evidence_valid else 'INVALID'}")

    is_audit_valid = await evidence_verifier.verify_evidence(audit_evidence)
    print(f"  ✅ Audit evidence signature: {'VALID' if is_audit_valid else 'INVALID'}")

    # Verify entire chain
    is_chain_verified = await evidence_verifier.verify_evidence_chain(chain)
    print(f"  ✅ Complete evidence chain: {'VALID' if is_chain_verified else 'INVALID'}")

    # Export evidence chain
    print("\n📤 Evidence chain export:")

    exported_chain = evidence_signer.export_evidence_chain()
    export_size = len(exported_chain)
    print(f"  📦 Exported chain size: {export_size:,} bytes")
    print("  📋 Export format: JSON")

    # Show a sample of the exported data
    import json

    try:
        chain_data = json.loads(exported_chain)
        print(f"  📊 Chain metadata: {chain_data['chain_metadata']['total_entries']} entries")
        print(f"  📅 Export timestamp: {chain_data['chain_metadata']['export_timestamp']}")
    except:
        print("  ⚠️  Could not parse exported chain data")


async def demonstrate_tamper_detection(kms):
    """Demonstrate tamper detection in evidence."""
    print_section("TAMPER DETECTION DEMONSTRATION")

    # Create evidence signer and verifier
    evidence_signer = EvidenceSigner(kms, "tamper-test-service")
    await evidence_signer.initialize()
    evidence_verifier = EvidenceVerifier(kms)

    # Create original evidence
    original_evidence = await evidence_signer.sign_verification_outcome(
        subject="tamper-test-document",
        verification_method="test-verification",
        outcome=VerificationOutcome.VALID,
        details={"original": "data", "important": "value"},
    )

    print("📋 Created original evidence")

    # Verify original evidence
    is_original_valid = await evidence_verifier.verify_evidence(original_evidence)
    print(f"  ✅ Original evidence valid: {is_original_valid}")

    # Simulate tampering by modifying the evidence
    print("\n🚨 Simulating evidence tampering:")

    # Make a copy and tamper with it
    import copy

    tampered_evidence = copy.deepcopy(original_evidence)
    tampered_evidence.evidence.details["tampered"] = "malicious_data"
    tampered_evidence.evidence.outcome = VerificationOutcome.INVALID

    print("  🔧 Modified evidence details and outcome")

    # Try to verify tampered evidence
    is_tampered_valid = await evidence_verifier.verify_evidence(tampered_evidence)
    print(f"  ❌ Tampered evidence valid: {is_tampered_valid}")

    if not is_tampered_valid:
        print("  ✅ SUCCESS: Tampering detected and rejected!")
    else:
        print("  🚨 FAILURE: Tampering not detected!")


async def main():
    """Main demonstration function."""
    print("🔐 Crypto Boundaries & Key Management Implementation Demo")
    print("=" * 60)

    try:
        # Demonstrate role separation
        await demonstrate_role_separation()

        # Demonstrate KMS provider
        kms, evidence_key = await demonstrate_kms_provider()

        # Demonstrate evidence signing
        await demonstrate_evidence_signing(kms, evidence_key)

        # Demonstrate tamper detection
        await demonstrate_tamper_detection(kms)

        print_section("DEMO COMPLETE")
        print("🎉 All demonstrations completed successfully!")
        print("\nKey achievements demonstrated:")
        print("  ✅ Role separation enforced with runtime validation")
        print("  ✅ KMS/HSM provider abstraction working")
        print("  ✅ Evidence signing creating tamper-evident audit logs")
        print("  ✅ Tamper detection preventing evidence manipulation")
        print("  ✅ Audit trails maintained for all operations")

        print("\n📚 Next steps:")
        print("  1. Deploy to development environment")
        print("  2. Configure production HSM/KMS providers")
        print("  3. Migrate existing services to new architecture")
        print("  4. Enable evidence signing in production")

    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
