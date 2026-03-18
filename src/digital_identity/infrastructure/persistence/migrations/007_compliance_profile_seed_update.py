"""
Migration: Add issuance_protocol to Compliance Profiles + Seed All 13 Codes

Adds:
- issuance_protocol column to compliance_profiles table
- Seeds / upserts all 13 protocol-defined system compliance codes

Revision ID: 007_compliance_profile_seed_update
Revises: 006_obv3_readiness
Create Date: 2026-03-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '007_compliance_profile_seed_update'
down_revision = '006_obv3_readiness'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add issuance_protocol column and seed all 13 system compliance profiles."""

    # ── Schema change ─────────────────────────────────────
    op.add_column(
        'digital_identity_compliance_profiles',
        sa.Column('issuance_protocol', sa.String(50), nullable=True)
    )
    op.create_index(
        'ix_compliance_profiles_issuance_protocol',
        'digital_identity_compliance_profiles',
        ['issuance_protocol']
    )

    # ── Seed / upsert system profiles ─────────────────────
    # Runs the idempotent seed function which creates new profiles
    # and updates existing ones to the current spec shape.
    # This is safe to run on both fresh and existing databases.
    _seed_system_profiles(op.get_bind())


def downgrade() -> None:
    """Remove issuance_protocol column."""
    op.drop_index(
        'ix_compliance_profiles_issuance_protocol',
        'digital_identity_compliance_profiles',
    )
    op.drop_column('digital_identity_compliance_profiles', 'issuance_protocol')


# ── Inline seed data (matches seed_system_compliance_profiles.py) ──

import json
from datetime import datetime, timezone

SYSTEM_PROFILES = [
    ("icao-dtc-system",  "ICAO Digital Travel Credential", "ICAO_DTC",
     "ICAO Digital Travel Credential using mDoc format with CSCA/DSC chain validation.",
     "MDOC", "DIRECT",
     {"requires_x509_cert": True, "requires_did": False, "requires_jwk": False,
      "cert_key_usage": ["digital_signature"], "recommended_algorithms": ["ES256", "ES384"]}),

    ("icao-mrz-system", "ICAO 9303 MRZ (mDoc)", "ICAO_MRZ",
     "ICAO 9303 Machine Readable Zone using mDoc format.",
     "MDOC", "DIRECT",
     {"requires_x509_cert": True, "requires_did": False, "requires_jwk": False,
      "cert_key_usage": ["digital_signature"], "recommended_algorithms": ["ES256", "ES384"]}),

    ("aamva-mdl-system", "AAMVA Mobile Driver's License", "AAMVA_MDL",
     "AAMVA mDL using mDoc format with IACA chain validation.",
     "MDOC", "DIRECT",
     {"requires_x509_cert": True, "requires_did": False, "requires_jwk": False,
      "cert_key_usage": ["digital_signature"], "recommended_algorithms": ["ES256"]}),

    ("eudi-pid-system", "EUDI Person Identification Data", "EUDI_PID",
     "EUDI Wallet PID attestation using SD-JWT VC per eIDAS 2.0.",
     "SD_JWT_VC", "OID4VCI_AUTH_CODE",
     {"requires_x509_cert": True, "requires_did": False, "requires_jwk": True,
      "cert_key_usage": ["digital_signature"], "recommended_algorithms": ["ES256"]}),

    ("eudi-mdl-system", "EUDI Mobile Driving Licence", "EUDI_MDL",
     "EUDI Wallet MDL attestation using mDoc per EUDI ARF.",
     "MDOC", "OID4VCI_AUTH_CODE",
     {"requires_x509_cert": True, "requires_did": False, "requires_jwk": False,
      "cert_key_usage": ["digital_signature"], "recommended_algorithms": ["ES256"]}),

    ("obv3-jwt-system", "Open Badge v3 (VC-JWT)", "OB3_JWT",
     "Open Badge v3 with JWT proof format.",
     "VC_JWT", "OID4VCI_PRE_AUTH",
     {"requires_x509_cert": False, "requires_did": True, "requires_jwk": False,
      "cert_key_usage": [], "recommended_algorithms": ["ES256", "EdDSA", "RS256"]}),

    ("obv3-jsonld-system", "Open Badge v3 (JSON-LD)", "OB3_JSONLD",
     "Open Badge v3 with JSON-LD Data Integrity proofs.",
     "JSON_LD", "OID4VCI_PRE_AUTH",
     {"requires_x509_cert": False, "requires_did": True, "requires_jwk": False,
      "cert_key_usage": [], "recommended_algorithms": ["ES256", "EdDSA"]}),

    ("obv2-compat-system", "Open Badge v2 (Legacy)", "OB2_COMPATIBILITY",
     "Open Badge v2 legacy backward-compatibility mode.",
     "JSON_LD", "DIRECT",
     {"requires_x509_cert": False, "requires_did": False, "requires_jwk": False,
      "cert_key_usage": [], "recommended_algorithms": ["RS256"]}),

    ("sd-jwt-vc-system", "SD-JWT Verifiable Credential", "SD_JWT_VC",
     "Generic SD-JWT VC per IETF draft-ietf-oauth-sd-jwt-vc.",
     "SD_JWT_VC", "OID4VCI_PRE_AUTH",
     {"requires_x509_cert": False, "requires_did": False, "requires_jwk": True,
      "cert_key_usage": [], "recommended_algorithms": ["ES256", "ES384"]}),

    ("enterprise-vc-system", "Enterprise Verifiable Credential", "ENTERPRISE_VC",
     "Generic enterprise VC for organization-internal credentials.",
     "SD_JWT_VC", "OID4VCI_PRE_AUTH",
     {"requires_x509_cert": False, "requires_did": False, "requires_jwk": True,
      "cert_key_usage": [], "recommended_algorithms": ["ES256", "ES384", "EdDSA"]}),

    ("oid4vc-system", "OID4VC (SD-JWT VC)", "OID4VC",
     "OpenID for Verifiable Credentials with SD-JWT VC.",
     "SD_JWT_VC", "OID4VCI_PRE_AUTH",
     {"requires_x509_cert": False, "requires_did": False, "requires_jwk": True,
      "cert_key_usage": [], "recommended_algorithms": ["ES256", "ES384", "EdDSA"]}),

    ("pex-system", "DIF Presentation Exchange v2", "PEX",
     "DIF Presentation Exchange v2 interoperability profile.",
     "SD_JWT_VC", "OID4VCI_PRE_AUTH",
     {"requires_x509_cert": False, "requires_did": False, "requires_jwk": True,
      "cert_key_usage": [], "recommended_algorithms": ["ES256", "ES384", "EdDSA"]}),

    ("custom-system", "Custom Compliance Profile", "CUSTOM",
     "Placeholder for organization-defined compliance profiles.",
     "SD_JWT_VC", "DIRECT",
     {"requires_x509_cert": False, "requires_did": False, "requires_jwk": False,
      "cert_key_usage": [], "recommended_algorithms": ["ES256"]}),
]


def _seed_system_profiles(bind) -> None:
    """Idempotent upsert of all 13 system compliance profiles."""
    now = datetime.now(timezone.utc).isoformat()

    for (pid, name, code, desc, fmt, protocol, artifacts) in SYSTEM_PROFILES:
        # Check existence
        row = bind.execute(
            text("SELECT id FROM digital_identity_compliance_profiles WHERE code = :code"),
            {"code": code},
        ).fetchone()

        if row:
            # Update existing to current spec shape
            bind.execute(
                text("""
                    UPDATE digital_identity_compliance_profiles
                    SET name = :name,
                        description = :desc,
                        credential_format = :fmt,
                        issuance_protocol = :protocol,
                        issuer_artifact_requirements = :artifacts,
                        default_claim_verification_rules = :rules,
                        updated_at = :now
                    WHERE code = :code
                """),
                {
                    "name": name, "desc": desc, "fmt": fmt, "protocol": protocol,
                    "artifacts": json.dumps(artifacts), "rules": json.dumps([]),
                    "now": now, "code": code,
                },
            )
        else:
            # Insert new
            bind.execute(
                text("""
                    INSERT INTO digital_identity_compliance_profiles
                        (id, name, code, description, credential_format,
                         issuance_protocol, issuer_artifact_requirements,
                         default_claim_verification_rules, trust_profile_requirements,
                         is_system, discoverable, metadata, created_at, updated_at, version)
                    VALUES
                        (:id, :name, :code, :desc, :fmt,
                         :protocol, :artifacts,
                         :rules, :tpc,
                         1, 1, :meta, :now, :now, 1)
                """),
                {
                    "id": pid, "name": name, "code": code, "desc": desc, "fmt": fmt,
                    "protocol": protocol, "artifacts": json.dumps(artifacts),
                    "rules": json.dumps([]), "tpc": json.dumps({}),
                    "meta": json.dumps({}), "now": now,
                },
            )
