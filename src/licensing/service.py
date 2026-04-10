"""
License Issuer Service

Mints, revokes, and validates Ed25519-signed JWT licenses.
Ties license lifecycle to organization subscription state.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

import jwt as pyjwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .keys import LicenseKeyManager
from .models import License, LicenseRevocation, LicenseStatus

logger = logging.getLogger(__name__)

# Canonical plan tier names (aligned with frontend pricingContent.js)
PLAN_TIER_SANDBOX = "sandbox"
PLAN_TIER_PROGRAM = "program"
PLAN_TIER_INSTITUTION = "institution"
PLAN_TIER_SYSTEM = "system"

VALID_PLAN_TIERS = {PLAN_TIER_SANDBOX, PLAN_TIER_PROGRAM, PLAN_TIER_INSTITUTION, PLAN_TIER_SYSTEM}

# Default entitlements per plan tier
DEFAULT_ENTITLEMENTS: dict[str, dict[str, Any]] = {
    PLAN_TIER_SANDBOX: {
        "entitled_products": ["verifier"],
        "features": ["mdl", "sd-jwt"],
        "max_instances": {},
        "registry_access": False,
        "api_calls_limit": 1000,
        "grace_period_days": 7,
    },
    PLAN_TIER_PROGRAM: {
        "entitled_products": [
            "verifier", "document-signer", "oid4vc-api", "ui-app",
        ],
        "features": ["mdl", "emrtd", "oid4vp", "sd-jwt", "open-badges"],
        "max_instances": {"verifier": 2},
        "registry_access": True,
        "api_calls_limit": 50000,
        "grace_period_days": 7,
    },
    PLAN_TIER_INSTITUTION: {
        "entitled_products": [
            "verifier", "document-signer", "passport-engine", "csca-service",
            "inspection-system", "mdl-engine", "oid4vc-api", "ui-app",
            "open-badges", "trust-anchor",
        ],
        "features": ["mdl", "emrtd", "oid4vp", "sd-jwt", "open-badges", "usb-sync", "reporting"],
        "max_instances": {"verifier": 10},
        "registry_access": True,
        "api_calls_limit": 500000,
        "grace_period_days": 14,
    },
    PLAN_TIER_SYSTEM: {
        "entitled_products": ["*"],
        "features": ["*"],
        "max_instances": {},  # all default to unlimited for system tier
        "registry_access": True,
        "api_calls_limit": 0,  # unlimited
        "grace_period_days": 30,
    },
}

# Maps plan names to canonical tier names.
# Canonical names map to themselves; legacy names provide backward compatibility.
SQUARE_PLAN_TO_TIER: dict[str, str] = {
    # Canonical (identity)
    "sandbox": PLAN_TIER_SANDBOX,
    "program": PLAN_TIER_PROGRAM,
    "institution": PLAN_TIER_INSTITUTION,
    "system": PLAN_TIER_SYSTEM,
    # Legacy (deprecated — kept for existing database records)
    "free": PLAN_TIER_SANDBOX,
    "devs": PLAN_TIER_SANDBOX,
    "starter": PLAN_TIER_PROGRAM,
    "professional": PLAN_TIER_INSTITUTION,
    "enterprise": PLAN_TIER_SYSTEM,
}


@dataclass
class LicenseRequest:
    """Request to issue a new license."""
    org_id: UUID
    org_name: str
    plan_tier: str
    entitled_products: list[str] | None = None
    features: list[str] | None = None
    max_instances: dict[str, int] | None = None
    registry_access: bool | None = None
    api_calls_limit: int | None = None
    hardware_binding: str | None = None
    deployment_mode: str | None = None
    duration_days: int = 365
    grace_period_days: int | None = None


@dataclass
class IssuedLicense:
    """Result of issuing a license."""
    license_id: UUID
    license_jti: str
    license_jwt: str
    org_id: UUID
    plan_tier: str
    issued_at: datetime
    expires_at: datetime
    entitled_products: list[str]
    features: list[str]


class LicenseIssuerError(Exception):
    """Base error for license issuer operations."""


class LicenseNotFoundError(LicenseIssuerError):
    """License not found."""


class LicenseIssuerService:
    """
    Issues and manages Ed25519-signed JWT licenses.

    Licenses are JWTs with the following claims (aligned with marty-license crate):
    - iss: "marty-license-issuer"
    - sub: organization ID
    - jti: unique license ID
    - iat/exp/nbf: timestamps
    - plan_tier: canonical tier name
    - features: list of licensed feature flags
    - entitled_products: list of product identifiers
    - max_instances: per-product instance caps
    - registry_access: container registry pull permission
    - api_calls_limit: monthly API cap
    - hardware_binding: optional hardware fingerprint hash
    - deployment_mode: "development" | "production"
    - grace_period_days: offline renewal window
    - org_name: display name
    - update_channels: allowed update channels
    """

    ISSUER = "marty-license-issuer"

    def __init__(self, db: AsyncSession, key_manager: LicenseKeyManager):
        self._db = db
        self._keys = key_manager

    async def issue_license(self, request: LicenseRequest) -> IssuedLicense:
        """
        Issue a new signed license for an organization.

        If the org already has an active license, it is superseded.
        """
        if request.plan_tier not in VALID_PLAN_TIERS:
            raise LicenseIssuerError(f"Invalid plan tier: {request.plan_tier}")

        if not self._keys.can_sign:
            raise LicenseIssuerError("No signing key available — cannot issue licenses")

        # Resolve entitlements: explicit overrides > plan defaults
        defaults = DEFAULT_ENTITLEMENTS[request.plan_tier]
        entitled_products = request.entitled_products or defaults["entitled_products"]
        features = request.features or defaults["features"]
        max_instances = request.max_instances or defaults["max_instances"]
        registry_access = request.registry_access if request.registry_access is not None else defaults["registry_access"]
        api_calls_limit = request.api_calls_limit if request.api_calls_limit is not None else defaults["api_calls_limit"]
        grace_period_days = request.grace_period_days if request.grace_period_days is not None else defaults["grace_period_days"]

        now = datetime.now(timezone.utc)
        expires_at = datetime.fromtimestamp(
            now.timestamp() + request.duration_days * 86400,
            tz=timezone.utc,
        )
        license_id = uuid4()
        license_jti = f"lic_{license_id.hex[:16]}"

        # Build JWT claims (matches marty-license crate LicenseClaims struct)
        claims: dict[str, Any] = {
            "iss": self.ISSUER,
            "sub": str(request.org_id),
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "nbf": int(now.timestamp()),
            "jti": license_jti,
            "plan_tier": request.plan_tier,
            "entitled_products": entitled_products,
            "features": features,
            "max_instances": max_instances,
            "registry_access": registry_access,
            "api_calls_limit": api_calls_limit,
            "org_name": request.org_name,
            "deployment_mode": request.deployment_mode or (
                "development" if request.plan_tier == PLAN_TIER_SANDBOX else "production"
            ),
            "max_verifications_total": 0,  # unlimited by default for non-verifier
            "update_channels": ["stable"],
            "grace_period_days": grace_period_days,
        }

        if request.hardware_binding:
            claims["hardware_binding"] = request.hardware_binding

        # Sign the JWT with Ed25519
        license_jwt = pyjwt.encode(
            claims,
            self._keys.private_key,
            algorithm="EdDSA",
        )

        # Supersede any existing active licenses for this org
        await self._supersede_active_licenses(request.org_id, now)

        # Persist the license record
        license_record = License(
            id=license_id,
            org_id=request.org_id,
            license_jti=license_jti,
            status=LicenseStatus.ACTIVE.value,
            plan_tier=request.plan_tier,
            entitled_products=entitled_products,
            features=features,
            max_instances=max_instances,
            registry_access=registry_access,
            api_calls_limit=api_calls_limit,
            license_jwt=license_jwt,
            issued_at=now,
            expires_at=expires_at,
            created_at=now,
        )
        self._db.add(license_record)
        await self._db.flush()

        logger.info(
            "Issued license %s for org %s (plan=%s, products=%s, expires=%s)",
            license_jti, request.org_id, request.plan_tier,
            entitled_products, expires_at.isoformat(),
        )

        return IssuedLicense(
            license_id=license_id,
            license_jti=license_jti,
            license_jwt=license_jwt,
            org_id=request.org_id,
            plan_tier=request.plan_tier,
            issued_at=now,
            expires_at=expires_at,
            entitled_products=entitled_products,
            features=features,
        )

    async def revoke_license(
        self,
        license_jti: str,
        reason: str = "Subscription canceled",
    ) -> None:
        """Revoke a license by JTI. Adds to the revocation list for online validation."""
        now = datetime.now(timezone.utc)

        # Update license record
        result = await self._db.execute(
            select(License).where(
                License.license_jti == license_jti,
                License.status == LicenseStatus.ACTIVE.value,
            )
        )
        license_record = result.scalar_one_or_none()
        if license_record is None:
            raise LicenseNotFoundError(f"No active license with jti={license_jti}")

        license_record.status = LicenseStatus.REVOKED.value
        license_record.revoked_at = now
        license_record.revocation_reason = reason
        license_record.updated_at = now

        # Add to revocation list (for phone-home checks)
        revocation = LicenseRevocation(
            id=uuid4(),
            license_jti=license_jti,
            org_id=license_record.org_id,
            revoked_at=now,
            reason=reason,
        )
        self._db.add(revocation)
        await self._db.flush()

        logger.info("Revoked license %s: %s", license_jti, reason)

    async def revoke_org_licenses(
        self,
        org_id: UUID,
        reason: str = "Subscription canceled",
    ) -> int:
        """Revoke all active licenses for an organization. Returns count revoked."""
        now = datetime.now(timezone.utc)

        result = await self._db.execute(
            select(License).where(
                License.org_id == org_id,
                License.status == LicenseStatus.ACTIVE.value,
            )
        )
        licenses = result.scalars().all()

        for lic in licenses:
            lic.status = LicenseStatus.REVOKED.value
            lic.revoked_at = now
            lic.revocation_reason = reason
            lic.updated_at = now

            self._db.add(LicenseRevocation(
                id=uuid4(),
                license_jti=lic.license_jti,
                org_id=org_id,
                revoked_at=now,
                reason=reason,
            ))

        await self._db.flush()
        logger.info("Revoked %d licenses for org %s: %s", len(licenses), org_id, reason)
        return len(licenses)

    async def validate_license_online(self, license_jti: str) -> dict[str, Any]:
        """
        Online validation endpoint: check if a license is still valid.

        Returns status info for phone-home checks from containers/verifiers.
        """
        # Check revocation list first (fast path)
        revocation = await self._db.execute(
            select(LicenseRevocation).where(LicenseRevocation.license_jti == license_jti)
        )
        if revocation.scalar_one_or_none() is not None:
            return {"valid": False, "reason": "revoked"}

        # Look up license record
        result = await self._db.execute(
            select(License).where(License.license_jti == license_jti)
        )
        license_record = result.scalar_one_or_none()

        if license_record is None:
            return {"valid": False, "reason": "not_found"}

        if license_record.status == LicenseStatus.EXPIRED.value:
            return {"valid": False, "reason": "expired"}

        if license_record.status == LicenseStatus.SUPERSEDED.value:
            return {"valid": False, "reason": "superseded"}

        now = datetime.now(timezone.utc)
        if license_record.expires_at < now:
            license_record.status = LicenseStatus.EXPIRED.value
            license_record.updated_at = now
            await self._db.flush()
            return {"valid": False, "reason": "expired"}

        return {
            "valid": True,
            "plan_tier": license_record.plan_tier,
            "expires_at": license_record.expires_at.isoformat(),
            "entitled_products": license_record.entitled_products,
        }

    async def get_org_license(self, org_id: UUID) -> License | None:
        """Get the current active license for an organization."""
        result = await self._db.execute(
            select(License).where(
                License.org_id == org_id,
                License.status == LicenseStatus.ACTIVE.value,
            ).order_by(License.issued_at.desc())
        )
        return result.scalar_one_or_none()

    async def get_license_by_jti(self, license_jti: str) -> License | None:
        """Look up a license by its JTI."""
        result = await self._db.execute(
            select(License).where(License.license_jti == license_jti)
        )
        return result.scalar_one_or_none()

    async def list_org_licenses(
        self,
        org_id: UUID,
        include_inactive: bool = False,
    ) -> list[License]:
        """List licenses for an organization."""
        query = select(License).where(License.org_id == org_id)
        if not include_inactive:
            query = query.where(License.status == LicenseStatus.ACTIVE.value)
        query = query.order_by(License.issued_at.desc())
        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def is_revoked(self, license_jti: str) -> bool:
        """Check if a license JTI appears on the revocation list."""
        result = await self._db.execute(
            select(LicenseRevocation.id).where(
                LicenseRevocation.license_jti == license_jti
            )
        )
        return result.scalar_one_or_none() is not None

    async def _supersede_active_licenses(self, org_id: UUID, now: datetime) -> None:
        """Mark all active licenses for an org as superseded."""
        await self._db.execute(
            update(License)
            .where(
                License.org_id == org_id,
                License.status == LicenseStatus.ACTIVE.value,
            )
            .values(
                status=LicenseStatus.SUPERSEDED.value,
                updated_at=now,
            )
        )
