"""
API Key Management Service

Provides secure API key generation, validation, and lifecycle management.
Supports scopes, IP allowlists, and rate limiting.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import APIKey, Organization, Subscription
from .square_service import PLAN_LIMITS, SquarePlan

logger = logging.getLogger(__name__)


# API key prefix for identification
API_KEY_PREFIX = "pk_"
API_KEY_BYTES = 32  # 256 bits of entropy

# Valid API key scopes
VALID_SCOPES = {
    "credentials:read",
    "credentials:write",
    "presentations:read",
    "presentations:write",
    "webhooks:read",
    "webhooks:write",
    "admin",
}


@dataclass
class APIKeyInfo:
    """Validated API key information."""
    key_id: UUID
    organization_id: UUID
    name: str
    scopes: list[str]
    rate_limit: int
    is_test: bool


@dataclass
class RateLimitResult:
    """Rate limit check result."""
    allowed: bool
    remaining: int
    reset_at: datetime
    retry_after: Optional[int] = None


class APIKeyService:
    """
    API Key management service.
    
    Features:
    - Secure key generation with SHA-256 hashing
    - Scope-based access control
    - IP allowlist validation
    - Integration with Redis for rate limiting
    """
    
    def __init__(
        self,
        db_session: AsyncSession,
        redis_client: Optional[object] = None,  # aioredis.Redis
    ):
        self.db = db_session
        self.redis = redis_client
    
    def generate_api_key(self, is_test: bool = False) -> tuple[str, str]:
        """
        Generate a new API key.
        
        Returns:
            Tuple of (full_key, key_hash) where:
            - full_key: The complete API key to give to the user (only shown once)
            - key_hash: SHA-256 hash to store in database
        """
        # Generate random bytes
        key_bytes = secrets.token_bytes(API_KEY_BYTES)
        key_suffix = secrets.token_urlsafe(API_KEY_BYTES)
        
        # Build full key with prefix
        mode = "test_" if is_test else "live_"
        full_key = f"{API_KEY_PREFIX}{mode}{key_suffix}"
        
        # Hash for storage
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        
        return full_key, key_hash
    
    async def create_api_key(
        self,
        organization: Organization,
        name: str,
        scopes: list[str],
        ip_allowlist: Optional[list[str]] = None,
        expires_at: Optional[datetime] = None,
        is_test: bool = False,
    ) -> tuple[APIKey, str]:
        """
        Create a new API key for an organization.
        
        Args:
            organization: The organization owning the key
            name: Human-readable name for the key
            scopes: List of permission scopes
            ip_allowlist: Optional list of allowed IP addresses/CIDRs
            expires_at: Optional expiration datetime
            is_test: Whether this is a test mode key
            
        Returns:
            Tuple of (APIKey record, raw_key) - raw_key is only available at creation
        """
        # Check subscription limits
        subscription = await self._get_active_subscription(organization.id)
        if subscription:
            limits = PLAN_LIMITS.get(SquarePlan(subscription.plan))
            if limits and limits.api_keys != -1:
                current_count = await self._count_api_keys(organization.id)
                if current_count >= limits.api_keys:
                    raise APIKeyLimitError(
                        f"API key limit reached ({limits.api_keys}). "
                        "Upgrade your plan for more keys."
                    )
        
        # Validate IP allowlist
        validated_ips: list[str] = []
        if ip_allowlist:
            for ip in ip_allowlist:
                try:
                    # Validate IP or CIDR
                    ipaddress.ip_network(ip, strict=False)
                    validated_ips.append(ip)
                except ValueError as e:
                    raise InvalidIPError(f"Invalid IP address: {ip}") from e
        
        # Generate key
        raw_key, key_hash = self.generate_api_key(is_test)
        
        # Create database record
        api_key = APIKey(
            id=uuid4(),
            organization_id=organization.id,
            name=name,
            key_hash=key_hash,
            key_prefix=raw_key[:16],  # Store prefix for identification
            scopes=scopes,
            ip_allowlist=validated_ips,
            is_test=is_test,
            expires_at=expires_at,
            last_used_at=None,
            created_at=datetime.now(timezone.utc),
        )
        
        self.db.add(api_key)
        await self.db.commit()
        await self.db.refresh(api_key)
        
        logger.info(f"Created API key {api_key.id} for org {organization.slug}")
        
        return api_key, raw_key
    
    async def validate_api_key(
        self,
        raw_key: str,
        required_scopes: Optional[list[str]] = None,
        client_ip: Optional[str] = None,
    ) -> APIKeyInfo:
        """
        Validate an API key and return its info.
        
        Args:
            raw_key: The full API key from the request
            required_scopes: Optional scopes that must be present
            client_ip: Optional client IP to validate against allowlist
            
        Returns:
            APIKeyInfo if valid
            
        Raises:
            InvalidAPIKeyError: If key is invalid, expired, or lacks permissions
        """
        # Validate format
        if not raw_key.startswith(API_KEY_PREFIX):
            raise InvalidAPIKeyError("Invalid API key format")
        
        # Hash the key
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        
        # Look up in database
        result = await self.db.execute(
            select(APIKey).where(
                and_(
                    APIKey.key_hash == key_hash,
                    APIKey.revoked_at.is_(None),
                )
            )
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            raise InvalidAPIKeyError("Invalid or revoked API key")
        
        # Check expiration
        if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
            raise InvalidAPIKeyError("API key has expired")
        
        # Check IP allowlist
        if client_ip and api_key.ip_allowlist:
            if not self._is_ip_allowed(client_ip, api_key.ip_allowlist):
                raise IPNotAllowedError(f"IP {client_ip} not in allowlist")
        
        # Check scopes
        if required_scopes:
            missing = set(required_scopes) - set(api_key.scopes)
            if missing:
                raise InsufficientScopesError(
                    f"Missing required scopes: {', '.join(missing)}"
                )
        
        # Update last used timestamp
        api_key.last_used_at = datetime.now(timezone.utc)
        await self.db.commit()
        
        # Get organization for rate limit info
        result = await self.db.execute(
            select(Organization).where(Organization.id == api_key.organization_id)
        )
        org = result.scalar_one_or_none()
        
        # Determine rate limit based on subscription
        rate_limit = 100  # Default
        if org:
            subscription = await self._get_active_subscription(org.id)
            if subscription:
                limits = PLAN_LIMITS.get(SquarePlan(subscription.plan))
                if limits:
                    # Calculate per-minute rate from monthly limit
                    if limits.api_calls_per_month == -1:
                        rate_limit = 10000  # High limit for unlimited plans
                    else:
                        rate_limit = max(100, limits.api_calls_per_month // (30 * 24 * 60))
        
        return APIKeyInfo(
            key_id=api_key.id,
            organization_id=api_key.organization_id,
            name=api_key.name,
            scopes=api_key.scopes,
            rate_limit=rate_limit,
            is_test=api_key.is_test,
        )
    
    async def check_rate_limit(
        self,
        key_info: APIKeyInfo,
        cost: int = 1,
    ) -> RateLimitResult:
        """
        Check and consume rate limit quota.
        
        Uses sliding window rate limiting with Redis.
        
        Args:
            key_info: Validated API key info
            cost: Number of units to consume (default 1)
            
        Returns:
            RateLimitResult with allowed status and remaining quota
        """
        if not self.redis:
            # No Redis, allow everything but log warning
            logger.warning("Rate limiting disabled - no Redis connection")
            return RateLimitResult(
                allowed=True,
                remaining=key_info.rate_limit,
                reset_at=datetime.now(timezone.utc),
            )
        
        # Sliding window rate limiting
        now = datetime.now(timezone.utc)
        window_key = f"ratelimit:{key_info.key_id}:{now.minute}"
        
        # Use Redis pipeline for atomic operations
        pipe = self.redis.pipeline()
        pipe.incr(window_key)
        pipe.expire(window_key, 120)  # Keep for 2 minutes
        results = await pipe.execute()
        
        current_count = results[0]
        
        if current_count > key_info.rate_limit:
            retry_after = 60 - now.second
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=now.replace(second=0, microsecond=0),
                retry_after=retry_after,
            )
        
        return RateLimitResult(
            allowed=True,
            remaining=key_info.rate_limit - current_count,
            reset_at=now.replace(second=0, microsecond=0),
        )
    
    async def revoke_api_key(
        self,
        key_id: UUID,
        organization_id: UUID,
    ) -> None:
        """
        Revoke an API key.
        
        Args:
            key_id: The API key ID
            organization_id: The owning organization (for authorization)
        """
        result = await self.db.execute(
            select(APIKey).where(
                and_(
                    APIKey.id == key_id,
                    APIKey.organization_id == organization_id,
                )
            )
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            raise InvalidAPIKeyError("API key not found")
        
        api_key.revoked_at = datetime.now(timezone.utc)
        await self.db.commit()
        
        logger.info(f"Revoked API key {key_id}")
    
    async def list_api_keys(
        self,
        organization_id: UUID,
        include_revoked: bool = False,
    ) -> list[APIKey]:
        """
        List all API keys for an organization.
        
        Args:
            organization_id: The organization ID
            include_revoked: Whether to include revoked keys
            
        Returns:
            List of APIKey records (without key_hash for security)
        """
        query = select(APIKey).where(APIKey.organization_id == organization_id)
        
        if not include_revoked:
            query = query.where(APIKey.revoked_at.is_(None))
        
        result = await self.db.execute(query.order_by(APIKey.created_at.desc()))
        return list(result.scalars().all())
    
    async def rotate_api_key(
        self,
        key_id: UUID,
        organization_id: UUID,
    ) -> tuple[APIKey, str]:
        """
        Rotate an API key (create new, revoke old).
        
        Args:
            key_id: The API key ID to rotate
            organization_id: The owning organization
            
        Returns:
            Tuple of (new APIKey, raw_key)
        """
        # Get existing key
        result = await self.db.execute(
            select(APIKey).where(
                and_(
                    APIKey.id == key_id,
                    APIKey.organization_id == organization_id,
                    APIKey.revoked_at.is_(None),
                )
            )
        )
        old_key = result.scalar_one_or_none()
        
        if not old_key:
            raise InvalidAPIKeyError("API key not found")
        
        # Get organization for create
        result = await self.db.execute(
            select(Organization).where(Organization.id == organization_id)
        )
        org = result.scalar_one_or_none()
        
        if not org:
            raise InvalidAPIKeyError("Organization not found")
        
        # Create new key with same properties
        new_key, raw_key = await self.create_api_key(
            organization=org,
            name=f"{old_key.name} (rotated)",
            scopes=old_key.scopes,
            ip_allowlist=old_key.ip_allowlist,
            expires_at=old_key.expires_at,
            is_test=old_key.is_test,
        )
        
        # Revoke old key
        old_key.revoked_at = datetime.now(timezone.utc)
        await self.db.commit()
        
        logger.info(f"Rotated API key {key_id} -> {new_key.id}")
        
        return new_key, raw_key
    
    async def update_ip_allowlist(
        self,
        key_id: UUID,
        organization_id: UUID,
        ip_allowlist: list[str],
    ) -> APIKey:
        """
        Update the IP allowlist for an API key.
        
        Args:
            key_id: The API key ID
            organization_id: The owning organization
            ip_allowlist: New list of allowed IPs/CIDRs
            
        Returns:
            Updated APIKey record
        """
        # Check subscription limits
        subscription = await self._get_active_subscription(organization_id)
        if subscription:
            limits = PLAN_LIMITS.get(SquarePlan(subscription.plan))
            if limits and limits.ip_allowlist_entries != -1:
                if len(ip_allowlist) > limits.ip_allowlist_entries:
                    raise APIKeyLimitError(
                        f"IP allowlist limit is {limits.ip_allowlist_entries} entries. "
                        "Upgrade your plan for more."
                    )
        
        # Validate IPs
        validated_ips: list[str] = []
        for ip in ip_allowlist:
            try:
                ipaddress.ip_network(ip, strict=False)
                validated_ips.append(ip)
            except ValueError as e:
                raise InvalidIPError(f"Invalid IP address: {ip}") from e
        
        # Update key
        result = await self.db.execute(
            select(APIKey).where(
                and_(
                    APIKey.id == key_id,
                    APIKey.organization_id == organization_id,
                    APIKey.revoked_at.is_(None),
                )
            )
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            raise InvalidAPIKeyError("API key not found")
        
        api_key.ip_allowlist = validated_ips
        await self.db.commit()
        await self.db.refresh(api_key)
        
        return api_key
    
    def _is_ip_allowed(self, client_ip: str, allowlist: list[str]) -> bool:
        """Check if client IP is in the allowlist."""
        try:
            client = ipaddress.ip_address(client_ip)
        except ValueError:
            return False
        
        for entry in allowlist:
            try:
                network = ipaddress.ip_network(entry, strict=False)
                if client in network:
                    return True
            except ValueError:
                continue
        
        return False
    
    async def _get_active_subscription(
        self,
        organization_id: UUID,
    ) -> Optional[Subscription]:
        """Get the active subscription for an organization."""
        from .models import SubscriptionStatus
        
        result = await self.db.execute(
            select(Subscription).where(
                and_(
                    Subscription.organization_id == organization_id,
                    Subscription.status == SubscriptionStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def _count_api_keys(self, organization_id: UUID) -> int:
        """Count active API keys for an organization."""
        from sqlalchemy import func
        
        result = await self.db.execute(
            select(func.count(APIKey.id)).where(
                and_(
                    APIKey.organization_id == organization_id,
                    APIKey.revoked_at.is_(None),
                )
            )
        )
        return result.scalar() or 0


# Custom exceptions
class APIKeyError(Exception):
    """Base API key error."""
    pass


class InvalidAPIKeyError(APIKeyError):
    """Invalid or expired API key."""
    pass


class IPNotAllowedError(APIKeyError):
    """Client IP not in allowlist."""
    pass


class InsufficientScopesError(APIKeyError):
    """API key lacks required scopes."""
    pass


class APIKeyLimitError(APIKeyError):
    """API key limit reached for subscription."""
    pass


class InvalidIPError(APIKeyError):
    """Invalid IP address format."""
    pass
