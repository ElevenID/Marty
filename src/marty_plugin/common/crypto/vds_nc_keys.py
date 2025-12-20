"""VDS-NC Public Key Management and Distribution.

This module handles VDS-NC signer key lifecycle management, distribution,
and PKD integration according to ICAO Doc 9303 Part 13 and the unified
trust protocol.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import (
    EllipticCurvePrivateKey,
    EllipticCurvePublicKey,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class KeyStatus(Enum):
    """VDS-NC key lifecycle status."""

    PENDING = "pending"  # Generated but not activated
    ACTIVE = "active"  # Currently active for signing
    ROTATING = "rotating"  # In rotation overlap period
    DEPRECATED = "deprecated"  # No longer used for signing, kept for verification
    REVOKED = "revoked"  # Revoked/compromised
    EXPIRED = "expired"  # Past validity period


class KeyRole(Enum):
    """VDS-NC signer role/purpose."""

    CMC = "CMC"  # Crew Member Certificate
    VISA = "VISA"  # Visa sticker
    EMERGENCY_TRAVEL = "ETD"  # Emergency Travel Document
    PROOF_OF_TESTING = "POT"  # Proof of Testing (health certificates)
    VACCINATION = "VCN"  # Vaccination certificates
    GENERAL = "GENERAL"  # General purpose


@dataclass
class VDSNCKeyMetadata:
    """Metadata for VDS-NC signer keys."""

    kid: str  # Key identifier
    issuer_country: str  # ISO 3166-1 alpha-3 country code
    role: KeyRole
    algorithm: str = "ES256"  # ECDSA with P-256 and SHA-256
    key_size: int = 256
    status: KeyStatus = KeyStatus.PENDING
    rotation_generation: int = 1
    not_before: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    not_after: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=730)
    )
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    activated_at: datetime | None = None
    deprecated_at: datetime | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None
    hsm_key_id: str | None = None  # HSM reference if using HSM
    parent_kid: str | None = None  # Previous key in rotation chain
    tags: dict[str, str] = field(default_factory=dict)

    def is_valid_now(self) -> bool:
        """Check if key is currently valid."""
        now = datetime.now(timezone.utc)
        return (
            self.status in [KeyStatus.ACTIVE, KeyStatus.ROTATING]
            and self.not_before <= now <= self.not_after
        )

    def needs_rotation(self, warning_days: int = 60) -> bool:
        """Check if key approaching expiration."""
        warning_threshold = datetime.now(timezone.utc) + timedelta(days=warning_days)
        return self.not_after <= warning_threshold

    def to_jwk(self, public_key: EllipticCurvePublicKey) -> dict[str, Any]:
        """Convert to JWK format for distribution."""
        # Get public key coordinates
        public_numbers = public_key.public_numbers()

        # Convert to bytes and base64url encode
        x_bytes = public_numbers.x.to_bytes(32, "big")
        y_bytes = public_numbers.y.to_bytes(32, "big")

        import base64

        x_b64 = base64.urlsafe_b64encode(x_bytes).decode("ascii").rstrip("=")
        y_b64 = base64.urlsafe_b64encode(y_bytes).decode("ascii").rstrip("=")

        return {
            "kid": self.kid,
            "kty": "EC",
            "crv": "P-256",
            "x": x_b64,
            "y": y_b64,
            "use": "sig",
            "alg": "ES256",
            "issuer": self.issuer_country,
            "role": self.role.value,
            "not_before": self.not_before.isoformat(),
            "not_after": self.not_after.isoformat(),
            "status": self.status.value,
            "rotation_generation": self.rotation_generation,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        # Convert enums to strings
        data["status"] = self.status.value
        data["role"] = self.role.value
        # Convert datetimes to ISO format
        for key in [
            "not_before",
            "not_after",
            "created_at",
            "activated_at",
            "deprecated_at",
            "revoked_at",
        ]:
            if data[key]:
                data[key] = data[key].isoformat() if isinstance(data[key], datetime) else data[key]
        return data


@dataclass
class RotationConfig:
    """Configuration for key rotation."""

    rotation_interval_days: int = 730  # 2 years default
    warning_days: int = 60
    overlap_days: int = 30
    max_parallel_keys: int = 3
    auto_rotate: bool = True
    grace_period_days: int = 30  # After expiration, keep for verification


class VDSNCKeyGenerator:
    """Generate VDS-NC signer key pairs."""

    @staticmethod
    def generate_kid(country: str, role: KeyRole, generation: int, use_uuid: bool = False) -> str:
        """Generate Key ID.

        Args:
            country: ISO 3166-1 alpha-3 country code
            role: Key role/purpose
            generation: Rotation generation number
            use_uuid: Use UUID instead of deterministic format

        Returns:
            Key identifier string
        """
        if use_uuid:
            return str(uuid.uuid4())

        # Deterministic format: VDS-NC-{COUNTRY}-{ROLE}-{YEAR}-{GEN:02d}
        year = datetime.now(timezone.utc).year
        return f"VDS-NC-{country}-{role.value}-{year}-{generation:02d}"

    @staticmethod
    def generate_key_pair() -> tuple[EllipticCurvePrivateKey, EllipticCurvePublicKey]:
        """Generate ECDSA P-256 key pair for ES256.

        Returns:
            Tuple of (private_key, public_key)
        """
        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()
        return private_key, public_key

    @staticmethod
    def export_private_key_pem(private_key: EllipticCurvePrivateKey) -> str:
        """Export private key to PEM format."""
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return pem.decode("utf-8")

    @staticmethod
    def export_public_key_pem(public_key: EllipticCurvePublicKey) -> str:
        """Export public key to PEM format."""
        pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return pem.decode("utf-8")


class VDSNCKeyManager:
    """Manage VDS-NC signer keys lifecycle."""

    def __init__(
        self, session: AsyncSession, rotation_config: RotationConfig | None = None
    ) -> None:
        """Initialize key manager.

        Args:
            session: Database session
            rotation_config: Key rotation configuration
        """
        self.session = session
        self.rotation_config = rotation_config or RotationConfig()
        self.generator = VDSNCKeyGenerator()

    async def create_key(
        self,
        issuer_country: str,
        role: KeyRole,
        validity_days: int = 730,
        auto_activate: bool = False,
        hsm_key_id: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> tuple[str, VDSNCKeyMetadata]:
        """Create new VDS-NC signer key.

        Args:
            issuer_country: ISO 3166-1 alpha-3 country code
            role: Key role/purpose
            validity_days: Key validity period in days
            auto_activate: Activate key immediately
            hsm_key_id: HSM key reference if using HSM
            tags: Additional metadata tags

        Returns:
            Tuple of (kid, metadata)
        """
        # Get current generation number
        generation = await self._get_next_generation(issuer_country, role)

        # Generate KID
        kid = self.generator.generate_kid(issuer_country, role, generation)

        # Create metadata
        now = datetime.now(timezone.utc)
        metadata = VDSNCKeyMetadata(
            kid=kid,
            issuer_country=issuer_country,
            role=role,
            rotation_generation=generation,
            not_before=now,
            not_after=now + timedelta(days=validity_days),
            created_at=now,
            status=KeyStatus.ACTIVE if auto_activate else KeyStatus.PENDING,
            activated_at=now if auto_activate else None,
            hsm_key_id=hsm_key_id,
            tags=tags or {},
        )

        # Generate key pair
        if not hsm_key_id:
            private_key, public_key = self.generator.generate_key_pair()

            # Store keys (implementation depends on storage backend)
            await self._store_key_pair(kid, private_key, public_key, metadata)
        else:
            # HSM-backed key - just store metadata
            await self._store_metadata(metadata)

        logger.info(
            f"Created VDS-NC key {kid} for {issuer_country}/{role.value} (generation {generation})"
        )

        return kid, metadata

    async def activate_key(self, kid: str) -> bool:
        """Activate a pending key.

        Args:
            kid: Key identifier

        Returns:
            Success status
        """
        metadata = await self.get_key_metadata(kid)
        if not metadata:
            logger.error(f"Key {kid} not found")
            return False

        if metadata.status != KeyStatus.PENDING:
            logger.warning(f"Key {kid} is not in PENDING status: {metadata.status}")
            return False

        metadata.status = KeyStatus.ACTIVE
        metadata.activated_at = datetime.now(timezone.utc)

        await self._update_metadata(metadata)
        logger.info(f"Activated VDS-NC key {kid}")

        return True

    async def rotate_key(
        self,
        issuer_country: str,
        role: KeyRole,
        overlap_days: int | None = None,
        new_validity_days: int = 730,
    ) -> tuple[str, str, datetime]:
        """Rotate VDS-NC signer key.

        Args:
            issuer_country: ISO 3166-1 alpha-3 country code
            role: Key role to rotate
            overlap_days: Override default overlap period
            new_validity_days: Validity period for new key

        Returns:
            Tuple of (old_kid, new_kid, deprecation_date)
        """
        overlap_days = overlap_days or self.rotation_config.overlap_days

        # Get current active key
        old_keys = await self.list_keys(
            issuer_country=issuer_country, role=role, status=KeyStatus.ACTIVE
        )

        if not old_keys:
            msg = f"No active key found for {issuer_country}/{role.value}"
            raise ValueError(msg)

        old_metadata = old_keys[0]
        old_kid = old_metadata.kid

        # Create new key
        new_kid, new_metadata = await self.create_key(
            issuer_country=issuer_country,
            role=role,
            validity_days=new_validity_days,
            auto_activate=True,
            tags={"rotation_from": old_kid},
        )

        # Update old key to ROTATING status
        old_metadata.status = KeyStatus.ROTATING
        await self._update_metadata(old_metadata)

        # Calculate deprecation date
        deprecation_date = datetime.now(timezone.utc) + timedelta(days=overlap_days)

        logger.info(
            f"Rotating VDS-NC key {old_kid} → {new_kid} "
            f"(overlap until {deprecation_date.isoformat()})"
        )

        return old_kid, new_kid, deprecation_date

    async def deprecate_key(self, kid: str, reason: str | None = None) -> bool:
        """Deprecate a key (no longer use for signing).

        Args:
            kid: Key identifier
            reason: Deprecation reason

        Returns:
            Success status
        """
        metadata = await self.get_key_metadata(kid)
        if not metadata:
            return False

        metadata.status = KeyStatus.DEPRECATED
        metadata.deprecated_at = datetime.now(timezone.utc)
        if reason:
            metadata.tags["deprecation_reason"] = reason

        await self._update_metadata(metadata)
        logger.info(f"Deprecated VDS-NC key {kid}")

        return True

    async def revoke_key(self, kid: str, reason: str) -> bool:
        """Revoke a key (compromised or emergency).

        Args:
            kid: Key identifier
            reason: Revocation reason

        Returns:
            Success status
        """
        metadata = await self.get_key_metadata(kid)
        if not metadata:
            return False

        metadata.status = KeyStatus.REVOKED
        metadata.revoked_at = datetime.now(timezone.utc)
        metadata.revocation_reason = reason

        await self._update_metadata(metadata)
        logger.error(f"REVOKED VDS-NC key {kid}: {reason}")

        # TODO: Publish to revocation list/CRL equivalent

        return True

    async def get_key_metadata(self, kid: str) -> VDSNCKeyMetadata | None:
        """Get key metadata.

        Args:
            kid: Key identifier

        Returns:
            Key metadata or None
        """
        # Implementation depends on storage backend
        # This is a placeholder
        return None

    async def list_keys(
        self,
        issuer_country: str | None = None,
        role: KeyRole | None = None,
        status: KeyStatus | None = None,
        include_expired: bool = False,
    ) -> list[VDSNCKeyMetadata]:
        """List VDS-NC keys matching criteria.

        Args:
            issuer_country: Filter by country
            role: Filter by role
            status: Filter by status
            include_expired: Include expired keys

        Returns:
            List of key metadata
        """
        # Implementation depends on storage backend
        return []

    async def get_active_keys_for_verification(
        self, issuer_country: str, role: KeyRole
    ) -> list[VDSNCKeyMetadata]:
        """Get all keys valid for verification (active + rotating + grace period).

        Args:
            issuer_country: Country code
            role: Key role

        Returns:
            List of valid keys for verification
        """
        all_keys = await self.list_keys(issuer_country=issuer_country, role=role)

        now = datetime.now(timezone.utc)
        grace_period = timedelta(days=self.rotation_config.grace_period_days)

        valid_keys = []
        for metadata in all_keys:
            # Include active and rotating keys
            if metadata.status in [KeyStatus.ACTIVE, KeyStatus.ROTATING]:
                if metadata.not_before <= now <= metadata.not_after:
                    valid_keys.append(metadata)
                continue

            # Include deprecated keys within grace period
            if metadata.status == KeyStatus.DEPRECATED:
                if metadata.not_after + grace_period >= now:
                    valid_keys.append(metadata)
                continue

        return valid_keys

    async def check_rotation_needed(self) -> list[tuple[str, str, VDSNCKeyMetadata]]:
        """Check all keys and identify those needing rotation.

        Returns:
            List of (country, role, metadata) tuples needing rotation
        """
        all_keys = await self.list_keys(status=KeyStatus.ACTIVE)

        return [
            (metadata.issuer_country, metadata.role.value, metadata)
            for metadata in all_keys
            if metadata.needs_rotation(self.rotation_config.warning_days)
        ]

    async def _get_next_generation(self, issuer_country: str, role: KeyRole) -> int:
        """Get next generation number for key rotation."""
        existing_keys = await self.list_keys(
            issuer_country=issuer_country, role=role, include_expired=True
        )

        if not existing_keys:
            return 1

        max_gen = max(k.rotation_generation for k in existing_keys)
        return max_gen + 1

    async def _store_key_pair(
        self,
        kid: str,
        private_key: EllipticCurvePrivateKey,
        public_key: EllipticCurvePublicKey,
        metadata: VDSNCKeyMetadata,
    ) -> None:
        """Store key pair and metadata."""
        # Implementation depends on storage backend (database, key vault, HSM)
        # This is a placeholder

    async def _store_metadata(self, metadata: VDSNCKeyMetadata) -> None:
        """Store key metadata."""
        # Implementation depends on storage backend

    async def _update_metadata(self, metadata: VDSNCKeyMetadata) -> None:
        """Update key metadata."""
        # Implementation depends on storage backend


class VDSNCKeyDistributor:
    """Distribute VDS-NC public keys via PKD endpoints."""

    def __init__(self, key_manager: VDSNCKeyManager) -> None:
        """Initialize key distributor.

        Args:
            key_manager: Key manager instance
        """
        self.key_manager = key_manager

    async def get_jwks(
        self, issuer_country: str | None = None, role: KeyRole | None = None
    ) -> dict[str, Any]:
        """Get JSON Web Key Set (JWKS) for distribution.

        Args:
            issuer_country: Filter by country
            role: Filter by role

        Returns:
            JWKS document
        """
        # Get all valid keys for verification
        if issuer_country and role:
            keys_metadata = await self.key_manager.get_active_keys_for_verification(
                issuer_country, role
            )
        else:
            keys_metadata = await self.key_manager.list_keys(
                issuer_country=issuer_country,
                role=role,
                status=None,  # Get all that are valid
            )

        # Convert to JWK format
        jwks_keys = []
        for metadata in keys_metadata:
            if not metadata.is_valid_now():
                continue

            # Load public key
            public_key = await self._load_public_key(metadata.kid)
            if public_key:
                jwk = metadata.to_jwk(public_key)
                jwks_keys.append(jwk)

        return {
            "keys": jwks_keys,
            "metadata": {
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "total_count": len(jwks_keys),
                "country": issuer_country,
                "role": role.value if role else None,
            },
        }

    async def get_key_by_kid(self, kid: str) -> dict[str, Any] | None:
        """Get single key by KID.

        Args:
            kid: Key identifier

        Returns:
            Key in JWK format or None
        """
        metadata = await self.key_manager.get_key_metadata(kid)
        if not metadata or not metadata.is_valid_now():
            return None

        public_key = await self._load_public_key(kid)
        if not public_key:
            return None

        return metadata.to_jwk(public_key)

    async def _load_public_key(self, kid: str) -> EllipticCurvePublicKey | None:
        """Load public key from storage."""
        # Implementation depends on storage backend
        return None


# Example usage functions
async def example_key_lifecycle(session: AsyncSession) -> None:
    """Example of complete key lifecycle."""
    manager = VDSNCKeyManager(session)

    # 1. Create initial key
    kid, metadata = await manager.create_key(
        issuer_country="USA",
        role=KeyRole.CMC,
        validity_days=730,
        auto_activate=True,
        tags={"environment": "production", "hsm": "true"},
    )

    print(f"Created key: {kid}")
    print(f"Valid from {metadata.not_before} to {metadata.not_after}")

    # 2. Check if rotation needed (after some time)
    if metadata.needs_rotation(warning_days=60):
        print("Key needs rotation!")

        # Perform rotation
        old_kid, new_kid, deprecation_date = await manager.rotate_key(
            issuer_country="USA", role=KeyRole.CMC, overlap_days=30
        )

        print(f"Rotated: {old_kid} → {new_kid}")
        print(f"Overlap until: {deprecation_date}")

    # 3. Get keys for verification (includes overlap)
    valid_keys = await manager.get_active_keys_for_verification("USA", KeyRole.CMC)
    print(f"Keys valid for verification: {len(valid_keys)}")

    # 4. Distribute via JWKS
    distributor = VDSNCKeyDistributor(manager)
    jwks = await distributor.get_jwks(issuer_country="USA", role=KeyRole.CMC)
    print(f"JWKS document: {json.dumps(jwks, indent=2)}")


if __name__ == "__main__":
    # Example standalone usage (requires async context)
    import asyncio

    async def main() -> None:
        """Example main function."""
        # This would need actual database session
        # await example_key_lifecycle(session)

    asyncio.run(main())
