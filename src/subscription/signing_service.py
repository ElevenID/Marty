"""
Signing Service with Tier-Based Key Vault Access

Manages cryptographic signing operations with subscription tier enforcement:
- FREE tier: Uses service-provided key vault with weekly rotation
- DEVS tier: Uses service-provided key vault with biweekly rotation
- STARTER, PROFESSIONAL, ENTERPRISE tiers: Remote signing with customer KMS
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from marty_backend_common.infrastructure.key_vault import KeyVaultClient

from .models import Organization, Subscription
from .square_service import PLAN_LIMITS, SquarePlan

if TYPE_CHECKING:
    from .remote_signing_service import RemoteSigningService

logger = logging.getLogger(__name__)


class SigningKeyType(str, Enum):
    """Types of signing keys."""
    SERVICE_MANAGED = "service_managed"  # Service key vault (DEVS tier only)
    REMOTE = "remote"  # Remote signing with customer's keys


@dataclass
class SigningKeyInfo:
    """Information about a signing key."""
    key_id: str
    organization_id: UUID
    key_type: SigningKeyType
    created_at: datetime
    last_rotated_at: Optional[datetime]
    rotation_required: bool
    algorithm: str


class SigningError(Exception):
    """Base exception for signing errors."""
    pass


class UnauthorizedKeyVaultAccess(SigningError):
    """Raised when tier doesn't allow service key vault access."""
    pass


class KeyRotationRequired(SigningError):
    """Raised when key rotation is overdue."""
    pass


class RemoteSigningRequired(SigningError):
    """Raised when tier requires remote signing."""
    pass


class SigningService:
    """
    Manages signing operations with tier-based access control.
    
    FREE tier:
    - Can use service key vault
    - Keys rotated weekly (every 7 days)
    - Service manages key lifecycle
    
    DEVS tier:
    - Can use service key vault
    - Keys rotated biweekly (every 14 days)
    - Service manages key lifecycle
    
    STARTER, PROFESSIONAL, ENTERPRISE tiers:
    - Must use remote signing with their own KMS/HSM
    - Service never has access to private keys
    - Keys managed by organization
    """
    
    # Key rotation intervals per tier
    FREE_ROTATION_DAYS = 7   # Weekly rotation for FREE tier
    DEVS_ROTATION_DAYS = 14  # Biweekly rotation for DEVS tier
    
    def __init__(
        self,
        db: AsyncSession,
        service_key_vault: Optional[KeyVaultClient] = None,
        remote_signing_service: Optional["RemoteSigningService"] = None,
    ):
        """
        Initialize signing service.
        
        Args:
            db: Database session
            service_key_vault: Service provider's key vault (for FREE/DEVS tiers)
            remote_signing_service: Remote signing service (for production tiers)
        """
        self.db = db
        self.service_key_vault = service_key_vault
        self.remote_signing_service = remote_signing_service
        # In-memory tracking of key rotation (in production, use database)
        self._key_rotation_tracker: dict[str, datetime] = {}
    
    async def get_subscription(self, organization: Organization) -> Optional[Subscription]:
        """Get active subscription for organization."""
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.organization_id == organization.id,
                Subscription.status == "active",
            )
        )
        return result.scalar_one_or_none()
    
    def can_use_service_key_vault(self, plan: SquarePlan) -> bool:
        """Check if subscription tier allows service key vault usage."""
        limits = PLAN_LIMITS.get(plan)
        return limits.can_use_service_key_vault if limits else False
    
    def requires_remote_signing(self, plan: SquarePlan) -> bool:
        """Check if subscription tier requires remote signing."""
        limits = PLAN_LIMITS.get(plan)
        return limits.requires_remote_signing if limits else True
    
    async def ensure_signing_key(
        self,
        organization: Organization,
        key_id: str,
        algorithm: str = "ecdsa-p256",
    ) -> SigningKeyInfo:
        """
        Ensure a signing key exists for the organization.
        
        Args:
            organization: Organization requesting the key
            key_id: Unique identifier for the key
            algorithm: Cryptographic algorithm (default: ecdsa-p256)
        
        Returns:
            SigningKeyInfo with key details
        
        Raises:
            UnauthorizedKeyVaultAccess: If tier doesn't allow service key vault
            RemoteSigningRequired: If tier requires remote signing
        """
        subscription = await self.get_subscription(organization)
        if not subscription:
            raise SigningError("No active subscription found")
        
        plan = SquarePlan(subscription.plan)
        
        # Check if this tier can use service key vault
        if not self.can_use_service_key_vault(plan):
            if self.requires_remote_signing(plan):
                raise RemoteSigningRequired(
                    f"Tier '{plan.value}' requires remote signing with your own keys"
                )
            raise UnauthorizedKeyVaultAccess(
                f"Tier '{plan.value}' cannot use service key vault"
            )
        
        # DEVS tier - use service key vault
        if not self.service_key_vault:
            raise SigningError("Service key vault not configured")
        
        # Generate organization-scoped key ID
        org_key_id = f"org-{organization.id}-{key_id}"
        
        # Ensure key exists in vault
        await self.service_key_vault.ensure_key(org_key_id, algorithm)
        
        # Track creation/rotation
        now = datetime.now(timezone.utc)
        if org_key_id not in self._key_rotation_tracker:
            self._key_rotation_tracker[org_key_id] = now
        
        last_rotated = self._key_rotation_tracker[org_key_id]
        rotation_required = self._check_rotation_required(last_rotated, plan)
        
        return SigningKeyInfo(
            key_id=org_key_id,
            organization_id=organization.id,
            key_type=SigningKeyType.SERVICE_MANAGED,
            created_at=now,
            last_rotated_at=last_rotated,
            rotation_required=rotation_required,
            algorithm=algorithm,
        )
    
    def _check_rotation_required(self, last_rotated: datetime, plan: SquarePlan) -> bool:
        """Check if key rotation is required based on plan."""
        # Determine rotation period based on plan
        if plan == SquarePlan.SANDBOX:
            rotation_days = self.FREE_ROTATION_DAYS
        elif plan == SquarePlan.PROGRAM:
            rotation_days = self.DEVS_ROTATION_DAYS
        else:
            # Other tiers use remote signing, no rotation required
            return False
        
        days_since_rotation = (datetime.now(timezone.utc) - last_rotated).days
        return days_since_rotation >= rotation_days
    
    async def rotate_key(
        self,
        organization: Organization,
        key_id: str,
        algorithm: str = "ecdsa-p256",
    ) -> SigningKeyInfo:
        """
        Rotate a signing key (DEVS tier only).
        
        Args:
            organization: Organization owning the key
            key_id: Key identifier to rotate
            algorithm: Cryptographic algorithm
        
        Returns:
            SigningKeyInfo for the new key
        
        Raises:
            UnauthorizedKeyVaultAccess: If tier doesn't allow service key vault
        """
        subscription = await self.get_subscription(organization)
        if not subscription:
            raise SigningError("No active subscription found")
        
        plan = SquarePlan(subscription.plan)
        
        if not self.can_use_service_key_vault(plan):
            raise UnauthorizedKeyVaultAccess(
                f"Tier '{plan.value}' cannot rotate service keys"
            )
        
        if not self.service_key_vault:
            raise SigningError("Service key vault not configured")
        
        # Generate new key ID with version
        org_key_id = f"org-{organization.id}-{key_id}"
        new_key_id = f"{org_key_id}-v{uuid4().hex[:8]}"
        
        # Create new key
        await self.service_key_vault.ensure_key(new_key_id, algorithm)
        
        # Update rotation tracker
        now = datetime.now(timezone.utc)
        self._key_rotation_tracker[new_key_id] = now
        
        logger.info(
            f"Rotated signing key for org {organization.id}, "
            f"old_key={org_key_id}, new_key={new_key_id}"
        )
        
        return SigningKeyInfo(
            key_id=new_key_id,
            organization_id=organization.id,
            key_type=SigningKeyType.SERVICE_MANAGED,
            created_at=now,
            last_rotated_at=now,
            rotation_required=False,
            algorithm=algorithm,
        )
    
    async def sign(
        self,
        organization: Organization,
        key_id: str,
        payload: bytes,
        algorithm: str = "ecdsa-p256",
        force_rotation_check: bool = True,
    ) -> bytes:
        """
        Sign payload with organization's key.
        
        Routes to appropriate signing method based on subscription tier:
        - FREE/DEVS: Service key vault with rotation enforcement
        - STARTER, PROFESSIONAL, ENTERPRISE: Remote signing with customer's KMS/HSM
        
        Args:
            organization: Organization performing the signing
            key_id: Key identifier
            payload: Data to sign
            algorithm: Cryptographic algorithm
            force_rotation_check: Enforce rotation requirements (service vault only)
        
        Returns:
            Signature bytes
        
        Raises:
            KeyRotationRequired: If key rotation is overdue (FREE/DEVS)
            RemoteSigningRequired: If tier requires remote signing but not configured
            SigningError: If signing fails
        """
        subscription = await self.get_subscription(organization)
        if not subscription:
            raise SigningError("No active subscription found")
        
        plan = SquarePlan(subscription.plan)
        
        # Route to appropriate signing method
        if self.requires_remote_signing(plan):
            # Production tier - use customer's KMS
            if not self.remote_signing_service:
                raise RemoteSigningRequired(
                    f"Tier '{plan.value}' requires remote signing. "
                    "Configure your KMS/HSM to enable signing operations."
                )
            
            return await self.remote_signing_service.sign(
                organization=organization,
                key_id=key_id,
                payload=payload,
                algorithm=algorithm,
            )
        
        else:
            # FREE/DEVS tier - use service key vault
            return await self._sign_with_service_vault(
                organization=organization,
                plan=plan,
                key_id=key_id,
                payload=payload,
                algorithm=algorithm,
                force_rotation_check=force_rotation_check,
            )
    
    async def _sign_with_service_vault(
        self,
        organization: Organization,
        plan: SquarePlan,
        key_id: str,
        payload: bytes,
        algorithm: str,
        force_rotation_check: bool,
    ) -> bytes:
        """
        Sign using service key vault (FREE/DEVS only).
        
        Internal method - use sign() instead.
        """
        if not self.service_key_vault:
            raise SigningError("Service key vault not configured")
        
        org_key_id = f"org-{organization.id}-{key_id}"
        
        # Check rotation status
        if force_rotation_check and org_key_id in self._key_rotation_tracker:
            last_rotated = self._key_rotation_tracker[org_key_id]
            if self._check_rotation_required(last_rotated, plan):
                # Determine rotation period for error message
                rotation_days = self.FREE_ROTATION_DAYS if plan == SquarePlan.SANDBOX else self.DEVS_ROTATION_DAYS
                tier_name = "SANDBOX" if plan == SquarePlan.SANDBOX else "PROGRAM"
                raise KeyRotationRequired(
                    f"Key rotation required (last rotated: {last_rotated.date()}). "
                    f"Keys must be rotated every {rotation_days} days for {tier_name} tier."
                )
        
        # Perform signing
        signature = await self.service_key_vault.sign(org_key_id, payload, algorithm)
        
        logger.info(f"Signed payload for org {organization.id} with key {org_key_id} (service vault)")
        
        return signature
    
    async def get_key_info(
        self,
        organization: Organization,
        key_id: str,
    ) -> Optional[SigningKeyInfo]:
        """
        Get information about a signing key.
        
        Args:
            organization: Organization owning the key
            key_id: Key identifier
        
        Returns:
            SigningKeyInfo if key exists, None otherwise
        """
        subscription = await self.get_subscription(organization)
        if not subscription:
            return None
        
        plan = SquarePlan(subscription.plan)
        org_key_id = f"org-{organization.id}-{key_id}"
        
        if org_key_id not in self._key_rotation_tracker:
            return None
        
        last_rotated = self._key_rotation_tracker[org_key_id]
        rotation_required = self._check_rotation_required(last_rotated, plan)
        
        return SigningKeyInfo(
            key_id=org_key_id,
            organization_id=organization.id,
            key_type=SigningKeyType.SERVICE_MANAGED,
            created_at=last_rotated,  # Using last_rotated as proxy for created_at
            last_rotated_at=last_rotated,
            rotation_required=rotation_required,
            algorithm="ecdsa-p256",  # Default
        )
