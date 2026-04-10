"""
Subscription API Routes

FastAPI endpoints for subscription management, API keys, and webhooks.

.. deprecated::
    These routers are NOT mounted in the application.  The active subscription,
    API key, and webhook endpoints are defined in
    ``digital_identity.infrastructure.adapters.rest.routers`` and registered by
    the DigitalIdentityPlugin.  This module is retained for reference but will
    be removed in a future cleanup pass.
"""
from __future__ import annotations

import logging
import os
import warnings
from datetime import datetime, timezone
from typing import Any, Optional

warnings.warn(
    "subscription.routes is orphaned and not mounted in any FastAPI app. "
    "Use digital_identity.infrastructure.adapters.rest.routers instead.",
    DeprecationWarning,
    stacklevel=2,
)
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from .api_key_service import (
    APIKeyError,
    APIKeyInfo,
    APIKeyService,
    InsufficientScopesError,
    InvalidAPIKeyError,
    IPNotAllowedError,
)
from .models import Organization, Subscription, SubscriptionStatus
from .square_service import SquareConfig, SquarePlan, SquareService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/subscriptions", tags=["subscriptions"])
api_key_router = APIRouter(prefix="/v1/api-keys", tags=["api-keys"])
webhook_router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


# Request/Response Models
class CreateOrganizationRequest(BaseModel):
    """Request to create an organization."""
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    email: str = Field(..., description="Billing email")


class OrganizationResponse(BaseModel):
    """Organization response."""
    id: UUID
    name: str
    slug: str
    created_at: datetime


class CreateSubscriptionRequest(BaseModel):
    """Request to create a subscription."""
    plan: SquarePlan
    card_id: Optional[str] = None


class SubscriptionResponse(BaseModel):
    """Subscription response."""
    id: UUID
    plan: str
    status: str
    api_calls_used: int
    api_calls_limit: int
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]


class UsageSummaryResponse(BaseModel):
    """Usage summary response."""
    plan: str
    api_calls: dict[str, Any]
    limits: dict[str, int]
    features: dict[str, bool]
    period_start: Optional[str]
    period_end: Optional[str]


class CreateAPIKeyRequest(BaseModel):
    """Request to create an API key."""
    name: str = Field(..., min_length=1, max_length=255)
    scopes: list[str] = Field(..., min_length=1, description="At least one scope is required")
    ip_allowlist: list[str] = Field(default_factory=list)
    expires_at: Optional[datetime] = None
    is_test: bool = False


class APIKeyResponse(BaseModel):
    """API key response (without secret)."""
    id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    ip_allowlist: list[str]
    is_test: bool
    expires_at: Optional[datetime]
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime]
    created_at: datetime


class APIKeyCreatedResponse(APIKeyResponse):
    """API key response with secret (only at creation)."""
    secret: str = Field(..., description="The API key secret - only shown once!")


class UpdateIPAllowlistRequest(BaseModel):
    """Request to update IP allowlist."""
    ip_allowlist: list[str]


class CreateWebhookRequest(BaseModel):
    """Request to create a webhook endpoint."""
    url: str = Field(..., min_length=1, max_length=2048)
    event_types: list[str] = Field(default_factory=list)
    description: Optional[str] = None


class WebhookResponse(BaseModel):
    """Webhook endpoint response."""
    id: UUID
    url: str
    event_types: list[str]
    enabled: bool
    description: Optional[str]
    created_at: datetime


class WebhookCreatedResponse(WebhookResponse):
    """Webhook response with secret (only at creation)."""
    secret: str = Field(..., description="HMAC secret for signature verification")


class UpdateWebhookRequest(BaseModel):
    """Request to update a webhook endpoint."""
    url: Optional[str] = Field(None, min_length=1, max_length=2048)
    event_types: Optional[list[str]] = None
    enabled: Optional[bool] = None


# Dependencies (to be configured by the application)
# Override these via app.dependency_overrides[get_db] = your_impl
async def get_db():
    """Get database session — must be overridden at app startup."""
    raise NotImplementedError(
        "get_db() dependency not configured. "
        "Set app.dependency_overrides[get_db] in your application startup."
    )


async def get_current_organization(request: Request) -> Organization:
    """Get current organization — must be overridden at app startup."""
    raise NotImplementedError(
        "get_current_organization() dependency not configured. "
        "Set app.dependency_overrides[get_current_organization] in your application startup."
    )


async def get_square_service() -> SquareService:
    """Get Square service — must be overridden at app startup."""
    raise NotImplementedError(
        "get_square_service() dependency not configured. "
        "Set app.dependency_overrides[get_square_service] in your application startup."
    )


async def get_api_key_service() -> APIKeyService:
    """Get API key service — must be overridden at app startup."""
    raise NotImplementedError(
        "get_api_key_service() dependency not configured. "
        "Set app.dependency_overrides[get_api_key_service] in your application startup."
    )


# Subscription Routes
@router.post(
    "/organizations",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Organization",
)
async def create_organization(
    request: CreateOrganizationRequest,
    db=Depends(get_db),
    current_user: str = Header(..., alias="X-User-ID"),
) -> OrganizationResponse:
    """
    Create a new organization.
    
    This is typically called during initial onboarding.
    Requires authenticated user identity.
    """
    from sqlalchemy import select
    from .models import Organization
    
    # Check if slug is taken
    result = await db.execute(
        select(Organization).where(Organization.slug == request.slug)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Organization slug '{request.slug}' is already taken",
        )
    
    # Create organization
    org = Organization(
        id=uuid4(),
        name=request.name,
        slug=request.slug,
        settings={},
        created_at=datetime.now(timezone.utc),
    )
    
    db.add(org)
    await db.commit()
    await db.refresh(org)
    
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        created_at=org.created_at,
    )


@router.get(
    "/organizations/{organization_id}",
    response_model=dict,
    summary="Get Organization",
)
async def get_organization(
    organization_id: UUID,
    db=Depends(get_db),
    current_org: Organization = Depends(get_current_organization),
) -> dict:
    """
    Get organization details.
    
    User must be a member of the organization.
    """
    from sqlalchemy import select
    from .models import Organization
    
    result = await db.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    
    # Verify user has access to this organization
    if current_org.id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this organization",
        )
    
    return {
        "id": str(org.id),
        "name": org.name,
        "slug": org.slug,
        "created_at": org.created_at.isoformat(),
        "settings": org.settings or {},
        "logo_url": org.settings.get("logo_url") if org.settings else None,
    }


class UpdateOrganizationRequest(BaseModel):
    """Request to update organization."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    logo_url: Optional[str] = Field(None, max_length=2048)
    website_url: Optional[str] = Field(None, max_length=2048)
    contact_email: Optional[str] = Field(None, max_length=255)


@router.patch(
    "/organizations/{organization_id}",
    response_model=dict,
    summary="Update Organization",
)
async def update_organization(
    organization_id: UUID,
    request: UpdateOrganizationRequest,
    db=Depends(get_db),
    current_org: Organization = Depends(get_current_organization),
) -> dict:
    """
    Update organization details.
    
    User must be an admin or owner of the organization.
    """
    from sqlalchemy import select
    from .models import Organization
    
    # Verify user has access to this organization
    if current_org.id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this organization",
        )
    
    result = await db.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    
    # Update fields
    if request.name is not None:
        org.name = request.name
    
    # Update settings (copy dict to trigger SQLAlchemy change tracking)
    if org.settings is None:
        org.settings = {}
    else:
        org.settings = dict(org.settings)
    
    if request.logo_url is not None:
        org.settings["logo_url"] = request.logo_url
    if request.website_url is not None:
        org.settings["website_url"] = request.website_url
    if request.contact_email is not None:
        org.settings["contact_email"] = request.contact_email
    
    await db.commit()
    await db.refresh(org)
    
    return {
        "id": str(org.id),
        "name": org.name,
        "slug": org.slug,
        "created_at": org.created_at.isoformat(),
        "settings": org.settings or {},
        "logo_url": org.settings.get("logo_url") if org.settings else None,
    }


@router.post(
    "",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Subscription",
)
async def create_subscription(
    request: CreateSubscriptionRequest,
    org: Organization = Depends(get_current_organization),
    square: SquareService = Depends(get_square_service),
) -> SubscriptionResponse:
    """
    Create a new subscription for the organization.
    
    Free plan doesn't require payment method.
    Paid plans require a valid card_id from Square.
    """
    try:
        subscription = await square.create_subscription(
            organization=org,
            plan=request.plan,
            card_id=request.card_id,
        )
    except Exception as e:
        logger.error(f"Failed to create subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create subscription",
        )
    
    return SubscriptionResponse(
        id=subscription.id,
        plan=subscription.plan,
        status=subscription.status.value if isinstance(subscription.status, SubscriptionStatus) else subscription.status,
        api_calls_used=subscription.api_calls_used,
        api_calls_limit=subscription.api_calls_limit,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
    )


@router.get(
    "/current",
    response_model=SubscriptionResponse,
    summary="Get Current Subscription",
)
async def get_current_subscription(
    org: Organization = Depends(get_current_organization),
    db=Depends(get_db),
) -> SubscriptionResponse:
    """Get the current active subscription for the organization."""
    from sqlalchemy import and_, select
    from .models import Subscription, SubscriptionStatus
    
    result = await db.execute(
        select(Subscription).where(
            and_(
                Subscription.organization_id == org.id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found",
        )
    
    return SubscriptionResponse(
        id=subscription.id,
        plan=subscription.plan,
        status=subscription.status.value if isinstance(subscription.status, SubscriptionStatus) else subscription.status,
        api_calls_used=subscription.api_calls_used,
        api_calls_limit=subscription.api_calls_limit,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
    )


@router.get(
    "/usage",
    response_model=UsageSummaryResponse,
    summary="Get Usage Summary",
)
async def get_usage_summary(
    org: Organization = Depends(get_current_organization),
    square: SquareService = Depends(get_square_service),
    db=Depends(get_db),
) -> UsageSummaryResponse:
    """Get usage summary for the current subscription."""
    from sqlalchemy import and_, select
    from .models import Subscription, SubscriptionStatus
    
    result = await db.execute(
        select(Subscription).where(
            and_(
                Subscription.organization_id == org.id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found",
        )
    
    summary = await square.get_usage_summary(subscription)
    return UsageSummaryResponse(**summary)


@router.post(
    "/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel Subscription",
)
async def cancel_subscription(
    immediately: bool = False,
    org: Organization = Depends(get_current_organization),
    square: SquareService = Depends(get_square_service),
    db=Depends(get_db),
) -> None:
    """
    Cancel the current subscription.
    
    By default, cancellation takes effect at the end of the billing period.
    Set `immediately=true` to cancel immediately.
    """
    from sqlalchemy import and_, select
    from .models import Subscription, SubscriptionStatus
    
    result = await db.execute(
        select(Subscription).where(
            and_(
                Subscription.organization_id == org.id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
    )
    subscription = result.scalar_one_or_none()
    
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found",
        )
    
    await square.cancel_subscription(subscription, immediately=immediately)


# API Key Routes
@api_key_router.post(
    "",
    response_model=APIKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create API Key",
)
async def create_api_key(
    request: CreateAPIKeyRequest,
    org: Organization = Depends(get_current_organization),
    service: APIKeyService = Depends(get_api_key_service),
) -> APIKeyCreatedResponse:
    """
    Create a new API key.
    
    The secret is only returned once at creation time.
    Store it securely - it cannot be retrieved later.
    """
    try:
        api_key, raw_key = await service.create_api_key(
            organization=org,
            name=request.name,
            scopes=request.scopes,
            ip_allowlist=request.ip_allowlist,
            expires_at=request.expires_at,
            is_test=request.is_test,
        )
    except APIKeyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return APIKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes,
        ip_allowlist=api_key.ip_allowlist,
        is_test=api_key.is_test,
        expires_at=api_key.expires_at,
        revoked_at=None,  # New keys are never revoked
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        secret=raw_key,
    )


class APIKeyListResponse(BaseModel):
    """Paginated API key list response."""
    keys: list[APIKeyResponse]
    total: int


@api_key_router.get(
    "",
    response_model=APIKeyListResponse,
    summary="List API Keys",
)
async def list_api_keys(
    include_revoked: bool = False,
    org: Organization = Depends(get_current_organization),
    service: APIKeyService = Depends(get_api_key_service),
) -> APIKeyListResponse:
    """List all API keys for the organization."""
    keys = await service.list_api_keys(
        organization_id=org.id,
        include_revoked=include_revoked,
    )
    
    items = [
        APIKeyResponse(
            id=key.id,
            name=key.name,
            key_prefix=key.key_prefix,
            scopes=key.scopes,
            ip_allowlist=key.ip_allowlist,
            is_test=key.is_test,
            expires_at=key.expires_at,
            revoked_at=key.revoked_at,
            last_used_at=key.last_used_at,
            created_at=key.created_at,
        )
        for key in keys
    ]
    
    return APIKeyListResponse(keys=items, total=len(items))


@api_key_router.post(
    "/{key_id}/revoke",
    response_model=APIKeyResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke API Key",
)
async def revoke_api_key_post(
    key_id: UUID,
    org: Organization = Depends(get_current_organization),
    service: APIKeyService = Depends(get_api_key_service),
    db=Depends(get_db),
) -> APIKeyResponse:
    """Revoke an API key."""
    from sqlalchemy import select
    from .models import APIKey
    
    try:
        await service.revoke_api_key(key_id=key_id, organization_id=org.id)
        
        # Fetch the updated key to return
        result = await db.execute(
            select(APIKey).filter_by(id=key_id, organization_id=org.id)
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            raise InvalidAPIKeyError("API key not found")
        
        return APIKeyResponse(
            id=api_key.id,
            name=api_key.name,
            key_prefix=api_key.key_prefix,
            scopes=api_key.scopes or [],
            ip_allowlist=api_key.ip_allowlist or [],
            is_test=api_key.is_test,
            expires_at=api_key.expires_at,
            revoked_at=api_key.revoked_at,
            last_used_at=api_key.last_used_at,
            created_at=api_key.created_at,
        )
    except InvalidAPIKeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )


@api_key_router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete API Key",
)
async def delete_api_key(
    key_id: UUID,
    org: Organization = Depends(get_current_organization),
    service: APIKeyService = Depends(get_api_key_service),
) -> None:
    """Delete an API key."""
    try:
        await service.revoke_api_key(key_id=key_id, organization_id=org.id)
    except InvalidAPIKeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )


@api_key_router.patch(
    "/{key_id}/ip-allowlist",
    response_model=APIKeyResponse,
    summary="Update IP Allowlist",
)
async def update_api_key_ip_allowlist(
    key_id: UUID,
    request: UpdateIPAllowlistRequest,
    org: Organization = Depends(get_current_organization),
    db=Depends(get_db),
) -> APIKeyResponse:
    """Update the IP allowlist for an API key."""
    from sqlalchemy import and_, select
    from .models import APIKey
    import ipaddress
    
    # Validate IPs
    for ip in request.ip_allowlist:
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid IP address: {ip}",
            )
    
    result = await db.execute(
        select(APIKey).where(
            and_(
                APIKey.id == key_id,
                APIKey.organization_id == org.id,
            )
        )
    )
    api_key = result.scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    
    api_key.ip_allowlist = request.ip_allowlist
    await db.commit()
    await db.refresh(api_key)
    
    return APIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes,
        ip_allowlist=api_key.ip_allowlist,
        is_test=api_key.is_test,
        expires_at=api_key.expires_at,
        revoked_at=api_key.revoked_at,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
    )


@api_key_router.post(
    "/{key_id}/rotate",
    response_model=APIKeyCreatedResponse,
    summary="Rotate API Key",
)
async def rotate_api_key(
    key_id: UUID,
    org: Organization = Depends(get_current_organization),
    service: APIKeyService = Depends(get_api_key_service),
) -> APIKeyCreatedResponse:
    """
    Rotate an API key.
    
    Creates a new key with the same settings and revokes the old one.
    """
    try:
        api_key, raw_key = await service.rotate_api_key(
            key_id=key_id,
            organization_id=org.id,
        )
    except InvalidAPIKeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    
    return APIKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes,
        ip_allowlist=api_key.ip_allowlist,
        is_test=api_key.is_test,
        expires_at=api_key.expires_at,
        revoked_at=None,  # New keys are never revoked
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        secret=raw_key,
    )


@api_key_router.put(
    "/{key_id}/ip-allowlist",
    response_model=APIKeyResponse,
    summary="Update IP Allowlist",
)
async def update_ip_allowlist(
    key_id: UUID,
    request: UpdateIPAllowlistRequest,
    org: Organization = Depends(get_current_organization),
    service: APIKeyService = Depends(get_api_key_service),
) -> APIKeyResponse:
    """Update the IP allowlist for an API key."""
    try:
        api_key = await service.update_ip_allowlist(
            key_id=key_id,
            organization_id=org.id,
            ip_allowlist=request.ip_allowlist,
        )
    except APIKeyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return APIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes,
        ip_allowlist=api_key.ip_allowlist,
        is_test=api_key.is_test,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
    )


# Webhook Routes
@webhook_router.post(
    "",
    response_model=WebhookCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Webhook Endpoint",
)
async def create_webhook(
    request: CreateWebhookRequest,
    org: Organization = Depends(get_current_organization),
    db=Depends(get_db),
) -> WebhookCreatedResponse:
    """
    Create a new webhook endpoint.
    
    The secret is used for HMAC-SHA256 signature verification.
    Store it securely - it cannot be retrieved later.
    """
    import secrets
    from .models import WebhookEndpoint
    from urllib.parse import urlparse
    
    # Validate URL
    try:
        parsed = urlparse(request.url)
        if not all([parsed.scheme, parsed.netloc]):
            raise ValueError("Invalid URL")
        _env = os.environ.get("MARTY_ENVIRONMENT", "production").lower()
        allowed_schemes = ["https"]
        if _env in ("development", "test") and parsed.hostname in ("localhost", "127.0.0.1", "::1"):
            allowed_schemes.append("http")
        if parsed.scheme not in allowed_schemes:
            raise ValueError("Webhook URL must use HTTPS")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid webhook URL",
        )
    
    # Generate secret
    webhook_secret = secrets.token_hex(32)
    
    endpoint = WebhookEndpoint(
        id=uuid4(),
        organization_id=org.id,
        url=request.url,
        secret=webhook_secret,
        event_types=request.event_types,
        description=request.description,
        enabled=True,
        failure_count=0,
        created_at=datetime.now(timezone.utc),
    )
    
    db.add(endpoint)
    await db.commit()
    await db.refresh(endpoint)
    
    return WebhookCreatedResponse(
        id=endpoint.id,
        url=endpoint.url,
        event_types=endpoint.event_types,
        enabled=endpoint.enabled,
        description=endpoint.description,
        created_at=endpoint.created_at,
        secret=webhook_secret,
    )


class WebhookListResponse(BaseModel):
    """Paginated webhook list response."""
    webhooks: list[WebhookResponse]
    total: int


@webhook_router.get(
    "",
    response_model=WebhookListResponse,
    summary="List Webhook Endpoints",
)
async def list_webhooks(
    org: Organization = Depends(get_current_organization),
    db=Depends(get_db),
) -> WebhookListResponse:
    """List all webhook endpoints for the organization."""
    from sqlalchemy import select
    from .models import WebhookEndpoint
    
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.organization_id == org.id
        ).order_by(WebhookEndpoint.created_at.desc())
    )
    endpoints = result.scalars().all()
    
    items = [
        WebhookResponse(
            id=ep.id,
            url=ep.url,
            event_types=ep.event_types,
            enabled=ep.enabled,
            description=ep.description,
            created_at=ep.created_at,
        )
        for ep in endpoints
    ]
    
    return WebhookListResponse(webhooks=items, total=len(items))


@webhook_router.get(
    "/{webhook_id}",
    response_model=WebhookResponse,
    summary="Get Webhook Endpoint",
)
async def get_webhook(
    webhook_id: UUID,
    org: Organization = Depends(get_current_organization),
    db=Depends(get_db),
) -> WebhookResponse:
    """Get details of a webhook endpoint."""
    from sqlalchemy import and_, select
    from .models import WebhookEndpoint
    
    result = await db.execute(
        select(WebhookEndpoint).where(
            and_(
                WebhookEndpoint.id == webhook_id,
                WebhookEndpoint.organization_id == org.id,
            )
        )
    )
    endpoint = result.scalar_one_or_none()
    
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )
    
    return WebhookResponse(
        id=endpoint.id,
        url=endpoint.url,
        event_types=endpoint.event_types,
        enabled=endpoint.enabled,
        description=endpoint.description,
        created_at=endpoint.created_at,
    )


@webhook_router.patch(
    "/{webhook_id}",
    response_model=WebhookResponse,
    summary="Update Webhook Endpoint",
)
async def update_webhook(
    webhook_id: UUID,
    request: UpdateWebhookRequest,
    org: Organization = Depends(get_current_organization),
    db=Depends(get_db),
) -> WebhookResponse:
    """Update a webhook endpoint."""
    from sqlalchemy import and_, select
    from .models import WebhookEndpoint
    from urllib.parse import urlparse
    
    result = await db.execute(
        select(WebhookEndpoint).where(
            and_(
                WebhookEndpoint.id == webhook_id,
                WebhookEndpoint.organization_id == org.id,
            )
        )
    )
    endpoint = result.scalar_one_or_none()
    
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )
    
    # Validate URL if provided
    if request.url is not None:
        try:
            parsed = urlparse(request.url)
            if not all([parsed.scheme, parsed.netloc]):
                raise ValueError("Invalid URL")
            if parsed.scheme not in ["http", "https"]:
                raise ValueError("URL must use http or https")
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid webhook URL",
            )
        endpoint.url = request.url
    
    if request.event_types is not None:
        endpoint.event_types = request.event_types
    
    if request.enabled is not None:
        endpoint.enabled = request.enabled
    
    endpoint.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(endpoint)
    
    return WebhookResponse(
        id=endpoint.id,
        url=endpoint.url,
        event_types=endpoint.event_types,
        enabled=endpoint.enabled,
        description=endpoint.description,
        created_at=endpoint.created_at,
    )


@webhook_router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Webhook Endpoint",
)
async def delete_webhook(
    webhook_id: UUID,
    org: Organization = Depends(get_current_organization),
    db=Depends(get_db),
) -> None:
    """Delete a webhook endpoint."""
    from sqlalchemy import and_, select
    from .models import WebhookEndpoint
    
    result = await db.execute(
        select(WebhookEndpoint).where(
            and_(
                WebhookEndpoint.id == webhook_id,
                WebhookEndpoint.organization_id == org.id,
            )
        )
    )
    endpoint = result.scalar_one_or_none()
    
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook endpoint not found",
        )
    
    await db.delete(endpoint)
    await db.commit()


@webhook_router.get(
    "/{webhook_id}/deliveries",
    summary="Get Webhook Delivery Attempts",
)
async def get_webhook_delivery_attempts(
    webhook_id: UUID,
    limit: int = 50,
    offset: int = 0,
    org: Organization = Depends(get_current_organization),
    db=Depends(get_db),
) -> dict[str, Any]:
    """Get delivery attempt history for a webhook."""
    from sqlalchemy import and_, func, select
    from .models import WebhookDeliveryAttempt, WebhookEndpoint
    
    result = await db.execute(
        select(WebhookEndpoint).where(
            and_(
                WebhookEndpoint.id == webhook_id,
                WebhookEndpoint.organization_id == org.id,
            )
        )
    )
    endpoint = result.scalar_one_or_none()
    
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )
    
    # Clamp pagination bounds
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    # Count total deliveries
    count_result = await db.execute(
        select(func.count()).where(
            WebhookDeliveryAttempt.webhook_id == webhook_id,
        )
    )
    total = count_result.scalar() or 0

    # Fetch delivery attempts ordered by most recent first
    deliveries_result = await db.execute(
        select(WebhookDeliveryAttempt)
        .where(WebhookDeliveryAttempt.webhook_id == webhook_id)
        .order_by(WebhookDeliveryAttempt.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    deliveries = deliveries_result.scalars().all()

    return {
        "webhook_id": str(webhook_id),
        "deliveries": [
            {
                "id": str(d.id),
                "event_id": d.event_id,
                "event_type": d.event_type,
                "success": d.success,
                "response_status_code": d.response_status_code,
                "error_message": d.error_message,
                "retry_count": d.retry_count,
                "response_time_ms": d.response_time_ms,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in deliveries
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@webhook_router.post(
    "/{webhook_id}/test",
    summary="Test Webhook Endpoint",
)
async def test_webhook(
    webhook_id: UUID,
    org: Organization = Depends(get_current_organization),
    db=Depends(get_db),
) -> dict[str, Any]:
    """
    Send a test event to the webhook endpoint.
    
    Returns the delivery result.
    """
    from sqlalchemy import and_, select
    from .models import WebhookEndpoint
    
    result = await db.execute(
        select(WebhookEndpoint).where(
            and_(
                WebhookEndpoint.id == webhook_id,
                WebhookEndpoint.organization_id == org.id,
            )
        )
    )
    endpoint = result.scalar_one_or_none()
    
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook endpoint not found",
        )
    
    # Send test event
    import httpx
    import hashlib
    import hmac
    import json
    
    test_payload = {
        "type": "webhook.test",
        "data": {
            "message": "This is a test event",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    
    body = json.dumps(test_payload).encode()
    signature = hmac.new(
        endpoint.secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                endpoint.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": f"sha256={signature}",
                    "X-Marty-Event": "webhook.test",
                },
            )
        
        return {
            "status": "success" if response.status_code < 400 else "error",
            "status_code": response.status_code,
            "response_time_ms": response.elapsed.total_seconds() * 1000,
        }
    except httpx.RequestError as e:
        return {
            "status": "error",
            "error": str(e),
        }


# Square Webhook Handler
@router.post(
    "/square/webhook",
    include_in_schema=False,
)
async def handle_square_webhook(
    request: Request,
    x_square_hmacsha256_signature: str = Header(...),
    square: SquareService = Depends(get_square_service),
) -> dict[str, str]:
    """Handle Square webhook events."""
    body = await request.body()
    
    # Verify signature
    webhook_url = str(request.url)
    if not square.verify_webhook_signature(body, x_square_hmacsha256_signature, webhook_url):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )
    
    # Parse and handle event
    import json
    event = json.loads(body)
    event_type = event.get("type", "")
    data = event.get("data", {})
    
    await square.handle_webhook(event_type, data)
    
    return {"status": "ok"}
