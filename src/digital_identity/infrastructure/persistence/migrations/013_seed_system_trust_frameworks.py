"""
Migration: Seed System Trust Frameworks

Seeds the five system trust frameworks (ICAO, AAMVA, EUDI, OB3, CUSTOM)
into the trust_frameworks table. These are immutable system records that
define default PKD endpoints, algorithms, formats, and validation rules
for each trust ecosystem.

Revision ID: 013_seed_system_trust_frameworks
Revises: 012_missing_columns
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

import json
from datetime import datetime, timezone


# revision identifiers, used by Alembic.
revision = '013_seed_system_trust_frameworks'
down_revision = '012_missing_columns'
branch_labels = None
depends_on = None


# (id, code, display_name, description, pkd_endpoints, default_algorithms,
#  default_formats, validation_ruleset, sync_config)
SYSTEM_FRAMEWORKS = [
    (
        "tf-icao-system", "ICAO", "ICAO PKD (ePassports / eMRTD)",
        "ICAO Public Key Directory trust framework for ePassport, eMRTD, "
        "and Digital Travel Credential verification.",
        {"master_list": "https://pkd.icao.int/",
         "crl_distribution": "https://pkd.icao.int/crl/"},
        ["ES256", "ES384", "RS256", "RS384"],
        ["MDOC"],
        {"require_csca_chain": True, "require_dsc_signature": True,
         "check_crl": True, "check_ocsp": True},
        {"source": "icao_pkd", "refresh_interval_hours": 24, "auto_sync": True},
    ),
    (
        "tf-aamva-system", "AAMVA", "AAMVA (Mobile Driver's License)",
        "AAMVA trust framework for ISO 18013-5 mDL verification "
        "with IACA root certificates.",
        {"iaca_trust_list": "https://trust.aamva.org/iaca-trust-list.json",
         "dts_endpoint": "https://dts.aamva.org/"},
        ["ES256", "ES384"],
        ["MDOC"],
        {"require_iaca_chain": True, "check_crl": True,
         "check_ocsp": True, "max_cert_chain_depth": 3},
        {"source": "aamva_dts", "refresh_interval_hours": 24, "auto_sync": True},
    ),
    (
        "tf-eudi-system", "EUDI", "EUDI (EU Digital Identity Wallet)",
        "European Digital Identity Wallet trust framework (eIDAS 2.0). "
        "Supports mDoc and SD-JWT VC with QTSP validation.",
        {"eu_lotl": "https://ec.europa.eu/tools/lotl/eu-lotl.xml",
         "trust_list": "https://eudi.ec.europa.eu/trusted-list.json"},
        ["ES256", "ES384"],
        ["MDOC", "SD_JWT_VC"],
        {"require_qualified_trust_service": True,
         "check_status_list": True, "eidas_level": "high"},
        {"source": "eudi_lotl", "refresh_interval_hours": 12, "auto_sync": True},
    ),
    (
        "tf-ob3-system", "OB3", "Open Badge v3 (1EdTech)",
        "1EdTech Open Badges v3 trust framework for verifiable "
        "achievement credentials (JWT VC and JSON-LD).",
        {},
        ["ES256", "EdDSA"],
        ["VC_JWT", "JSON_LD"],
        {"require_holder_binding": True, "require_issuer_did": True,
         "check_status_list": True},
        {"source": "pinned_issuer", "refresh_interval_hours": 0, "auto_sync": False},
    ),
    (
        "tf-custom-system", "CUSTOM", "Custom (Organization-Defined)",
        "Catch-all trust framework for organization-defined credential ecosystems.",
        {},
        ["ES256", "ES384", "ES512"],
        ["MDOC", "SD_JWT_VC"],
        {},
        {"refresh_interval_hours": 0, "auto_sync": False},
    ),
]


def upgrade() -> None:
    """Seed system trust frameworks (idempotent upsert by code)."""
    bind = op.get_bind()
    now = datetime.now(timezone.utc).isoformat()

    for (fid, code, display_name, desc, pkd, algos, fmts, rules, sync) in SYSTEM_FRAMEWORKS:
        row = bind.execute(
            text("SELECT id FROM trust_frameworks WHERE code = :code"),
            {"code": code},
        ).fetchone()

        if row:
            bind.execute(
                text("""
                    UPDATE trust_frameworks
                    SET display_name      = :display_name,
                        description       = :desc,
                        pkd_endpoints     = :pkd,
                        default_algorithms = :algos,
                        default_formats   = :fmts,
                        validation_ruleset = :rules,
                        sync_config       = :sync,
                        updated_at        = :now
                    WHERE code = :code
                """),
                {
                    "display_name": display_name, "desc": desc,
                    "pkd": json.dumps(pkd), "algos": json.dumps(algos),
                    "fmts": json.dumps(fmts), "rules": json.dumps(rules),
                    "sync": json.dumps(sync), "now": now, "code": code,
                },
            )
        else:
            bind.execute(
                text("""
                    INSERT INTO trust_frameworks
                        (id, code, display_name, description,
                         pkd_endpoints, default_algorithms, default_formats,
                         validation_ruleset, sync_config,
                         is_system, created_at, updated_at)
                    VALUES
                        (:id, :code, :display_name, :desc,
                         :pkd, :algos, :fmts,
                         :rules, :sync,
                         1, :now, :now)
                """),
                {
                    "id": fid, "code": code,
                    "display_name": display_name, "desc": desc,
                    "pkd": json.dumps(pkd), "algos": json.dumps(algos),
                    "fmts": json.dumps(fmts), "rules": json.dumps(rules),
                    "sync": json.dumps(sync), "now": now,
                },
            )


def downgrade() -> None:
    """Remove system trust frameworks."""
    bind = op.get_bind()
    for (fid, code, *_) in SYSTEM_FRAMEWORKS:
        bind.execute(
            text("DELETE FROM trust_frameworks WHERE code = :code AND is_system = 1"),
            {"code": code},
        )
