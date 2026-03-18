"""
System Compliance Profiles Seed Data

Creates read-only system compliance profiles for all 13 protocol-defined
compliance codes. Profiles are marked is_system=True and cannot be modified
by users. They can be cloned to create custom organization profiles.

Compliance codes (from marty-protocol enums/compliance-codes.json):
  ICAO_DTC, ICAO_MRZ, AAMVA_MDL, EUDI_PID, EUDI_MDL,
  OB3_JWT, OB3_JSONLD, OB2_COMPATIBILITY,
  SD_JWT_VC, ENTERPRISE_VC, OID4VC, PEX, CUSTOM
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
# issuer_artifact_requirements uses spec shape:
#   requires_x509_cert, requires_did, requires_jwk,
#   cert_key_usage, recommended_algorithms
SYSTEM_COMPLIANCE_PROFILES = [
    # ── ICAO ──────────────────────────────────────────────
    {
        "id": "icao-dtc-system",
        "name": "ICAO Digital Travel Credential",
        "code": "ICAO_DTC",
        "description": (
            "ICAO Digital Travel Credential compliance profile using ISO/IEC 18013-5 mDoc format. "
            "Supports digital travel documents with CSCA/DSC certificate chain validation "
            "per ICAO Doc 9303 and DTC Technical Report."
        ),
        "credential_format": "MDOC",
        "issuance_protocol": "DIRECT",
        "issuer_artifact_requirements": {
            "requires_x509_cert": True,
            "requires_did": False,
            "requires_jwk": False,
            "cert_key_usage": ["digital_signature"],
            "recommended_algorithms": ["ES256", "ES384"],
        },
        "default_claim_verification_rules": [],
        "trust_profile_requirements": {
            "revocation_methods": ["CRL", "OCSP"],
            "require_csca_chain": True,
        },
        "metadata_": {
            "standard": "ICAO Doc 9303, ICAO DTC Technical Report",
            "governed_by": "ICAO",
            "format_family": "mdoc",
        },
    },
    {
        "id": "icao-mrz-system",
        "name": "ICAO 9303 MRZ (mDoc)",
        "code": "ICAO_MRZ",
        "description": (
            "ICAO 9303 Machine Readable Zone compliance profile using ISO/IEC 18013-5 mDoc format. "
            "Supports travel document verification including passports, ID cards, and visa documents "
            "with CSCA/DSC certificate chain validation."
        ),
        "credential_format": "MDOC",
        "issuance_protocol": "DIRECT",
        "issuer_artifact_requirements": {
            "requires_x509_cert": True,
            "requires_did": False,
            "requires_jwk": False,
            "cert_key_usage": ["digital_signature"],
            "recommended_algorithms": ["ES256", "ES384"],
        },
        "default_claim_verification_rules": [],
        "trust_profile_requirements": {
            "revocation_methods": ["CRL", "OCSP"],
            "require_csca_chain": True,
        },
        "metadata_": {
            "standard": "ICAO Doc 9303 Parts 1-13",
            "governed_by": "ICAO",
            "format_family": "mdoc",
            "doc_types": ["TD1", "TD2", "TD3"],
        },
    },
    # ── AAMVA ─────────────────────────────────────────────
    {
        "id": "aamva-mdl-system",
        "name": "AAMVA Mobile Driver's License",
        "code": "AAMVA_MDL",
        "description": (
            "AAMVA Mobile Driver's License compliance profile using ISO/IEC 18013-5 mDoc format. "
            "Supports mDL issuance and verification per AAMVA Implementation Guidelines "
            "with IACA certificate chain validation."
        ),
        "credential_format": "MDOC",
        "issuance_protocol": "DIRECT",
        "issuer_artifact_requirements": {
            "requires_x509_cert": True,
            "requires_did": False,
            "requires_jwk": False,
            "cert_key_usage": ["digital_signature"],
            "recommended_algorithms": ["ES256"],
        },
        "default_claim_verification_rules": [],
        "trust_profile_requirements": {
            "revocation_methods": ["CRL", "STATUS_LIST_2021"],
            "require_iaca_chain": True,
        },
        "metadata_": {
            "standard": "ISO/IEC 18013-5:2021, AAMVA mDL Implementation Guidelines",
            "governed_by": "AAMVA",
            "format_family": "mdoc",
        },
    },
    # ── EUDI ──────────────────────────────────────────────
    {
        "id": "eudi-pid-system",
        "name": "EUDI Person Identification Data",
        "code": "EUDI_PID",
        "description": (
            "EU Digital Identity Wallet Person Identification Data compliance profile "
            "using SD-JWT VC format. Implements eIDAS 2.0 PID attestation requirements "
            "per the EUDI Architecture Reference Framework."
        ),
        "credential_format": "SD_JWT_VC",
        "issuance_protocol": "OID4VCI_AUTH_CODE",
        "issuer_artifact_requirements": {
            "requires_x509_cert": True,
            "requires_did": False,
            "requires_jwk": True,
            "cert_key_usage": ["digital_signature"],
            "recommended_algorithms": ["ES256"],
        },
        "default_claim_verification_rules": [],
        "trust_profile_requirements": {
            "revocation_methods": ["STATUS_LIST_2021"],
            "require_qualified_trust_service": True,
        },
        "metadata_": {
            "standard": "EUDI ARF, eIDAS 2.0, ETSI EN-319",
            "governed_by": "European Commission",
            "format_family": "sd_jwt_vc",
        },
    },
    {
        "id": "eudi-mdl-system",
        "name": "EUDI Mobile Driving Licence",
        "code": "EUDI_MDL",
        "description": (
            "EU Digital Identity Wallet Mobile Driving Licence compliance profile "
            "using ISO/IEC 18013-5 mDoc format. Implements EUDI ARF Annex requirements "
            "for driving licence attestation."
        ),
        "credential_format": "MDOC",
        "issuance_protocol": "OID4VCI_AUTH_CODE",
        "issuer_artifact_requirements": {
            "requires_x509_cert": True,
            "requires_did": False,
            "requires_jwk": False,
            "cert_key_usage": ["digital_signature"],
            "recommended_algorithms": ["ES256"],
        },
        "default_claim_verification_rules": [],
        "trust_profile_requirements": {
            "revocation_methods": ["STATUS_LIST_2021"],
            "require_qualified_trust_service": True,
        },
        "metadata_": {
            "standard": "ISO/IEC 18013-5:2021, EUDI ARF Annex",
            "governed_by": "European Commission",
            "format_family": "mdoc",
        },
    },
    # ── Open Badge ────────────────────────────────────────
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
        "issuance_protocol": "OID4VCI_PRE_AUTH",
        "issuer_artifact_requirements": {
            "requires_x509_cert": False,
            "requires_did": True,
            "requires_jwk": False,
            "cert_key_usage": [],
            "recommended_algorithms": ["ES256", "EdDSA", "RS256"],
        },
        "default_claim_verification_rules": [],
        "trust_profile_requirements": {
            "revocation_methods": ["STATUS_LIST_2021", "BITSTRING_STATUS_LIST"],
            "require_holder_binding": True,
        },
        "metadata_": {
            "standard": "1EdTech Open Badges 3.0, W3C VC Data Model",
            "governed_by": "1EdTech",
            "specification_url": "https://www.imsglobal.org/spec/ob/v3p0/",
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
        "issuance_protocol": "OID4VCI_PRE_AUTH",
        "issuer_artifact_requirements": {
            "requires_x509_cert": False,
            "requires_did": True,
            "requires_jwk": False,
            "cert_key_usage": [],
            "recommended_algorithms": ["ES256", "EdDSA"],
        },
        "default_claim_verification_rules": [],
        "trust_profile_requirements": {
            "revocation_methods": ["STATUS_LIST_2021"],
            "require_holder_binding": True,
        },
        "metadata_": {
            "standard": "1EdTech Open Badges 3.0, W3C VC Data Model, JSON-LD 1.1",
            "governed_by": "1EdTech",
            "specification_url": "https://www.imsglobal.org/spec/ob/v3p0/",
            "format_family": "w3c_vc_jsonld",
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
        "credential_format": "JSON_LD",
        "issuance_protocol": "DIRECT",
        "issuer_artifact_requirements": {
            "requires_x509_cert": False,
            "requires_did": False,
            "requires_jwk": False,
            "cert_key_usage": [],
            "recommended_algorithms": ["RS256"],
        },
        "default_claim_verification_rules": [],
        "trust_profile_requirements": {
            "revocation_methods": ["STATUS_LIST_2021"],
        },
        "metadata_": {
            "standard": "1EdTech Open Badges 2.0",
            "governed_by": "1EdTech",
            "specification_url": "https://www.imsglobal.org/spec/ob/v2p0/",
            "format_family": "openbadges",
            "deprecated": True,
            "migration_target": "OB3_JWT or OB3_JSONLD",
        },
    },
    # ── Generic VC / Interop ──────────────────────────────
    {
        "id": "sd-jwt-vc-system",
        "name": "SD-JWT Verifiable Credential",
        "code": "SD_JWT_VC",
        "description": (
            "Generic Selective Disclosure JWT Verifiable Credential compliance profile. "
            "Framework-agnostic SD-JWT VC issuance and verification with holder binding "
            "per IETF draft-ietf-oauth-sd-jwt-vc."
        ),
        "credential_format": "SD_JWT_VC",
        "issuance_protocol": "OID4VCI_PRE_AUTH",
        "issuer_artifact_requirements": {
            "requires_x509_cert": False,
            "requires_did": False,
            "requires_jwk": True,
            "cert_key_usage": [],
            "recommended_algorithms": ["ES256", "ES384"],
        },
        "default_claim_verification_rules": [],
        "trust_profile_requirements": {
            "revocation_methods": ["STATUS_LIST_2021", "BITSTRING_STATUS_LIST"],
        },
        "metadata_": {
            "standard": "IETF draft-ietf-oauth-sd-jwt-vc",
            "format_family": "sd_jwt_vc",
        },
    },
    {
        "id": "enterprise-vc-system",
        "name": "Enterprise Verifiable Credential",
        "code": "ENTERPRISE_VC",
        "description": (
            "Generic enterprise verifiable credential compliance profile. "
            "Suitable for organization-internal credentials not bound to a public standard. "
            "Supports both JWT and SD-JWT VC formats."
        ),
        "credential_format": "SD_JWT_VC",
        "issuance_protocol": "OID4VCI_PRE_AUTH",
        "issuer_artifact_requirements": {
            "requires_x509_cert": False,
            "requires_did": False,
            "requires_jwk": True,
            "cert_key_usage": [],
            "recommended_algorithms": ["ES256", "ES384", "EdDSA"],
        },
        "default_claim_verification_rules": [],
        "trust_profile_requirements": {},
        "metadata_": {
            "use_case": "Organization-internal credentials",
            "format_family": "sd_jwt_vc",
        },
    },
    {
        "id": "oid4vc-system",
        "name": "OID4VC (SD-JWT VC)",
        "code": "OID4VC",
        "description": (
            "OpenID for Verifiable Credentials compliance profile using SD-JWT VC format. "
            "Supports OID4VCI credential issuance and OID4VP presentation protocols with "
            "selective disclosure and holder binding."
        ),
        "credential_format": "SD_JWT_VC",
        "issuance_protocol": "OID4VCI_PRE_AUTH",
        "issuer_artifact_requirements": {
            "requires_x509_cert": False,
            "requires_did": False,
            "requires_jwk": True,
            "cert_key_usage": [],
            "recommended_algorithms": ["ES256", "ES384", "EdDSA"],
        },
        "default_claim_verification_rules": [],
        "trust_profile_requirements": {
            "revocation_methods": ["STATUS_LIST_2021", "BITSTRING_STATUS_LIST"],
            "require_holder_binding": True,
        },
        "metadata_": {
            "standard": "OpenID for Verifiable Credential Issuance 1.0, OpenID for Verifiable Presentations 1.0",
            "governed_by": "OpenID Foundation",
            "specification_url": "https://openid.net/specs/openid-4-verifiable-credential-issuance-1_0.html",
            "format_family": "sd_jwt_vc",
        },
    },
    {
        "id": "pex-system",
        "name": "DIF Presentation Exchange v2",
        "code": "PEX",
        "description": (
            "DIF Presentation Exchange v2 compliance profile for interoperable credential presentation. "
            "Supports presentation definitions and submission requirements across multiple credential "
            "formats with constraint validation."
        ),
        "credential_format": "SD_JWT_VC",
        "issuance_protocol": "OID4VCI_PRE_AUTH",
        "issuer_artifact_requirements": {
            "requires_x509_cert": False,
            "requires_did": False,
            "requires_jwk": True,
            "cert_key_usage": [],
            "recommended_algorithms": ["ES256", "ES384", "EdDSA"],
        },
        "default_claim_verification_rules": [],
        "trust_profile_requirements": {
            "revocation_methods": ["STATUS_LIST_2021", "BITSTRING_STATUS_LIST"],
        },
        "metadata_": {
            "standard": "DIF Presentation Exchange 2.0.0",
            "governed_by": "Decentralized Identity Foundation",
            "specification_url": "https://identity.foundation/presentation-exchange/spec/v2.0.0/",
            "format_family": "sd_jwt_vc",
        },
    },
    # ── Custom ────────────────────────────────────────────
    {
        "id": "custom-system",
        "name": "Custom Compliance Profile",
        "code": "CUSTOM",
        "description": (
            "Placeholder for organization-defined custom compliance profiles. "
            "Clone this profile and set organization_id to create a proprietary "
            "credential framework configuration."
        ),
        "credential_format": "SD_JWT_VC",
        "issuance_protocol": "DIRECT",
        "issuer_artifact_requirements": {
            "requires_x509_cert": False,
            "requires_did": False,
            "requires_jwk": False,
            "cert_key_usage": [],
            "recommended_algorithms": ["ES256"],
        },
        "default_claim_verification_rules": [],
        "trust_profile_requirements": {},
        "metadata_": {
            "use_case": "Organization-defined compliance profile",
        },
    },
]


async def seed_system_compliance_profiles(session: AsyncSession) -> None:
    """
    Seed system compliance profiles into the database.
    
    This function is idempotent - it will only insert profiles that don't already exist
    based on the compliance_code field. Existing profiles are updated in place to
    ensure artifact requirements match the current spec shape.
    
    Args:
        session: Async SQLAlchemy session
    """
    created_count = 0
    updated_count = 0
    skipped_count = 0
    
    for profile_data in SYSTEM_COMPLIANCE_PROFILES:
        # Check if profile already exists
        result = await session.execute(
            select(ComplianceProfileModel).where(
                ComplianceProfileModel.compliance_code == profile_data["code"]
            )
        )
        existing = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        
        if existing:
            # Update existing profile to current spec shape
            existing.name = profile_data["name"]
            existing.description = profile_data["description"]
            existing.credential_format = profile_data["credential_format"]
            existing.issuer_artifact_requirements = profile_data["issuer_artifact_requirements"]
            existing.default_verification_rules = profile_data["default_claim_verification_rules"]
            existing.trust_profile_constraints = profile_data["trust_profile_requirements"]
            existing.metadata_ = profile_data["metadata_"]
            existing.updated_at = now
            print(f"🔄 Updated existing profile: {profile_data['name']} ({profile_data['code']})")
            updated_count += 1
            continue
        
        # Create new system profile
        profile = ComplianceProfileModel(
            id=profile_data["id"],
            name=profile_data["name"],
            compliance_code=profile_data["code"],
            description=profile_data["description"],
            credential_format=profile_data["credential_format"],
            issuer_artifact_requirements=profile_data["issuer_artifact_requirements"],
            default_verification_rules=profile_data["default_claim_verification_rules"],
            trust_profile_constraints=profile_data["trust_profile_requirements"],
            is_system=True,
            metadata_=profile_data["metadata_"],
            created_at=now,
            updated_at=now,
            version=1,
        )
        
        session.add(profile)
        print(f"✅ Created system profile: {profile_data['name']} ({profile_data['code']})")
        created_count += 1
    
    await session.commit()
    
    print(f"\n📊 Seeding complete: {created_count} created, {updated_count} updated, {skipped_count} skipped")


async def main():
    """Main entry point for seeding system compliance profiles."""
    print("🌱 Seeding System Compliance Profiles...\n")
    
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
