"""
Device Registration API

REST API endpoints for device registration and push notification management.
Supports mobile wallet device registration for push challenges.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any, AsyncIterator, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Header, Path, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .device_registry import DeviceInfo, DeviceRegistry
from .challenge_store import ChallengeStore
from .adapters.sse import SSEAdapter
from .adapters.fcm import FCMAdapter
from .signing import get_server_public_key_der_base64, sign_challenge, get_signer
from .types import MartyChallengePayload, ChallengeOption, NotificationTarget

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/devices", tags=["devices"])

# Global SSE adapter instance - configured at app startup
_sse_adapter: Optional[SSEAdapter] = None

# Global FCM adapter instance - configured at app startup
_fcm_adapter: Optional[FCMAdapter] = None


def configure_sse_adapter(adapter: SSEAdapter) -> None:
    """Configure the global SSE adapter. Called at app startup."""
    global _sse_adapter
    _sse_adapter = adapter


def configure_fcm_adapter(adapter: FCMAdapter) -> None:
    """Configure the global FCM adapter. Called at app startup."""
    global _fcm_adapter
    _fcm_adapter = adapter
    logger.info("FCM adapter configured")


def get_fcm_adapter() -> Optional[FCMAdapter]:
    """
    Get the configured FCM adapter.
    
    Returns None if Firebase is not configured, allowing
    the system to run in polling-only mode.
    """
    return _fcm_adapter


# =============================================================================
# Request/Response Models
# =============================================================================

class DeviceRegistrationRequest(BaseModel):
    """Request to register a device for push notifications."""
    device_id: str = Field(
        ...,
        description="Device ID in format '<org_id>:<platform_device_id>' or just '<platform_device_id>'",
        examples=["550e8400-e29b-41d4-a716-446655440000:ABC123DEF456"],
    )
    fcm_token: str = Field(
        ...,
        description="Firebase Cloud Messaging token for push delivery",
        min_length=1,
    )
    platform: str = Field(
        ...,
        description="Device platform: ios, android, or web",
        pattern="^(ios|android|web)$",
    )
    public_key: Optional[str] = Field(
        None,
        description="RSA public key in base64-encoded PKCS#1 DER format for challenge signature verification",
        examples=["MIIBCgKCAQEA..."],
    )
    app_version: Optional[str] = Field(
        None,
        description="Application version string",
        examples=["1.0.0", "2.1.3-beta"],
    )
    os_version: Optional[str] = Field(
        None,
        description="Operating system version",
        examples=["iOS 17.2", "Android 14"],
    )
    device_model: Optional[str] = Field(
        None,
        description="Device model identifier",
        examples=["iPhone 15 Pro", "Pixel 8"],
    )
    preferences: Optional[dict[str, Any]] = Field(
        default_factory=dict,
        description="Notification preferences",
    )


class DeviceRegistrationResponse(BaseModel):
    """Response after device registration."""
    device_id: str
    registration_id: str
    organization_id: Optional[str] = None
    public_key_kid: Optional[str] = None
    registered_at: datetime
    server_public_key: Optional[str] = Field(
        None,
        description="Server's RSA public key in base64-encoded DER format for verifying challenge signatures",
    )
    
    class Config:
        from_attributes = True


class KeyRotationRequest(BaseModel):
    """Request to rotate device public key."""
    public_key: str = Field(
        ...,
        description="New RSA public key in base64-encoded PKCS#1 DER format",
    )
    grace_period_days: int = Field(
        default=30,
        description="Days to keep old key valid for overlap",
        ge=1,
        le=90,
    )


class KeyRotationResponse(BaseModel):
    """Response after key rotation."""
    device_id: str
    old_key_kid: Optional[str] = None
    new_key_kid: str
    grace_period_ends: Optional[datetime] = None


class DeviceListResponse(BaseModel):
    """List of registered devices."""
    devices: list[DeviceRegistrationResponse]
    total_count: int


class PushChallengeRequest(BaseModel):
    """Request to create a push challenge."""
    title: str = Field(
        ...,
        description="Challenge title shown to user",
    )
    question: str = Field(
        ...,
        description="Question or action prompt",
    )
    nonce: str = Field(
        ...,
        description="Random nonce for challenge-response",
    )
    credential_id: Optional[str] = Field(
        None,
        description="Associated credential ID if applicable",
    )
    data: Optional[dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional challenge data",
    )
    ttl_seconds: int = Field(
        default=120,
        description="Time-to-live for the challenge",
        ge=30,
        le=600,
    )


class PushChallengeResponse(BaseModel):
    """Response after creating a push challenge."""
    challenge_id: str
    device_id: str
    created_at: datetime
    expires_at: datetime


class PendingChallengeResponse(BaseModel):
    """A pending push challenge."""
    challenge_id: str
    title: str
    question: str
    nonce: str
    credential_id: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    ttl_seconds: int


class ChallengeListResponse(BaseModel):
    """List of pending challenges."""
    challenges: list[PendingChallengeResponse]
    count: int


class ChallengeResponseRequest(BaseModel):
    """Response to a push challenge."""
    response: str = Field(
        ...,
        description="Response value: 'accept' or 'reject'",
        pattern="^(accept|reject)$",
    )
    signature: Optional[str] = Field(
        None,
        description="Cryptographic signature over challenge nonce (base64)",
    )


# =============================================================================
# Dependencies
# =============================================================================

async def get_device_registry() -> DeviceRegistry:
    """Get device registry instance. Override in app setup."""
    # This would be injected by the app's dependency system
    # For now, raise an error if not configured
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Device registry not configured",
    )


# Global challenge store instance - configured at app startup
_challenge_store: Optional[ChallengeStore] = None


def configure_challenge_store(store: ChallengeStore) -> None:
    """Configure the global challenge store. Called at app startup."""
    global _challenge_store
    _challenge_store = store


def get_challenge_store() -> ChallengeStore:
    """Get the challenge store instance. Fails if not configured."""
    if _challenge_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Challenge store not configured",
        )
    return _challenge_store


def parse_device_id(device_id: str) -> tuple[Optional[UUID], str]:
    """
    Parse device ID into org_id and platform_device_id.
    
    Format: '<org_id>:<platform_device_id>' or just '<platform_device_id>'
    
    Returns:
        Tuple of (organization_id, platform_device_id)
    """
    if ':' in device_id:
        parts = device_id.split(':', 1)
        try:
            org_id = UUID(parts[0])
            return org_id, parts[1]
        except ValueError:
            # Not a valid UUID, treat whole thing as device ID
            return None, device_id
    return None, device_id


# =============================================================================
# Device Registration Endpoints
# =============================================================================

@router.post(
    "/register",
    response_model=DeviceRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a device for push notifications",
    description="""
    Register a mobile device to receive push notifications.
    
    The device_id should be in the format `<org_id>:<platform_device_id>` 
    to support multi-organization scenarios. The organization ID is extracted
    from the device ID and stored with the registration.
    
    If the device is already registered, the FCM token is updated.
    
    Optionally include a public_key (base64 PKCS#1 DER) for challenge signature verification.
    """,
)
async def register_device(
    request: DeviceRegistrationRequest,
    user_id: Annotated[str, Header(alias="X-User-ID")] = None,
    registry: DeviceRegistry = Depends(get_device_registry),
) -> DeviceRegistrationResponse:
    """Register a device for push notifications."""
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-ID header required",
        )
    
    # Parse organization from device ID
    org_id, platform_device_id = parse_device_id(request.device_id)
    
    device_info = DeviceInfo(
        device_id=request.device_id,  # Store full device ID
        platform=request.platform,
        fcm_token=request.fcm_token,
        app_version=request.app_version,
        os_version=request.os_version,
        device_model=request.device_model,
        preferences=request.preferences,
        public_key=request.public_key,
    )
    
    registration = await registry.register_device(
        user_id=user_id,
        device_info=device_info,
        organization_id=org_id,
    )
    
    logger.info(f"Device registered: {request.device_id} for user {user_id}")
    
    # Emit SSE event for test observability
    try:
        if _sse_adapter:
            from .types import NotificationPayload, NotificationTarget
            from uuid import uuid4
            from datetime import datetime, timezone
            
            payload = NotificationPayload(
                id=uuid4(),
                event_type="device.registered",
                title="Device Registered",
                body=f"Device {request.device_id} registered successfully",
                data={
                    "device_id": request.device_id,
                    "platform": request.platform,
                    "registration_id": str(registration.id),
                },
                created_at=datetime.now(timezone.utc),
                target=NotificationTarget(
                    user_id=user_id,
                    organization_id=org_id,
                ),
            )
            await _sse_adapter.send(payload)
    except Exception as e:
        logger.debug(f"Failed to emit device.registered event: {e}")
    
    # Get server public key for signature verification (if signing is configured)
    server_public_key = get_server_public_key_der_base64()
    
    return DeviceRegistrationResponse(
        device_id=registration.device_id,
        registration_id=str(registration.id),
        organization_id=str(registration.organization_id) if registration.organization_id else None,
        public_key_kid=registration.public_key_kid,
        registered_at=registration.created_at,
        server_public_key=server_public_key,
    )


@router.delete(
    "/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Unregister a device",
    description="Remove a device registration and stop receiving push notifications.",
)
async def unregister_device(
    device_id: Annotated[str, Path(description="Device ID to unregister")],
    user_id: Annotated[str, Header(alias="X-User-ID")] = None,
    registry: DeviceRegistry = Depends(get_device_registry),
):
    """Unregister a device."""
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-ID header required",
        )
    
    success = await registry.unregister_device(
        user_id=user_id,
        device_id=device_id,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device registration not found",
        )
    
    logger.info(f"Device unregistered: {device_id} for user {user_id}")


@router.post(
    "/{device_id}/rotate-key",
    response_model=KeyRotationResponse,
    summary="Rotate device public key",
    description="""
    Rotate the RSA public key for a device.
    
    The old key remains valid for a grace period (default 30 days) to allow
    for in-flight challenges. The new key is activated immediately.
    """,
)
async def rotate_device_key(
    device_id: Annotated[str, Path(description="Device ID to rotate key for")],
    request: KeyRotationRequest,
    user_id: Annotated[str, Header(alias="X-User-ID")] = None,
    registry: DeviceRegistry = Depends(get_device_registry),
) -> KeyRotationResponse:
    """Rotate device public key."""
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-ID header required",
        )
    
    # Get current key ID before rotation
    device = await registry.get_device_by_id(device_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )
    
    old_kid = device.public_key_kid
    
    updated = await registry.rotate_public_key(
        device_id=device_id,
        new_public_key=request.public_key,
        grace_period_days=request.grace_period_days,
    )
    
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to rotate key - invalid public key format",
        )
    
    logger.info(f"Key rotated for device {device_id}: {old_kid} -> {updated.public_key_kid}")
    
    return KeyRotationResponse(
        device_id=device_id,
        old_key_kid=old_kid,
        new_key_kid=updated.public_key_kid,
        grace_period_ends=updated.key_valid_until,
    )


@router.get(
    "",
    response_model=DeviceListResponse,
    summary="List registered devices",
    description="Get all registered devices for the current user.",
)
async def list_devices(
    user_id: Annotated[str, Header(alias="X-User-ID")] = None,
    organization_id: Annotated[Optional[str], Query(description="Filter by organization")] = None,
    registry: DeviceRegistry = Depends(get_device_registry),
) -> DeviceListResponse:
    """List registered devices for a user."""
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-ID header required",
        )
    
    org_uuid = UUID(organization_id) if organization_id else None
    
    devices = await registry.get_user_devices(
        user_id=user_id,
        organization_id=org_uuid,
    )
    
    # Get server public key for the list response
    server_public_key = get_server_public_key_der_base64()
    
    return DeviceListResponse(
        devices=[
            DeviceRegistrationResponse(
                device_id=d.device_id,
                registration_id=str(d.id),
                organization_id=str(d.organization_id) if d.organization_id else None,
                registered_at=d.created_at,
                server_public_key=server_public_key,
            )
            for d in devices
        ],
        total_count=len(devices),
    )


# =============================================================================
# Push Challenge Endpoints (production + polling)
# =============================================================================

push_router = APIRouter(prefix="/api/push", tags=["push-notifications"])


class ChallengeOptionInput(BaseModel):
    """An option for multi-choice challenges."""
    id: str = Field(
        ...,
        description="Unique identifier sent in response",
        max_length=50,
    )
    label: str = Field(
        ...,
        description="Display text for the button",
        max_length=100,
    )


class CreateChallengeRequest(BaseModel):
    """Request to create a push authentication challenge."""
    title: str = Field(
        ...,
        description="Challenge title shown to user",
        max_length=100,
    )
    question: str = Field(
        ...,
        description="Authentication question or action prompt",
        max_length=500,
    )
    credential_id: Optional[str] = Field(
        None,
        description="Specific credential ID to use, or any if not specified",
    )
    options: Optional[list[ChallengeOptionInput]] = Field(
        None,
        description="Options for multi-choice challenges, displayed as buttons. If not provided, defaults to Accept/Reject.",
        max_length=6,
    )
    data: Optional[dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional challenge data (up to 10 keys)",
    )
    ttl_seconds: int = Field(
        default=120,
        description="Time-to-live in seconds",
        ge=30,
        le=600,
    )
    require_signature: bool = Field(
        default=True,
        description="Whether to require cryptographic signature on response",
    )


class ChallengeCreatedResponse(BaseModel):
    """Response after creating a push authentication challenge."""
    challenge_id: str
    device_id: str
    nonce: str
    created_at: datetime
    expires_at: datetime
    delivery_method: str = Field(description="'fcm', 'sse', or 'poll'")


@push_router.post(
    "/challenges",
    response_model=ChallengeCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a push authentication challenge",
    description="""
    Create a new push authentication challenge for a registered device.
    
    The challenge is delivered via:
    - **FCM**: If the device has a valid FCM token (mobile apps)
    - **SSE**: If the device has an active SSE connection (web clients)
    - **Poll**: The challenge is stored for polling via GET /challenges
    
    The response includes a cryptographically random nonce that must be
    signed by the device's private key when accepting the challenge.
    """,
)
async def create_challenge(
    device_id: Annotated[str, Query(description="Target device ID")],
    request: CreateChallengeRequest,
    x_relying_party_id: Annotated[str, Header(description="Relying party identifier")],
    registry: DeviceRegistry = Depends(get_device_registry),
    challenge_store: ChallengeStore = Depends(get_challenge_store),
) -> ChallengeCreatedResponse:
    """Create a push authentication challenge for a device."""
    import secrets
    
    # Get adapters
    global _sse_adapter, _fcm_adapter
    sse_adapter = _sse_adapter
    fcm_adapter = _fcm_adapter
    
    # Verify device exists and is registered
    device = await registry.get_device_by_id(device_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not registered",
        )
    
    # Generate cryptographic nonce (32 bytes = 256 bits)
    nonce = secrets.token_urlsafe(32)
    challenge_id = str(uuid4())
    now = datetime.now(timezone.utc)
    expires_at = datetime.fromtimestamp(now.timestamp() + request.ttl_seconds, tz=timezone.utc)
    
    # Build options (default to Accept/Reject if not provided)
    if request.options:
        options = [ChallengeOption(id=opt.id, label=opt.label) for opt in request.options]
    else:
        options = [
            ChallengeOption(id="accept", label="Approve"),
            ChallengeOption(id="reject", label="Deny"),
        ]
    
    # Build Marty challenge payload
    challenge = MartyChallengePayload(
        challenge_id=challenge_id,
        device_id=device_id,
        title=request.title,
        question=request.question,
        nonce=nonce,
        options=options,
        ttl_seconds=request.ttl_seconds,
        created_at=now,
        credential_id=request.credential_id,
        relying_party_id=x_relying_party_id,
        require_signature=request.require_signature,
        data=request.data or {},
    )
    
    # Sign the challenge (if signing is configured)
    signer = get_signer()
    if signer:
        challenge = sign_challenge(challenge)
    else:
        logger.warning("Challenge signing not configured - challenge will be unsigned")
    
    delivery_method = "poll"
    
    # Platform-based routing:
    # - Web (platform == "web"): Use SSE only
    # - Mobile (platform == "ios" or "android"): Use FCM, skip SSE
    is_web_platform = device.platform == "web"
    
    if is_web_platform and sse_adapter:
        # Web clients: deliver via SSE
        try:
            payload = challenge.to_notification_payload()
            payload.target = NotificationTarget(user_id=device_id)
            result = await sse_adapter.send(payload)
            if result.success and result.metadata.get("connections", 0) > 0:
                delivery_method = "sse"
                logger.info(f"Challenge {challenge_id} delivered via SSE to {device_id}")
        except Exception as e:
            logger.debug(f"SSE delivery failed: {e}")
    elif not is_web_platform and fcm_adapter and device.fcm_token:
        # Mobile clients: deliver via FCM
        try:
            payload = challenge.to_notification_payload()
            payload.target = NotificationTarget(device_tokens=[device.fcm_token])
            result = await fcm_adapter.send(payload)
            if result.success:
                delivery_method = "fcm"
                logger.info(f"Challenge {challenge_id} delivered via FCM to {device_id}")
            else:
                logger.warning(f"FCM delivery failed for {device_id}: {result.error_message}")
        except Exception as e:
            logger.error(f"FCM delivery error: {e}")
    elif not is_web_platform and not fcm_adapter:
        logger.debug(f"FCM not configured, challenge {challenge_id} will use polling")
    
    # Store challenge for polling (always, as fallback)
    challenge_data = {
        "challenge_id": challenge_id,
        "title": request.title,
        "question": request.question,
        "nonce": nonce,
        "credential_id": request.credential_id,
        "relying_party_id": x_relying_party_id,
        "require_signature": request.require_signature,
        "options": [opt.to_dict() for opt in options],
        "data": request.data or {},
        "created_at": now.isoformat(),
        "ttl_seconds": request.ttl_seconds,
        "signature": challenge.signature,
        "format": challenge.format,
    }
    await challenge_store.create_challenge(
        device_id=device_id,
        challenge_data=challenge_data,
        ttl_seconds=request.ttl_seconds,
    )
    
    return ChallengeCreatedResponse(
        challenge_id=challenge_id,
        device_id=device_id,
        nonce=nonce,
        created_at=now,
        expires_at=expires_at,
        delivery_method=delivery_method,
    )


@push_router.get(
    "/challenges",
    response_model=ChallengeListResponse,
    summary="Poll for pending push challenges",
    description="""
    Poll for pending push challenges for a device.
    
    Mobile wallets call this endpoint to check for pending authentication
    or authorization challenges when push notifications are not available
    or as a fallback mechanism.
    
    Challenges are automatically removed once polled (to prevent replay).
    """,
)
async def get_pending_challenges(
    device_id: Annotated[str, Query(description="Device ID to get challenges for")],
    challenge_store: ChallengeStore = Depends(get_challenge_store),
    registry: DeviceRegistry = Depends(get_device_registry),
) -> ChallengeListResponse:
    """Get pending challenges for a device."""
    # Verify device exists
    device = await registry.get_device_by_id(device_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not registered",
        )
    
    challenges = await challenge_store.get_pending_challenges(device_id)
    
    return ChallengeListResponse(
        challenges=[
            PendingChallengeResponse(
                challenge_id=c.get("challenge_id", c["data"].get("challenge_id", "")),
                title=c["data"].get("title", ""),
                question=c["data"].get("question", ""),
                nonce=c["data"].get("nonce", ""),
                credential_id=c["data"].get("credential_id"),
                data=c["data"].get("data", {}),
                created_at=datetime.fromisoformat(c["created_at"]) if isinstance(c.get("created_at"), str) else c.get("created_at", datetime.now(timezone.utc)),
                ttl_seconds=c.get("ttl_seconds", 120),
            )
            for c in challenges
        ],
        count=len(challenges),
    )


@push_router.post(
    "/challenges/{challenge_id}/respond",
    status_code=status.HTTP_200_OK,
    summary="Respond to a push challenge",
    description="""
    Submit a response (accept/reject) to a push challenge.
    
    For 'accept' responses, a cryptographic signature over the challenge nonce
    is required if the challenge was created with `require_signature=true`.
    The signature is verified against the device's registered public key
    using RSA PKCS#1 SHA-256.
    """,
)
async def respond_to_challenge(
    challenge_id: Annotated[str, Path(description="Challenge ID to respond to")],
    device_id: Annotated[str, Query(description="Device ID responding")],
    request: ChallengeResponseRequest,
    challenge_store: ChallengeStore = Depends(get_challenge_store),
    registry: DeviceRegistry = Depends(get_device_registry),
) -> dict[str, Any]:
    """Respond to a push challenge."""
    # Verify device exists
    device = await registry.get_device_by_id(device_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not registered",
        )
    
    # Lookup device public key for signature verification
    public_key_der = None
    if request.signature:
        try:
            if device.public_key_der and registry.is_key_valid(device):
                public_key_der = device.public_key_der
        except Exception as e:
            logger.warning(f"Could not get public key for signature verification: {e}")
    
    success, error = await challenge_store.respond_to_challenge(
        device_id=device_id,
        challenge_id=challenge_id,
        response=request.response,
        signature=request.signature,
    )
    
    if not success:
        if error == "Invalid signature":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid challenge signature",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error or "Challenge not found or already responded",
        )
    
    return {
        "success": True,
        "challenge_id": challenge_id,
        "response": request.response,
        "signature_verified": bool(public_key_der and request.signature),
    }


# =============================================================================
# SSE (Server-Sent Events) Router for Real-time Push Notifications
# =============================================================================

sse_router = APIRouter(prefix="/api/events", tags=["sse"])


def get_sse_adapter() -> SSEAdapter:
    """Get the SSE adapter instance."""
    if _sse_adapter is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SSE adapter not configured",
        )
    return _sse_adapter


@sse_router.get(
    "/push",
    summary="SSE stream for push challenges",
    description="""
    Server-Sent Events endpoint for real-time push challenge delivery.
    
    This is an alternative to Firebase Cloud Messaging for web-based development
    and testing. Mobile wallets can connect to this endpoint to receive push
    challenges in real-time without polling.
    
    **Usage:**
    ```javascript
    const eventSource = new EventSource('/api/events/push?device_id=xxx');
    eventSource.onmessage = (event) => {
        const challenge = JSON.parse(event.data);
        console.log('Received challenge:', challenge);
    };
    ```
    
    **Automatic Reconnection:**
    The EventSource API automatically reconnects if the connection is lost.
    Heartbeat events are sent every 30 seconds to keep the connection alive.
    """,
    responses={
        200: {
            "description": "SSE event stream",
            "content": {"text/event-stream": {}},
        },
    },
)
async def sse_push_stream(
    device_id: Annotated[str, Query(description="Device ID to receive challenges for")],
    sse_adapter: SSEAdapter = Depends(get_sse_adapter),
) -> StreamingResponse:
    """SSE stream for push challenges."""
    connection_id = f"wallet-{device_id}-{uuid4().hex[:8]}"
    
    # Parse organization from device ID
    org_id = None
    if ':' in device_id:
        try:
            org_id = UUID(device_id.split(':')[0])
        except ValueError:
            pass
    
    # Add connection
    connection = sse_adapter.add_connection(
        connection_id=connection_id,
        user_id=device_id,  # Use device_id as user_id for targeting
        organization_id=org_id,
    )
    
    logger.info(f"SSE connection opened: {connection_id} for device {device_id}")
    
    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in sse_adapter.event_stream(connection):
                yield event
        finally:
            logger.info(f"SSE connection closed: {connection_id}")
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@sse_router.post(
    "/push/send",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send a push challenge via SSE",
    description="""
    Send a push challenge to a device via SSE.
    
    This endpoint is for testing and development. In production, challenges
    are created through the normal push challenge API and delivered via FCM.
    """,
)
async def send_sse_push(
    device_id: Annotated[str, Query(description="Target device ID")],
    request: PushChallengeRequest,
    sse_adapter: SSEAdapter = Depends(get_sse_adapter),
) -> dict[str, Any]:
    """Send a push challenge via SSE."""
    from .types import NotificationPayload, NotificationTarget
    
    challenge_id = str(uuid4())
    now = datetime.now(timezone.utc)
    
    payload = NotificationPayload(
        id=UUID(challenge_id),
        title=request.title,
        body=request.question,
        event_type="push_challenge",
        data={
            "challenge_id": challenge_id,
            "nonce": request.nonce,
            "question": request.question,
            "credential_id": request.credential_id,
            "ttl_seconds": request.ttl_seconds,
            **request.data,
        },
        created_at=now,
        target=NotificationTarget(
            user_id=device_id,  # Target by device_id
        ),
    )
    
    result = await sse_adapter.send(payload)
    
    return {
        "challenge_id": challenge_id,
        "device_id": device_id,
        "delivered": result.success,
        "connections": result.metadata.get("connections", 0),
    }


@sse_router.get(
    "/stats",
    summary="Get SSE connection statistics",
    description="Get statistics about active SSE connections.",
)
async def get_sse_stats(
    sse_adapter: SSEAdapter = Depends(get_sse_adapter),
) -> dict[str, Any]:
    """Get SSE connection statistics."""
    return sse_adapter.get_connection_stats()

