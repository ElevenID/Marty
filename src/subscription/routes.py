"""
Subscription API Routes

FastAPI endpoints for subscription management, API keys, and webhooks.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
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
    scopes: list[str] = Field(default_factory=list)
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


# Dependencies (to be configured by the application)
async def get_db():
    """Get database session."""
    raise NotImplementedError("Database dependency not configured")


async def get_current_organization(request: Request) -> Organization:
    """Get current organization from request context."""
    raise NotImplementedError("Auth dependency not configured")


async def get_square_service() -> SquareService:
    """Get Square service instance."""
    raise NotImplementedError("Square service not configured")


async def get_api_key_service() -> APIKeyService:
    """Get API key service instance."""
    raise NotImplementedError("API key service not configured")


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
) -> OrganizationResponse:
    """
    Create a new organization.
    
    This is typically called during initial onboarding.
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
            detail=str(e),
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
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        secret=raw_key,
    )


@api_key_router.get(
    "",
    response_model=list[APIKeyResponse],
    summary="List API Keys",
)
async def list_api_keys(
    include_revoked: bool = False,
    org: Organization = Depends(get_current_organization),
    service: APIKeyService = Depends(get_api_key_service),
) -> list[APIKeyResponse]:
    """List all API keys for the organization."""
    keys = await service.list_api_keys(
        organization_id=org.id,
        include_revoked=include_revoked,
    )
    
    return [
        APIKeyResponse(
            id=key.id,
            name=key.name,
            key_prefix=key.key_prefix,
            scopes=key.scopes,
            ip_allowlist=key.ip_allowlist,
            is_test=key.is_test,
            expires_at=key.expires_at,
            last_used_at=key.last_used_at,
            created_at=key.created_at,
        )
        for key in keys
    ]


@api_key_router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke API Key",
)
async def revoke_api_key(
    key_id: UUID,
    org: Organization = Depends(get_current_organization),
    service: APIKeyService = Depends(get_api_key_service),
) -> None:
    """Revoke an API key."""
    try:
        await service.revoke_api_key(key_id=key_id, organization_id=org.id)
    except InvalidAPIKeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
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


@webhook_router.get(
    "",
    response_model=list[WebhookResponse],
    summary="List Webhook Endpoints",
)
async def list_webhooks(
    org: Organization = Depends(get_current_organization),
    db=Depends(get_db),
) -> list[WebhookResponse]:
    """List all webhook endpoints for the organization."""
    from sqlalchemy import select
    from .models import WebhookEndpoint
    
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.organization_id == org.id
        ).order_by(WebhookEndpoint.created_at.desc())
    )
    endpoints = result.scalars().all()
    
    return [
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
                    "X-Marty-Signature": signature,
                    "X-Marty-Event": "webhook.test",
                },
            )
        
        return {
            "success": response.status_code < 400,
            "status_code": response.status_code,
            "response_time_ms": response.elapsed.total_seconds() * 1000,
        }
    except httpx.RequestError as e:
        return {
            "success": False,
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
