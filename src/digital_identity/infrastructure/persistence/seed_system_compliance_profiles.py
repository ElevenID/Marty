"""
System Compliance Profiles Seed Data

Creates read-only system compliance profiles for:
- Open Badge v3 (VC-JWT format)
- Open Badge v3 (JSON-LD format)
- Open Badge v2 (Legacy compatibility)

These profiles are marked as is_system=True and cannot be modified by users.
They can be cloned to create custom compliance profiles.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_async_session
from .models import ComplianceProfileModel


# System compliance profile definitions
SYSTEM_COMPLIANCE_PROFILES = [
    {
        "id": "obv3-jwt-system",
        "name": "Open Badge v3 (VC-JWT)",
        "code": "OB3_JWT",
        "description": (
            "Open Badge v3 compliance profile using W3C Verifiable Credentials "
            "with JWT proof format. Supports standard OBv3 achievement credentials "
            "with selective disclosure capabilities."
        ),
        "credential_format": "VC_JWT",
        "issuer_artifact_requirements": {
            "required_artifacts": ["issuer_did", "issuer_key_id"],
            "optional_artifacts": ["issuer_certificate_chain_pem"],
            "key_algorithms": ["RS256", "ES256", "EdDSA"],
            "key_access_modes": ["key_vault", "hsm", "local"],
        },
        "default_claim_verification_rules": [
            {
                "claim_name": "achievement",
                "required": True,
                "data_type": "object",
                "validation": {
                    "required_fields": ["type", "name", "description", "criteria"],
                },
            },
            {
                "claim_name": "criteria",
                "required": True,
                "data_type": "object",
                "validation": {
                    "required_fields": ["narrative"],
                },
            },
            {
                "claim_name": "issuer",
                "required": True,
                "data_type": "object",
                "validation": {
                    "required_fields": ["type", "name", "id"],
                },
            },
            {
                "claim_name": "issuedOn",
                "required": True,
                "data_type": "datetime",
                "validation": {
                    "format": "iso8601",
                },
            },
        ],
        "trust_profile_requirements": {
            "revocation_methods": ["StatusList2021", "BitstringStatusList"],
            "require_holder_binding": True,
            "allowed_signing_algorithms": ["RS256", "ES256", "EdDSA"],
        },
        "metadata_": {
            "specification_url": "https://www.imsglobal.org/spec/ob/v3p0/",
            "context": "https://purl.imsglobal.org/spec/ob/v3p0/context.json",
            "version": "3.0",
            "format_family": "w3c_vc",
        },
    },
    {
        "id": "obv3-jsonld-system",
        "name": "Open Badge v3 (JSON-LD)",
        "code": "OB3_JSONLD",
        "description": (
            "Open Badge v3 compliance profile using W3C Verifiable Credentials "
            "with JSON-LD Data Integrity proofs. Provides full linked data "
            "semantics with cryptographic verification."
        ),
        "credential_format": "JSON_LD",
        "issuer_artifact_requirements": {
            "required_artifacts": ["issuer_did", "issuer_key_id"],
            "optional_artifacts": ["verification_method"],
            "key_algorithms": ["Ed25519", "ES256K", "BLS12381G2"],
            "key_access_modes": ["key_vault", "hsm", "local"],
            "proof_suites": ["Ed25519Signature2020", "JsonWebSignature2020"],
        },
        "default_claim_verification_rules": [
            {
                "claim_name": "achievement",
                "required": True,
                "data_type": "object",
                "validation": {
                    "required_fields": ["type", "name", "description", "criteria"],
                },
            },
            {
                "claim_name": "criteria",
                "required": True,
                "data_type": "object",
                "validation": {
                    "required_fields": ["narrative"],
                },
            },
            {
                "claim_name": "issuer",
                "required": True,
                "data_type": "object",
                "validation": {
                    "required_fields": ["type", "name", "id"],
                },
            },
            {
                "claim_name": "issuedOn",
                "required": True,
                "data_type": "datetime",
                "validation": {
                    "format": "iso8601",
                },
            },
        ],
        "trust_profile_requirements": {
            "revocation_methods": ["StatusList2021", "RevocationList2020"],
            "require_holder_binding": True,
            "require_did_resolution": True,
        },
        "metadata_": {
            "specification_url": "https://www.imsglobal.org/spec/ob/v3p0/",
            "context": "https://purl.imsglobal.org/spec/ob/v3p0/context.json",
            "version": "3.0",
            "format_family": "w3c_vc_jsonld",
            "proof_format": "data_integrity",
        },
    },
    {
        "id": "obv2-compat-system",
        "name": "Open Badge v2 (Legacy)",
        "code": "OB2_COMPATIBILITY",
        "description": (
            "Open Badge v2 legacy compliance profile for backward compatibility. "
            "Supports JSON-based badge assertions with hosted verification. "
            "Recommended for migration scenarios only; new implementations should use OBv3."
        ),
        "credential_format": "OB2_JSON",
        "issuer_artifact_requirements": {
            "required_artifacts": ["issuer_profile_url", "issuer_public_key"],
            "optional_artifacts": ["badge_class_url"],
            "key_algorithms": ["RSA-SHA256"],
            "key_access_modes": ["local", "hosted"],
        },
        "default_claim_verification_rules": [
            {
                "claim_name": "badge",
                "required": True,
                "data_type": "object",
                "validation": {
                    "required_fields": ["type", "name", "description", "image", "criteria", "issuer"],
                },
            },
            {
                "claim_name": "recipient",
                "required": True,
                "data_type": "object",
                "validation": {
                    "required_fields": ["type", "identity", "hashed"],
                },
            },
            {
                "claim_name": "issuedOn",
                "required": True,
                "data_type": "datetime",
                "validation": {
                    "format": "iso8601",
                },
            },
            {
                "claim_name": "verification",
                "required": True,
                "data_type": "object",
                "validation": {
                    "required_fields": ["type"],
                },
            },
        ],
        "trust_profile_requirements": {
            "revocation_methods": ["hosted_revocation_list"],
            "require_hosted_verification": True,
        },
        "metadata_": {
            "specification_url": "https://www.imsglobal.org/spec/ob/v2p0/",
            "version": "2.0",
            "format_family": "openbadges",
            "deprecation_notice": "Open Badge v2 is deprecated. Please migrate to OBv3.",
        },
    },
]


async def seed_system_compliance_profiles(session: AsyncSession) -> None:
    """
    Seed system compliance profiles into the database.
    
    This function is idempotent - it will only insert profiles that don't already exist
    based on the 'code' field.
    
    Args:
        session: Async SQLAlchemy session
    """
    seeded_count = 0
    skipped_count = 0
    
    for profile_data in SYSTEM_COMPLIANCE_PROFILES:
        # Check if profile already exists
        result = await session.execute(
            select(ComplianceProfileModel).where(ComplianceProfileModel.code == profile_data["code"])
        )
        existing_profile = result.scalar_one_or_none()
        
        if existing_profile:
            print(f"⏭️  Skipping existing profile: {profile_data['name']} ({profile_data['code']})")
            skipped_count += 1
            continue
        
        # Create new system profile
        now = datetime.now(timezone.utc)
        profile = ComplianceProfileModel(
            id=profile_data["id"],
            name=profile_data["name"],
            code=profile_data["code"],
            description=profile_data["description"],
            credential_format=profile_data["credential_format"],
            issuer_artifact_requirements=profile_data["issuer_artifact_requirements"],
            default_claim_verification_rules=profile_data["default_claim_verification_rules"],
            trust_profile_requirements=profile_data["trust_profile_requirements"],
            is_system=True,  # System profiles are read-only
            metadata_=profile_data["metadata_"],
            created_at=now,
            updated_at=now,
            version=1,
        )
        
        session.add(profile)
        print(f"✅ Created system profile: {profile_data['name']} ({profile_data['code']})")
        seeded_count += 1
    
    await session.commit()
    
    print(f"\n📊 Seeding complete: {seeded_count} created, {skipped_count} skipped")


async def main():
    """Main entry point for seeding system compliance profiles."""
    print("🌱 Seeding System Compliance Profiles for Open Badge v3...\n")
    
    async for session in get_async_session():
        try:
            await seed_system_compliance_profiles(session)
        except Exception as e:
            print(f"❌ Error seeding profiles: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


if __name__ == "__main__":
    asyncio.run(main())
