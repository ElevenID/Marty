"""
System Trust Frameworks Seed Data

Creates system trust framework rows for each trust ecosystem.
These are immutable records (is_system=True) that define the global
trust configuration for ICAO, AAMVA, EUDI, Open Badge v3, and a
catch-all CUSTOM framework.

Organizations reference a framework via OrganizationTrustProfile and
apply their own policy overrides.

Framework codes match TrustProfileType enum values in the domain layer
(ICAO, AAMVA, EUDI, CUSTOM) plus OB3 for Open Badge use-cases.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import TrustFrameworkAnchorModel, TrustFrameworkModel

logger = logging.getLogger(__name__)


# ── OB3 Trust Anchors (pinned issuer DIDs) ────────────────────
OB3_TRUST_ANCHORS: list[dict[str, Any]] = [
    {
        "id": "ta-ob3-marty-system",
        "framework_id": "tf-ob3-system",
        "anchor_type": "issuer_did",
        "subject": "Marty Platform (System Issuer)",
        "issuer": "did:web:marty.example.com",
        "issuer_did": "did:web:marty.example.com",
        "issuer_jwk": {
            "kty": "EC",
            "crv": "P-256",
            "x": "_PLACEHOLDER_",
            "y": "_PLACEHOLDER_",
        },
        "source": "pinned_issuer",
    },
]


SYSTEM_TRUST_FRAMEWORKS: list[dict[str, Any]] = [
    # ── ICAO ──────────────────────────────────────────────
    {
        "id": "tf-icao-system",
        "code": "ICAO",
        "display_name": "ICAO PKD (ePassports / eMRTD)",
        "description": (
            "ICAO Public Key Directory trust framework for ePassport, eMRTD, "
            "and Digital Travel Credential verification. Uses CSCA/DSC "
            "certificate chain validation per ICAO Doc 9303."
        ),
        "pkd_endpoints": {
            "master_list": "https://pkd.icao.int/",
            "crl_distribution": "https://pkd.icao.int/crl/",
        },
        "default_algorithms": ["ES256", "ES384", "RS256", "RS384"],
        "default_formats": ["MDOC"],
        "validation_ruleset": {
            "require_csca_chain": True,
            "require_dsc_signature": True,
            "check_crl": True,
            "check_ocsp": True,
        },
        "sync_config": {
            "source": "icao_pkd",
            "refresh_interval_hours": 24,
            "auto_sync": True,
        },
    },
    # ── AAMVA ─────────────────────────────────────────────
    {
        "id": "tf-aamva-system",
        "code": "AAMVA",
        "display_name": "AAMVA (Mobile Driver's License)",
        "description": (
            "AAMVA trust framework for ISO 18013-5 Mobile Driver's License "
            "verification. Uses IACA root certificates and CRL/OCSP "
            "revocation checking per AAMVA Implementation Guidelines."
        ),
        "pkd_endpoints": {
            "iaca_trust_list": "https://trust.aamva.org/iaca-trust-list.json",
            "dts_endpoint": "https://dts.aamva.org/",
        },
        "default_algorithms": ["ES256", "ES384"],
        "default_formats": ["MDOC"],
        "validation_ruleset": {
            "require_iaca_chain": True,
            "check_crl": True,
            "check_ocsp": True,
            "max_cert_chain_depth": 3,
        },
        "sync_config": {
            "source": "aamva_dts",
            "refresh_interval_hours": 24,
            "auto_sync": True,
        },
    },
    # ── EUDI ──────────────────────────────────────────────
    {
        "id": "tf-eudi-system",
        "code": "EUDI",
        "display_name": "EUDI (EU Digital Identity Wallet)",
        "description": (
            "European Digital Identity Wallet trust framework implementing "
            "eIDAS 2.0 requirements. Supports both mDoc (ISO 18013-5) and "
            "SD-JWT VC formats with Qualified Trust Service Provider "
            "certificate validation via the EU List of Trusted Lists."
        ),
        "pkd_endpoints": {
            "eu_lotl": "https://ec.europa.eu/tools/lotl/eu-lotl.xml",
            "trust_list": "https://eudi.ec.europa.eu/trusted-list.json",
        },
        "default_algorithms": ["ES256", "ES384"],
        "default_formats": ["MDOC", "SD_JWT_VC"],
        "validation_ruleset": {
            "require_qualified_trust_service": True,
            "check_status_list": True,
            "eidas_level": "high",
        },
        "sync_config": {
            "source": "eudi_lotl",
            "refresh_interval_hours": 12,
            "auto_sync": True,
        },
    },
    # ── Open Badge v3 ─────────────────────────────────────
    {
        "id": "tf-ob3-system",
        "code": "OB3",
        "display_name": "Open Badge v3 (1EdTech)",
        "description": (
            "1EdTech Open Badges v3 trust framework for verifiable "
            "achievement credentials. Supports both JWT VC and JSON-LD "
            "Data Integrity proof formats with DID-based issuer "
            "verification and StatusList2021 revocation."
        ),
        "pkd_endpoints": {},
        "default_algorithms": ["ES256", "EdDSA"],
        "default_formats": ["VC_JWT", "JSON_LD"],
        "validation_ruleset": {
            "require_holder_binding": True,
            "require_issuer_did": True,
            "check_status_list": True,
        },
        "sync_config": {
            "source": "pinned_issuer",
            "refresh_interval_hours": 0,
            "auto_sync": False,
        },
    },
    # ── CUSTOM ────────────────────────────────────────────
    {
        "id": "tf-custom-system",
        "code": "CUSTOM",
        "display_name": "Custom (Organization-Defined)",
        "description": (
            "Catch-all trust framework for organization-defined credential "
            "ecosystems. Supports all algorithms and formats. Clone this "
            "framework to build organization-specific trust configurations."
        ),
        "pkd_endpoints": {},
        "default_algorithms": ["ES256", "ES384", "ES512"],
        "default_formats": ["MDOC", "SD_JWT_VC"],
        "validation_ruleset": {},
        "sync_config": {
            "refresh_interval_hours": 0,
            "auto_sync": False,
        },
    },
]


async def seed_system_trust_frameworks(session: AsyncSession) -> None:
    """
    Seed system trust frameworks into the database.

    Idempotent — existing frameworks (matched by code) are updated to the
    current spec shape; new ones are inserted.

    Args:
        session: Async SQLAlchemy session
    """
    created_count = 0
    updated_count = 0

    for fw_data in SYSTEM_TRUST_FRAMEWORKS:
        result = await session.execute(
            select(TrustFrameworkModel).where(
                TrustFrameworkModel.code == fw_data["code"]
            )
        )
        existing = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)

        if existing:
            existing.display_name = fw_data["display_name"]
            existing.description = fw_data["description"]
            existing.pkd_endpoints = fw_data["pkd_endpoints"]
            existing.default_algorithms = fw_data["default_algorithms"]
            existing.default_formats = fw_data["default_formats"]
            existing.validation_ruleset = fw_data["validation_ruleset"]
            existing.sync_config = fw_data["sync_config"]
            existing.updated_at = now
            updated_count += 1
            continue

        model = TrustFrameworkModel(
            id=fw_data["id"],
            code=fw_data["code"],
            display_name=fw_data["display_name"],
            description=fw_data["description"],
            pkd_endpoints=fw_data["pkd_endpoints"],
            default_algorithms=fw_data["default_algorithms"],
            default_formats=fw_data["default_formats"],
            validation_ruleset=fw_data["validation_ruleset"],
            sync_config=fw_data["sync_config"],
            is_system=True,
            created_at=now,
            updated_at=now,
        )
        session.add(model)
        created_count += 1

    await session.commit()
    logger.info(
        "Trust framework seeding complete: %d created, %d updated",
        created_count, updated_count,
    )

    # Seed OB3 trust anchors after frameworks exist
    await seed_ob3_trust_anchors(session)


async def seed_ob3_trust_anchors(session: AsyncSession) -> None:
    """
    Seed system trust anchors for the OB3 framework.

    Idempotent — existing anchors (matched by id) are skipped.
    """
    created = 0

    for anchor_data in OB3_TRUST_ANCHORS:
        result = await session.execute(
            select(TrustFrameworkAnchorModel).where(
                TrustFrameworkAnchorModel.id == anchor_data["id"]
            )
        )
        if result.scalar_one_or_none():
            continue

        now = datetime.now(timezone.utc)
        model = TrustFrameworkAnchorModel(
            id=anchor_data["id"],
            framework_id=anchor_data["framework_id"],
            anchor_type=anchor_data["anchor_type"],
            subject=anchor_data["subject"],
            issuer=anchor_data["issuer"],
            issuer_did=anchor_data["issuer_did"],
            issuer_jwk=anchor_data["issuer_jwk"],
            source=anchor_data["source"],
            synced_at=now,
            created_at=now,
        )
        session.add(model)
        created += 1

    if created:
        await session.commit()
        logger.info("OB3 trust anchor seeding complete: %d created", created)


async def main():
    """Main entry point for seeding system trust frameworks."""
    logging.basicConfig(level=logging.INFO)
    from .database import get_db_session

    async for session in get_db_session():
        try:
            await seed_system_trust_frameworks(session)
        except Exception as e:
            print(f"Error seeding trust frameworks: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


if __name__ == "__main__":
    asyncio.run(main())
if __name__ == "__main__":
    asyncio.run(main())
