"""
License Validator

Python port of the marty-license Rust crate's validation logic.
Used by backend containers to verify Ed25519-signed JWT licenses offline,
with optional phone-home for revocation checks.

This module has NO database dependency — it's pure JWT + HTTP.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

logger = logging.getLogger(__name__)

# Environment variables
ENV_LICENSE = "MARTY_LICENSE"  # JWT string
ENV_LICENSE_PATH = "MARTY_LICENSE_PATH"  # path to file containing JWT
ENV_PUBLIC_KEY = "LICENSE_SIGNING_PUBLIC_KEY"
ENV_PUBLIC_KEY_PATH = "LICENSE_SIGNING_PUBLIC_KEY_PATH"
ENV_PRODUCT_ID = "MARTY_PRODUCT_ID"  # which product this container is
ENV_VALIDATION_URL = "MARTY_LICENSE_VALIDATION_URL"  # phone-home URL

DEFAULT_LICENSE_PATH = "/etc/marty/license.key"
DEFAULT_PUBLIC_KEY_PATH = "/etc/marty/license.pub"

ISSUER = "marty-license-issuer"


class LicenseValidationError(Exception):
    """License validation failed."""


class LicenseExpiredError(LicenseValidationError):
    """License has expired and grace period is exhausted."""


class ProductNotEntitledError(LicenseValidationError):
    """This product is not included in the license entitlements."""


class GracePeriodActiveError(LicenseValidationError):
    """License is expired but within grace period — degraded operation."""


@dataclass
class LicenseInfo:
    """Validated license information available to the application."""
    org_id: str
    org_name: str | None
    plan_tier: str | None
    entitled_products: list[str]
    features: list[str]
    max_instances: dict[str, int]
    registry_access: bool
    api_calls_limit: int
    deployment_mode: str | None
    grace_period_days: int
    expires_at: datetime
    days_until_expiry: int
    is_expired: bool
    grace_period_active: bool
    license_jti: str | None
    raw_claims: dict[str, Any]


@dataclass
class ValidatorState:
    """Tracks runtime state for grace period and phone-home."""
    last_phone_home: float = 0.0
    phone_home_interval: float = 86400.0  # 24 hours
    grace_period_started: float | None = None
    revocation_confirmed: bool = False


class LicenseValidator:
    """
    Validates Ed25519-signed JWT licenses for container use.

    Offline-first: signature verification is local. Phone-home is
    optional and only used for revocation checks.
    """

    def __init__(
        self,
        public_key: Ed25519PublicKey,
        product_id: str | None = None,
        validation_url: str | None = None,
    ):
        self._public_key = public_key
        self._product_id = product_id or os.environ.get(ENV_PRODUCT_ID)
        self._validation_url = validation_url or os.environ.get(ENV_VALIDATION_URL)
        self._state = ValidatorState()
        self._cached_info: LicenseInfo | None = None
        self._cached_jwt: str | None = None

    @classmethod
    def from_env(cls, product_id: str | None = None) -> LicenseValidator:
        """
        Create a validator from environment variables.

        Loads the public key from env var or default file path.
        """
        public_key = _load_public_key()
        return cls(
            public_key=public_key,
            product_id=product_id,
        )

    def validate(self, license_jwt: str) -> LicenseInfo:
        """
        Validate a license JWT and return license info.

        Raises LicenseValidationError on failure.
        """
        # Decode and verify signature
        try:
            claims = pyjwt.decode(
                license_jwt,
                self._public_key,
                algorithms=["EdDSA"],
                issuer=ISSUER,
                options={"verify_exp": False},  # we handle expiry + grace ourselves
            )
        except pyjwt.InvalidSignatureError:
            raise LicenseValidationError("Invalid license signature")
        except pyjwt.InvalidIssuerError:
            raise LicenseValidationError("Invalid license issuer")
        except pyjwt.DecodeError as e:
            raise LicenseValidationError(f"Cannot decode license: {e}")

        # Validate required fields
        org_id = claims.get("sub")
        if not org_id:
            raise LicenseValidationError("License missing organization ID (sub)")

        # Build license info
        now = datetime.now(timezone.utc)
        exp_ts = claims.get("exp", 0)
        expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
        is_expired = now > expires_at
        days_until_expiry = int((expires_at - now).total_seconds() / 86400)

        entitled_products = claims.get("entitled_products", [])
        features = claims.get("features", [])
        grace_period_days = claims.get("grace_period_days", 7)

        # Handle expiry and grace period
        grace_period_active = False
        if is_expired:
            grace_period_active = self._check_grace_period(grace_period_days)
            if not grace_period_active:
                raise LicenseExpiredError(
                    f"License expired on {expires_at.isoformat()} "
                    f"and {grace_period_days}-day grace period is exhausted"
                )

        # Check product entitlement
        if self._product_id:
            if not _is_product_entitled(entitled_products, self._product_id):
                raise ProductNotEntitledError(
                    f"Product '{self._product_id}' is not entitled by this license. "
                    f"Entitled: {entitled_products}"
                )

        info = LicenseInfo(
            org_id=org_id,
            org_name=claims.get("org_name"),
            plan_tier=claims.get("plan_tier"),
            entitled_products=entitled_products,
            features=features,
            max_instances=claims.get("max_instances", {}),
            registry_access=claims.get("registry_access", False),
            api_calls_limit=claims.get("api_calls_limit", 0),
            deployment_mode=claims.get("deployment_mode"),
            grace_period_days=grace_period_days,
            expires_at=expires_at,
            days_until_expiry=days_until_expiry,
            is_expired=is_expired,
            grace_period_active=grace_period_active,
            license_jti=claims.get("jti"),
            raw_claims=claims,
        )

        self._cached_info = info
        self._cached_jwt = license_jwt
        return info

    def validate_from_env(self) -> LicenseInfo:
        """Load and validate the license from environment / file system."""
        license_jwt = _load_license_jwt()
        return self.validate(license_jwt)

    @property
    def cached_info(self) -> LicenseInfo | None:
        """Get the last validated license info (None if not yet validated)."""
        return self._cached_info

    def has_feature(self, feature: str) -> bool:
        """Check if a feature is licensed. Returns False if no license loaded."""
        if self._cached_info is None:
            return False
        features = self._cached_info.features
        if "*" in features:
            return True
        if feature in features:
            return True
        # Category match (e.g., "mdl" matches "mdl_qr")
        return any(feature.startswith(f) for f in features)

    def has_product(self, product: str) -> bool:
        """Check if a product is entitled. Returns False if no license loaded."""
        if self._cached_info is None:
            return False
        return _is_product_entitled(self._cached_info.entitled_products, product)

    async def phone_home(self) -> dict[str, Any] | None:
        """
        Check license validity against the license server (revocation check).

        Returns the validation response, or None if phone-home is not configured
        or not due yet. Non-blocking — failures are logged, not raised.
        """
        if not self._validation_url or not self._cached_info:
            return None

        now = time.monotonic()
        if now - self._state.last_phone_home < self._state.phone_home_interval:
            return None  # not due yet

        jti = self._cached_info.license_jti
        if not jti:
            return None

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self._validation_url}/v1/licenses/validate/{jti}")
                resp.raise_for_status()
                result = resp.json()

            self._state.last_phone_home = now

            if not result.get("valid", False):
                reason = result.get("reason", "unknown")
                logger.warning("License %s failed phone-home: %s", jti, reason)
                if reason == "revoked":
                    self._state.revocation_confirmed = True

            return result

        except Exception:
            logger.debug("License phone-home failed (will retry later)", exc_info=True)
            return None

    @property
    def is_revoked(self) -> bool:
        """Whether a phone-home check has confirmed revocation."""
        return self._state.revocation_confirmed

    def _check_grace_period(self, grace_period_days: int) -> bool:
        """Check if we're within the grace period after expiry."""
        now = time.monotonic()

        if self._state.grace_period_started is None:
            self._state.grace_period_started = now
            logger.warning(
                "License expired — entering %d-day grace period",
                grace_period_days,
            )

        elapsed_seconds = now - self._state.grace_period_started
        elapsed_days = elapsed_seconds / 86400
        return elapsed_days < grace_period_days


def _is_product_entitled(entitled_products: list[str], product: str) -> bool:
    """Check if a product is in the entitlement list."""
    if not entitled_products:
        return product == "verifier"  # legacy license = verifier only
    if "*" in entitled_products:
        return True
    return product in entitled_products


def _load_public_key() -> Ed25519PublicKey:
    """Load the Ed25519 public key from environment or default paths."""
    # Try env var (PEM string)
    pem_str = os.environ.get(ENV_PUBLIC_KEY)
    if pem_str:
        return _parse_public_key(pem_str.encode())

    # Try env var (file path)
    key_path = os.environ.get(ENV_PUBLIC_KEY_PATH)
    if key_path:
        return _parse_public_key(Path(key_path).read_bytes())

    # Try default path
    default_path = Path(DEFAULT_PUBLIC_KEY_PATH)
    if default_path.exists():
        return _parse_public_key(default_path.read_bytes())

    raise LicenseValidationError(
        f"No license public key found. Set {ENV_PUBLIC_KEY}, "
        f"{ENV_PUBLIC_KEY_PATH}, or place key at {DEFAULT_PUBLIC_KEY_PATH}"
    )


def _parse_public_key(pem_data: bytes) -> Ed25519PublicKey:
    """Parse PEM data into an Ed25519 public key."""
    key = load_pem_public_key(pem_data)
    if not isinstance(key, Ed25519PublicKey):
        raise LicenseValidationError(
            f"Expected Ed25519 public key, got {type(key).__name__}"
        )
    return key


def _load_license_jwt() -> str:
    """Load the license JWT from environment or file system."""
    # Try env var (JWT string)
    jwt_str = os.environ.get(ENV_LICENSE)
    if jwt_str:
        return jwt_str.strip()

    # Try env var (file path)
    jwt_path = os.environ.get(ENV_LICENSE_PATH)
    if jwt_path:
        return Path(jwt_path).read_text().strip()

    # Try default path
    default_path = Path(DEFAULT_LICENSE_PATH)
    if default_path.exists():
        return default_path.read_text().strip()

    raise LicenseValidationError(
        f"No license found. Set {ENV_LICENSE}, {ENV_LICENSE_PATH}, "
        f"or place license at {DEFAULT_LICENSE_PATH}"
    )
