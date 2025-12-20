"""Test Helper API Router.

Provides endpoints for E2E test setup and teardown.
These endpoints should ONLY be enabled in test/development environments.

Endpoints:
- POST /api/test/setup-credential - Set up a credential for testing
- POST /api/test/setup-expired-credential - Set up an expired credential
- POST /api/test/set-device-offline - Simulate device going offline
- POST /api/test/set-device-online - Simulate device coming back online
- POST /api/test/reset-user - Reset a test user's state
- GET /api/test/health - Health check for test environment
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Only enable in test/dev environments
ENABLE_TEST_ENDPOINTS = os.environ.get("ENABLE_TEST_ENDPOINTS", "false").lower() == "true"

router = APIRouter(prefix="/api/test", tags=["test"])


# =============================================================================
# Request/Response Models
# =============================================================================


class SetupCredentialRequest(BaseModel):
    """Request to set up a test credential."""
    
    user_id: str = Field(..., description="User ID to create credential for")
    credential_type: str = Field("TRAVEL_VISA", description="Type of credential")
    expiry_days: int = Field(365, description="Days until expiry")
    metadata: dict | None = Field(None, description="Additional credential metadata")


class SetupCredentialResponse(BaseModel):
    """Response after setting up credential."""
    
    success: bool
    credential_id: str
    offer_uri: str
    expires_at: str
    message: str


class DeviceStateRequest(BaseModel):
    """Request to change device state."""
    
    device_id: str = Field(..., description="Device ID")


class DeviceStateResponse(BaseModel):
    """Response after changing device state."""
    
    success: bool
    device_id: str
    is_online: bool
    message: str


class ResetUserRequest(BaseModel):
    """Request to reset a test user."""
    
    user_id: str | None = Field(None, description="User ID to reset")
    email: str | None = Field(None, description="User email to reset")


class ResetUserResponse(BaseModel):
    """Response after resetting user."""
    
    success: bool
    user_id: str | None
    message: str


class TestHealthResponse(BaseModel):
    """Test environment health check."""
    
    healthy: bool
    environment: str
    test_endpoints_enabled: bool
    timestamp: str


# =============================================================================
# In-memory test state
# =============================================================================

# Track device online/offline state for testing
_device_states: dict[str, bool] = {}  # device_id -> is_online

# Track test credentials
_test_credentials: dict[str, dict] = {}  # credential_id -> credential data


# =============================================================================
# Endpoints
# =============================================================================


def _check_test_mode():
    """Check if test endpoints are enabled."""
    if not ENABLE_TEST_ENDPOINTS:
        raise HTTPException(
            status_code=403,
            detail="Test endpoints are disabled. Set ENABLE_TEST_ENDPOINTS=true to enable."
        )


@router.get("/health", response_model=TestHealthResponse)
async def test_health():
    """Health check for test environment."""
    return TestHealthResponse(
        healthy=True,
        environment=os.environ.get("ENVIRONMENT", "development"),
        test_endpoints_enabled=ENABLE_TEST_ENDPOINTS,
        timestamp=datetime.utcnow().isoformat(),
    )


@router.post("/setup-credential", response_model=SetupCredentialResponse)
async def setup_credential(body: SetupCredentialRequest):
    """Set up a test credential for E2E testing."""
    _check_test_mode()
    
    credential_id = str(uuid4())
    expires_at = datetime.utcnow() + timedelta(days=body.expiry_days)
    
    # Generate a mock OID4VCI offer URI
    offer_uri = f"openid-credential-offer://?credential_offer_uri=https://issuer.marty.demo/offers/{credential_id}"
    
    # Store credential for later verification
    _test_credentials[credential_id] = {
        "id": credential_id,
        "user_id": body.user_id,
        "credential_type": body.credential_type,
        "expires_at": expires_at.isoformat(),
        "metadata": body.metadata or {},
        "offer_uri": offer_uri,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
    }
    
    logger.info(f"Created test credential: {credential_id} for user {body.user_id}")
    
    return SetupCredentialResponse(
        success=True,
        credential_id=credential_id,
        offer_uri=offer_uri,
        expires_at=expires_at.isoformat(),
        message=f"Test credential created: {credential_id}",
    )


@router.post("/setup-expired-credential", response_model=SetupCredentialResponse)
async def setup_expired_credential(body: SetupCredentialRequest):
    """Set up an expired test credential for E2E testing."""
    _check_test_mode()
    
    credential_id = str(uuid4())
    # Expired yesterday
    expires_at = datetime.utcnow() - timedelta(days=1)
    
    offer_uri = f"openid-credential-offer://?credential_offer_uri=https://issuer.marty.demo/offers/{credential_id}"
    
    _test_credentials[credential_id] = {
        "id": credential_id,
        "user_id": body.user_id,
        "credential_type": body.credential_type,
        "expires_at": expires_at.isoformat(),
        "metadata": body.metadata or {},
        "offer_uri": offer_uri,
        "status": "expired",
        "created_at": datetime.utcnow().isoformat(),
    }
    
    logger.info(f"Created expired test credential: {credential_id}")
    
    return SetupCredentialResponse(
        success=True,
        credential_id=credential_id,
        offer_uri=offer_uri,
        expires_at=expires_at.isoformat(),
        message=f"Expired test credential created: {credential_id}",
    )


@router.post("/set-device-offline", response_model=DeviceStateResponse)
async def set_device_offline(body: DeviceStateRequest):
    """Simulate a device going offline."""
    _check_test_mode()
    
    _device_states[body.device_id] = False
    logger.info(f"Device set offline: {body.device_id}")
    
    return DeviceStateResponse(
        success=True,
        device_id=body.device_id,
        is_online=False,
        message="Device marked as offline",
    )


@router.post("/set-device-online", response_model=DeviceStateResponse)
async def set_device_online(body: DeviceStateRequest):
    """Simulate a device coming back online."""
    _check_test_mode()
    
    _device_states[body.device_id] = True
    logger.info(f"Device set online: {body.device_id}")
    
    return DeviceStateResponse(
        success=True,
        device_id=body.device_id,
        is_online=True,
        message="Device marked as online",
    )


@router.get("/device-state/{device_id}")
async def get_device_state(device_id: str):
    """Get current device online state."""
    _check_test_mode()
    
    is_online = _device_states.get(device_id, True)  # Default to online
    
    return {
        "device_id": device_id,
        "is_online": is_online,
    }


@router.post("/reset-user", response_model=ResetUserResponse)
async def reset_user(body: ResetUserRequest):
    """Reset a test user's state."""
    _check_test_mode()
    
    if not body.user_id and not body.email:
        raise HTTPException(status_code=400, detail="Must provide user_id or email")
    
    # Clear any test credentials for this user
    user_id = body.user_id
    creds_to_remove = []
    
    for cred_id, cred in _test_credentials.items():
        if cred.get("user_id") == user_id:
            creds_to_remove.append(cred_id)
    
    for cred_id in creds_to_remove:
        del _test_credentials[cred_id]
    
    logger.info(f"Reset user {user_id or body.email}: removed {len(creds_to_remove)} credentials")
    
    return ResetUserResponse(
        success=True,
        user_id=user_id,
        message=f"User reset complete. Removed {len(creds_to_remove)} test credentials.",
    )


@router.get("/credentials")
async def list_test_credentials():
    """List all test credentials (for debugging)."""
    _check_test_mode()
    
    return {
        "count": len(_test_credentials),
        "credentials": list(_test_credentials.values()),
    }


@router.delete("/credentials")
async def clear_test_credentials():
    """Clear all test credentials."""
    _check_test_mode()
    
    count = len(_test_credentials)
    _test_credentials.clear()
    
    return {
        "success": True,
        "cleared": count,
        "message": f"Cleared {count} test credentials",
    }
