"""
Device Registry

Manages device registrations for push notifications.
Stores FCM tokens and device metadata.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, LargeBinary, String, Text, and_, select
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for device registry models."""
    pass


class DeviceRegistration(Base):
    """
    Device registration for push notifications.
    
    Stores FCM tokens and device metadata for each user's device.
    """
    __tablename__ = "device_registrations"
    
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    
    # Owner
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    organization_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    
    # Device identification
    device_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)  # ios, android, web
    
    # Push token
    fcm_token: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Device metadata
    app_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    os_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    device_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Notification preferences
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    
    # RSA public key for challenge signature verification
    # Stored as base64-encoded DER (PKCS#1 format)
    public_key_der: Mapped[Optional[bytes]] = mapped_column(
        LargeBinary,
        nullable=True,
        comment="Base64-decoded RSA public key in PKCS#1 DER format",
    )
    # Key ID is SHA-256 thumbprint of public key DER (RFC 7638)
    public_key_kid: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="SHA-256 thumbprint of public key for key identification",
    )
    # Key validity window for rotation support
    key_valid_from: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this key became valid",
    )
    key_valid_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this key expires (for rotation grace period)",
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


@dataclass
class DeviceInfo:
    """Device information for registration."""
    device_id: str
    platform: str
    fcm_token: str
    app_version: Optional[str] = None
    os_version: Optional[str] = None
    device_model: Optional[str] = None
    preferences: Optional[dict] = None
    # RSA public key in base64-encoded PKCS#1 DER format
    public_key: Optional[str] = None


def compute_key_id(public_key_der: bytes) -> str:
    """
    Compute key ID as SHA-256 thumbprint of public key DER.
    
    Per RFC 7638, this provides a stable identifier for key rotation.
    Returns first 16 hex characters of SHA-256 hash.
    """
    import hashlib
    return hashlib.sha256(public_key_der).hexdigest()[:16]


class DeviceRegistry:
    """
    Device registry for managing push notification tokens.
    
    Features:
    - Register/unregister devices
    - Update FCM tokens
    - Query devices by user/organization
    - Automatic token cleanup
    """
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def register_device(
        self,
        user_id: str,
        device_info: DeviceInfo,
        organization_id: Optional[UUID] = None,
    ) -> DeviceRegistration:
        """
        Register a device for push notifications.
        
        If the device already exists, updates the FCM token.
        
        Args:
            user_id: User identifier
            device_info: Device information
            organization_id: Optional organization ID
            
        Returns:
            DeviceRegistration record
        """
        # Check for existing registration
        result = await self.db.execute(
            select(DeviceRegistration).where(
                and_(
                    DeviceRegistration.user_id == user_id,
                    DeviceRegistration.device_id == device_info.device_id,
                )
            )
        )
        existing = result.scalar_one_or_none()
        
        now = datetime.now(timezone.utc)
        
        # Decode public key if provided
        public_key_der = None
        public_key_kid = None
        if device_info.public_key:
            import base64
            try:
                public_key_der = base64.b64decode(device_info.public_key)
                public_key_kid = compute_key_id(public_key_der)
            except Exception as e:
                logger.warning(f"Failed to decode public key: {e}")
        
        if existing:
            # Update existing registration
            existing.fcm_token = device_info.fcm_token
            existing.platform = device_info.platform
            existing.app_version = device_info.app_version
            existing.os_version = device_info.os_version
            existing.device_model = device_info.device_model
            if device_info.preferences:
                existing.preferences = device_info.preferences
            # Update public key if provided
            if public_key_der:
                existing.public_key_der = public_key_der
                existing.public_key_kid = public_key_kid
                existing.key_valid_from = now
                existing.key_valid_until = None  # No expiration until rotated
            existing.updated_at = now
            existing.last_seen_at = now
            existing.is_active = True
            
            await self.db.commit()
            await self.db.refresh(existing)
            
            logger.info(f"Updated device registration {existing.id}")
            return existing
        
        # Create new registration
        registration = DeviceRegistration(
            id=uuid4(),
            user_id=user_id,
            organization_id=organization_id,
            device_id=device_info.device_id,
            platform=device_info.platform,
            fcm_token=device_info.fcm_token,
            app_version=device_info.app_version,
            os_version=device_info.os_version,
            device_model=device_info.device_model,
            preferences=device_info.preferences or {},
            public_key_der=public_key_der,
            public_key_kid=public_key_kid,
            key_valid_from=now if public_key_der else None,
            is_active=True,
            created_at=now,
            last_seen_at=now,
        )
        
        self.db.add(registration)
        await self.db.commit()
        await self.db.refresh(registration)
        
        logger.info(f"Created device registration {registration.id} for user {user_id}")
        return registration
    
    async def unregister_device(
        self,
        user_id: str,
        device_id: str,
    ) -> bool:
        """
        Unregister a device.
        
        Args:
            user_id: User identifier
            device_id: Device identifier
            
        Returns:
            True if device was found and unregistered
        """
        result = await self.db.execute(
            select(DeviceRegistration).where(
                and_(
                    DeviceRegistration.user_id == user_id,
                    DeviceRegistration.device_id == device_id,
                )
            )
        )
        registration = result.scalar_one_or_none()
        
        if not registration:
            return False
        
        registration.is_active = False
        registration.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        
        logger.info(f"Unregistered device {device_id} for user {user_id}")
        return True
    
    async def get_user_devices(
        self,
        user_id: str,
        organization_id: Optional[UUID] = None,
        active_only: bool = True,
    ) -> list[DeviceRegistration]:
        """
        Get all devices for a user.
        
        Args:
            user_id: User identifier
            organization_id: Optional organization filter
            active_only: Only return active devices
            
        Returns:
            List of DeviceRegistration records
        """
        query = select(DeviceRegistration).where(
            DeviceRegistration.user_id == user_id
        )
        
        if organization_id:
            query = query.where(DeviceRegistration.organization_id == organization_id)
        
        if active_only:
            query = query.where(DeviceRegistration.is_active == True)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_organization_devices(
        self,
        organization_id: UUID,
        active_only: bool = True,
    ) -> list[DeviceRegistration]:
        """
        Get all devices for an organization.
        
        Args:
            organization_id: Organization identifier
            active_only: Only return active devices
            
        Returns:
            List of DeviceRegistration records
        """
        query = select(DeviceRegistration).where(
            DeviceRegistration.organization_id == organization_id
        )
        
        if active_only:
            query = query.where(DeviceRegistration.is_active == True)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_fcm_tokens(
        self,
        user_id: Optional[str] = None,
        organization_id: Optional[UUID] = None,
    ) -> list[str]:
        """
        Get FCM tokens for push notification delivery.
        
        Args:
            user_id: Optional user filter
            organization_id: Optional organization filter
            
        Returns:
            List of FCM tokens
        """
        query = select(DeviceRegistration.fcm_token).where(
            DeviceRegistration.is_active == True
        )
        
        if user_id:
            query = query.where(DeviceRegistration.user_id == user_id)
        
        if organization_id:
            query = query.where(DeviceRegistration.organization_id == organization_id)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def mark_token_invalid(self, fcm_token: str) -> None:
        """
        Mark a token as invalid (device unregistered from FCM).
        
        Called when FCM returns an invalid token error.
        
        Args:
            fcm_token: The invalid FCM token
        """
        result = await self.db.execute(
            select(DeviceRegistration).where(
                DeviceRegistration.fcm_token == fcm_token
            )
        )
        registration = result.scalar_one_or_none()
        
        if registration:
            registration.is_active = False
            registration.updated_at = datetime.now(timezone.utc)
            await self.db.commit()
            
            logger.info(f"Marked token as invalid for device {registration.device_id}")
    
    async def update_last_seen(
        self,
        user_id: str,
        device_id: str,
    ) -> None:
        """
        Update the last seen timestamp for a device.
        
        Args:
            user_id: User identifier
            device_id: Device identifier
        """
        result = await self.db.execute(
            select(DeviceRegistration).where(
                and_(
                    DeviceRegistration.user_id == user_id,
                    DeviceRegistration.device_id == device_id,
                    DeviceRegistration.is_active == True,
                )
            )
        )
        registration = result.scalar_one_or_none()
        
        if registration:
            registration.last_seen_at = datetime.now(timezone.utc)
            await self.db.commit()
    
    async def get_device_by_id(
        self,
        device_id: str,
    ) -> Optional[DeviceRegistration]:
        """
        Get a device registration by device ID.
        
        Args:
            device_id: Device identifier
            
        Returns:
            DeviceRegistration or None
        """
        result = await self.db.execute(
            select(DeviceRegistration).where(
                and_(
                    DeviceRegistration.device_id == device_id,
                    DeviceRegistration.is_active == True,
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def rotate_public_key(
        self,
        device_id: str,
        new_public_key: str,
        grace_period_days: int = 30,
    ) -> Optional[DeviceRegistration]:
        """
        Rotate the public key for a device.
        
        Sets the old key to expire after the grace period and activates
        the new key immediately. Both keys are valid during the grace period.
        
        Args:
            device_id: Device identifier
            new_public_key: New RSA public key in base64 PKCS#1 DER format
            grace_period_days: Days to keep old key valid (default 30)
            
        Returns:
            Updated DeviceRegistration or None if not found
        """
        import base64
        from datetime import timedelta
        
        result = await self.db.execute(
            select(DeviceRegistration).where(
                and_(
                    DeviceRegistration.device_id == device_id,
                    DeviceRegistration.is_active == True,
                )
            )
        )
        registration = result.scalar_one_or_none()
        
        if not registration:
            return None
        
        now = datetime.now(timezone.utc)
        
        try:
            new_key_der = base64.b64decode(new_public_key)
            new_key_kid = compute_key_id(new_key_der)
        except Exception as e:
            logger.error(f"Failed to decode new public key: {e}")
            return None
        
        # Set old key to expire after grace period
        # (In a more sophisticated system, we'd keep a key history table)
        registration.key_valid_until = now + timedelta(days=grace_period_days)
        
        # Activate new key
        registration.public_key_der = new_key_der
        registration.public_key_kid = new_key_kid
        registration.key_valid_from = now
        registration.key_valid_until = None  # New key has no expiration
        registration.updated_at = now
        
        await self.db.commit()
        await self.db.refresh(registration)
        
        logger.info(f"Rotated public key for device {device_id}, new kid: {new_key_kid}")
        return registration
    
    def is_key_valid(self, registration: DeviceRegistration, at_time: Optional[datetime] = None) -> bool:
        """
        Check if a device's public key is currently valid.
        
        Args:
            registration: Device registration to check
            at_time: Time to check validity for (default: now)
            
        Returns:
            True if key is valid
        """
        if not registration.public_key_der:
            return False
        
        check_time = at_time or datetime.now(timezone.utc)
        
        # Check key_valid_from
        if registration.key_valid_from and check_time < registration.key_valid_from:
            return False
        
        # Check key_valid_until
        if registration.key_valid_until and check_time >= registration.key_valid_until:
            return False
        
        return True
