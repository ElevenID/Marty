"""VDS-NC key management service with database integration.

This service provides complete VDS-NC key lifecycle management including:
- Key generation and storage
- Rotation and supersession tracking
- Database persistence and retrieval
- JWKS distribution preparation
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import (
    EllipticCurvePrivateKey,
    EllipticCurvePublicKey,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from marty_common.crypto.vds_nc_keys import KeyRole, KeyStatus, VDSNCKeyMetadata
from marty_common.infrastructure.trust_models import KeyRotationLog, VDSNCKeyModel
from marty_common.security.encryption import SymmetricEncryption

logger = logging.getLogger(__name__)


class DatabaseVDSNCKeyManager:
    """Database-backed VDS-NC key management service."""

    def __init__(
        self,
        session: AsyncSession,
        encryption_service: SymmetricEncryption | None = None,
    ) -> None:
        """Initialize key manager.

        Args:
            session: Database session
            encryption_service: Optional encryption service for private keys
        """
        self.session = session
        self.encryption_service = encryption_service
        self.logger = logging.getLogger(__name__)

    async def generate_key_pair(
        self,
        kid: str,
        issuer_country: str,
        role: KeyRole,
        validity_days: int = 730,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[EllipticCurvePrivateKey, EllipticCurvePublicKey]:
        """Generate new VDS-NC key pair."""
        self.logger.info(f"Generating VDS-NC key pair: {kid}")

        # Generate EC P-256 key pair
        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()

        # Store in database
        await self._store_key_pair(
            kid=kid,
            private_key=private_key,
            public_key=public_key,
            issuer_country=issuer_country,
            role=role,
            validity_days=validity_days,
            metadata=metadata or {},
        )

        # Log generation
        await self._log_key_action(
            action="created",
            key_id=kid,
            issuer_country=issuer_country,
            reason=f"Generated new {role.value} key for {issuer_country}",
        )

        return private_key, public_key

    async def rotate_key(
        self,
        old_kid: str,
        new_kid: str,
        overlap_days: int = 30,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[EllipticCurvePrivateKey, EllipticCurvePublicKey]:
        """Rotate VDS-NC key with overlap period."""
        self.logger.info(f"Rotating VDS-NC key: {old_kid} -> {new_kid}")

        # Get old key info
        old_key = await self.get_key_by_kid(old_kid)
        if not old_key:
            msg = f"Old key not found: {old_kid}"
            raise ValueError(msg)

        # Generate new key pair
        private_key, public_key = await self.generate_key_pair(
            kid=new_kid,
            issuer_country=old_key.issuer_country,
            role=old_key.role,
            metadata=metadata,
        )

        # Update supersession relationships
        await self._update_supersession(old_kid, new_kid, overlap_days)

        # Log rotation
        await self._log_key_action(
            action="rotated",
            key_id=new_kid,
            old_key_id=old_kid,
            issuer_country=old_key.issuer_country,
            reason=f"Key rotation with {overlap_days} day overlap",
        )

        return private_key, public_key

    async def revoke_key(
        self,
        kid: str,
        reason: str,
        immediate: bool = False,
    ) -> bool:
        """Revoke VDS-NC key."""
        self.logger.warning(f"Revoking VDS-NC key: {kid}, reason: {reason}")

        try:
            # Get existing key
            result = await self.session.execute(
                select(VDSNCKeyModel).where(VDSNCKeyModel.kid == kid)
            )
            key_model = result.scalar_one_or_none()

            if not key_model:
                self.logger.error(f"Key not found for revocation: {kid}")
                return False

            # Update status and revocation info
            key_model.status = KeyStatus.REVOKED
            key_model.revoked_at = datetime.now(timezone.utc)
            key_model.revocation_reason = reason

            if immediate:
                # Immediate revocation - set not_after to now
                key_model.not_after = datetime.now(timezone.utc)

            # Disable distribution
            key_model.distribution_enabled = False

            await self.session.commit()

            # Log revocation
            await self._log_key_action(
                action="revoked",
                key_id=kid,
                issuer_country=key_model.issuer_country,
                reason=reason,
                metadata={"immediate": immediate},
            )

        except Exception:
            self.logger.exception("Error revoking key")
            await self.session.rollback()
            return False
        else:
            return True

    async def get_key_by_kid(self, kid: str) -> VDSNCKeyModel | None:
        """Get key by KID."""
        result = await self.session.execute(select(VDSNCKeyModel).where(VDSNCKeyModel.kid == kid))
        return result.scalar_one_or_none()

    async def list_keys(
        self,
        issuer_country: str | None = None,
        role: KeyRole | None = None,
        status: KeyStatus | None = None,
        include_private: bool = False,
    ) -> list[VDSNCKeyModel]:
        """List VDS-NC keys with filtering."""
        query = select(VDSNCKeyModel)

        if issuer_country:
            query = query.where(VDSNCKeyModel.issuer_country == issuer_country)
        if role:
            query = query.where(VDSNCKeyModel.role == role)
        if status:
            query = query.where(VDSNCKeyModel.status == status)

        # Default to only active keys if no status specified
        if status is None:
            query = query.where(VDSNCKeyModel.status == KeyStatus.ACTIVE)

        # Order by creation time
        query = query.order_by(VDSNCKeyModel.created_at.desc())

        result = await self.session.execute(query)
        keys = result.scalars().all()

        if not include_private:
            # Clear private key data for security
            for key in keys:
                key.private_key_encrypted = None

        return list(keys)

    async def get_active_keys_for_verification(
        self,
        timestamp: datetime | None = None,
    ) -> list[VDSNCKeyModel]:
        """Get keys that are valid for verification at given timestamp."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        query = select(VDSNCKeyModel).where(
            VDSNCKeyModel.status == KeyStatus.ACTIVE,
            VDSNCKeyModel.is_trusted is True,
            VDSNCKeyModel.distribution_enabled is True,
            VDSNCKeyModel.not_before <= timestamp,
            VDSNCKeyModel.not_after >= timestamp,
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_expiring_keys(
        self,
        warning_days: int = 30,
    ) -> list[VDSNCKeyModel]:
        """Get keys expiring within warning period."""
        warning_date = datetime.now(timezone.utc) + timedelta(days=warning_days)

        query = select(VDSNCKeyModel).where(
            VDSNCKeyModel.status == KeyStatus.ACTIVE,
            VDSNCKeyModel.not_after <= warning_date,
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_jwks_for_distribution(
        self,
        issuer_country: str | None = None,
        role: KeyRole | None = None,
    ) -> dict[str, Any]:
        """Get JWKS format for PKD distribution."""
        keys = await self.list_keys(
            issuer_country=issuer_country,
            role=role,
            status=KeyStatus.ACTIVE,
        )

        jwks_keys = []
        for key_model in keys:
            if key_model.distribution_enabled and key_model.is_valid_now():
                # Get public key from JWK
                jwk = key_model.public_key_jwk.copy()

                # Add metadata
                jwk.update(
                    {
                        "kid": key_model.kid,
                        "use": "sig",
                        "alg": key_model.algorithm,
                        "country": key_model.issuer_country,
                        "role": key_model.role.value,
                        "nbf": int(key_model.not_before.timestamp()),
                        "exp": int(key_model.not_after.timestamp()),
                    }
                )

                jwks_keys.append(jwk)

        return {
            "keys": jwks_keys,
            "metadata": {
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "total_count": len(jwks_keys),
                "country_filter": issuer_country,
                "role_filter": role.value if role else None,
            },
        }

    async def get_private_key(self, kid: str) -> EllipticCurvePrivateKey | None:
        """Get private key for signing (requires encryption service)."""
        if not self.encryption_service:
            msg = "Encryption service required for private key access"
            raise ValueError(msg)

        key_model = await self.get_key_by_kid(kid)
        if not key_model or not key_model.private_key_encrypted:
            return None

        try:
            # Decrypt private key
            private_key_pem = self.encryption_service.decrypt(key_model.private_key_encrypted)

            # Load private key
            private_key = serialization.load_pem_private_key(
                private_key_pem.encode(),
                password=None,
            )

            if isinstance(private_key, EllipticCurvePrivateKey):
                return private_key

        except Exception:
            self.logger.exception(f"Error loading private key {kid}")
            return None
        else:
            return None

    async def schedule_rotation(
        self,
        kid: str,
        rotation_date: datetime,
        new_kid: str | None = None,
        overlap_days: int = 30,
    ) -> bool:
        """Schedule future key rotation."""
        key_model = await self.get_key_by_kid(kid)
        if not key_model:
            return False

        # Generate new KID if not provided
        if not new_kid:
            new_kid = self._generate_kid(
                key_model.issuer_country,
                key_model.role,
                key_model.rotation_generation + 1,
            )

        # Log scheduled rotation
        await self._log_key_action(
            action="scheduled_rotation",
            key_id=new_kid,
            old_key_id=kid,
            issuer_country=key_model.issuer_country,
            reason=f"Scheduled rotation for {rotation_date.isoformat()}",
            scheduled_at=rotation_date,
            metadata={
                "overlap_days": overlap_days,
                "auto_generated_kid": new_kid,
            },
        )

        return True

    # Helper methods
    async def _store_key_pair(
        self,
        kid: str,
        private_key: EllipticCurvePrivateKey,
        public_key: EllipticCurvePublicKey,
        issuer_country: str,
        role: KeyRole,
        validity_days: int,
        metadata: dict[str, Any],
    ) -> None:
        """Store key pair in database."""
        now = datetime.now(timezone.utc)

        # Convert public key to JWK
        public_jwk = self._public_key_to_jwk(public_key)

        # Encrypt private key if encryption service available
        private_key_encrypted = None
        if self.encryption_service:
            private_key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            private_key_encrypted = self.encryption_service.encrypt(private_key_pem.decode())

        # Create model
        key_model = VDSNCKeyModel(
            kid=kid,
            issuer_country=issuer_country,
            role=role,
            status=KeyStatus.ACTIVE,
            algorithm="ES256",
            not_before=now,
            not_after=now + timedelta(days=validity_days),
            rotation_generation=1,
            public_key_jwk=public_jwk,
            private_key_encrypted=private_key_encrypted,
            custom_metadata=metadata,
            is_trusted=True,
            distribution_enabled=True,
        )

        self.session.add(key_model)
        await self.session.commit()

    async def _update_supersession(
        self,
        old_kid: str,
        new_kid: str,
        overlap_days: int,
    ) -> None:
        """Update key supersession relationships."""
        # Get both keys
        old_key = await self.get_key_by_kid(old_kid)
        new_key = await self.get_key_by_kid(new_kid)

        if not old_key or not new_key:
            msg = "Both keys must exist for supersession"
            raise ValueError(msg)

        # Update supersession links
        old_key.superseded_by = new_kid
        new_key.supersedes = old_kid

        # Update old key status and validity
        if overlap_days > 0:
            # Keep old key active during overlap
            overlap_end = datetime.now(timezone.utc) + timedelta(days=overlap_days)
            old_key.not_after = min(old_key.not_after, overlap_end)
            old_key.status = KeyStatus.DEPRECATED
        else:
            # Immediate supersession
            old_key.status = KeyStatus.DEPRECATED
            old_key.not_after = datetime.now(timezone.utc)
            old_key.distribution_enabled = False

        # Update rotation generation
        new_key.rotation_generation = old_key.rotation_generation + 1

        await self.session.commit()

    async def _log_key_action(
        self,
        action: str,
        key_id: str,
        issuer_country: str,
        reason: str,
        old_key_id: str | None = None,
        new_key_id: str | None = None,
        scheduled_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log key management action."""
        log_entry = KeyRotationLog(
            key_type="vds_nc",
            key_id=key_id,
            issuer_country=issuer_country,
            action=action,
            old_key_id=old_key_id,
            new_key_id=new_key_id,
            scheduled_at=scheduled_at,
            reason=reason,
            status="completed",
            metadata=metadata or {},
        )

        self.session.add(log_entry)
        await self.session.commit()

    def _public_key_to_jwk(self, public_key: EllipticCurvePublicKey) -> dict[str, Any]:
        """Convert EC public key to JWK format."""
        numbers = public_key.public_numbers()

        # Get coordinate bytes (32 bytes each for P-256)
        x_bytes = numbers.x.to_bytes(32, "big")
        y_bytes = numbers.y.to_bytes(32, "big")

        # Base64url encode
        import base64

        x_b64 = base64.urlsafe_b64encode(x_bytes).decode().rstrip("=")
        y_b64 = base64.urlsafe_b64encode(y_bytes).decode().rstrip("=")

        return {
            "kty": "EC",
            "crv": "P-256",
            "x": x_b64,
            "y": y_b64,
        }

    def _generate_kid(
        self,
        issuer_country: str,
        role: KeyRole,
        generation: int,
    ) -> str:
        """Generate KID for key."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"{issuer_country}_{role.value}_{generation:03d}_{timestamp}"

    # Legacy compatibility methods
    async def get_key_metadata(self, kid: str) -> VDSNCKeyMetadata | None:
        """Get key metadata (compatibility method)."""
        key_model = await self.get_key_by_kid(kid)
        if not key_model:
            return None

        # Convert to legacy metadata format
        return VDSNCKeyMetadata(
            kid=key_model.kid,
            issuer_country=key_model.issuer_country,
            role=key_model.role,
            status=key_model.status,
            algorithm=key_model.algorithm,
            not_before=key_model.not_before,
            not_after=key_model.not_after,
            rotation_generation=key_model.rotation_generation,
            custom_metadata=key_model.custom_metadata,
        )


class VDSNCKeyRepository:
    """Repository for VDS-NC key database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_kid(self, kid: str) -> VDSNCKeyModel | None:
        """Get key by KID."""
        result = await self.session.execute(select(VDSNCKeyModel).where(VDSNCKeyModel.kid == kid))
        return result.scalar_one_or_none()

    async def list_by_country_and_role(
        self,
        country: str,
        role: KeyRole,
        status: KeyStatus | None = None,
    ) -> list[VDSNCKeyModel]:
        """List keys by country and role."""
        query = select(VDSNCKeyModel).where(
            VDSNCKeyModel.issuer_country == country,
            VDSNCKeyModel.role == role,
        )

        if status:
            query = query.where(VDSNCKeyModel.status == status)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_rotation_history(
        self,
        country: str,
        role: KeyRole | None = None,
    ) -> list[KeyRotationLog]:
        """Get key rotation history."""
        query = select(KeyRotationLog).where(
            KeyRotationLog.key_type == "vds_nc",
            KeyRotationLog.issuer_country == country,
        )

        if role:
            # Filter by role in metadata or key_id pattern
            pass  # Would need more complex filtering

        query = query.order_by(KeyRotationLog.executed_at.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())
