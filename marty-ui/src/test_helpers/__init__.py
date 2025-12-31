"""Test Helper API Router.

Provides endpoints for E2E test setup and teardown.
These endpoints should ONLY be enabled in test/development environments.

Endpoints:
- POST /api/test/setup-credential - Set up a credential for testing
- POST /api/test/setup-expired-credential - Set up an expired credential
- POST /api/test/issue-credential - Issue a real signed credential using marty-rs
- POST /api/test/issue-open-badge - Issue an Open Badge (OB2/OB3)
- POST /api/test/verify-open-badge - Verify an Open Badge (OB2/OB3)
- POST /api/test/request-presentation - Create a presentation request
- POST /api/test/set-device-offline - Simulate device going offline
- POST /api/test/set-device-online - Simulate device coming back online
- POST /api/test/reset-user - Reset a test user's state
- GET /api/test/health - Health check for test environment
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Only enable in test/dev environments
ENABLE_TEST_ENDPOINTS = os.environ.get("ENABLE_TEST_ENDPOINTS", "false").lower() == "true"

# Try to import marty-rs bindings for real credential issuance
try:
    import _marty_rs as marty_rs
    MARTY_RS_AVAILABLE = True
    logger.info("marty-rs bindings available for test credential issuance")
except ImportError:
    MARTY_RS_AVAILABLE = False
    logger.warning("marty-rs bindings not available - using mock credentials")

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
    marty_rs_available: bool = False
    timestamp: str


# =============================================================================
# Real Credential Issuance Models (using marty-rs)
# =============================================================================


class IssueCredentialRequest(BaseModel):
    """Request to issue a real signed credential."""
    
    subject_did: str | None = Field(None, description="Holder's DID (optional)")
    credential_type: str = Field("TravelVisa", description="Credential type")
    claims: dict[str, Any] = Field(..., description="Claims to include in the credential")
    expiration_days: int = Field(365, description="Days until expiry")


class IssueCredentialResponse(BaseModel):
    """Response with real signed credential."""
    
    success: bool
    credential_id: str
    jwt: str  # The actual signed JWT credential
    offer_uri: str  # OID4VCI offer URI
    issuer_did: str
    message: str


class IssueOpenBadgeRequest(BaseModel):
    """Request to issue an Open Badge credential."""

    version: Literal["v2", "v3"] = Field("v2", description="Open Badges version")
    issuer_name: str = Field("Marty Issuer", description="Issuer display name")
    recipient_identity: str = Field("user@example.org", description="Recipient identity")
    recipient_name: str | None = Field(None, description="Recipient display name")
    badge_name: str = Field("Marty Open Badge", description="Badge name")
    badge_description: str = Field(
        "Issued by Marty for testing",
        description="Badge description",
    )
    include_document_store: bool = Field(
        True,
        description="Include verification document_store in response",
    )


class IssueOpenBadgeResponse(BaseModel):
    """Response with issued Open Badge credential."""

    success: bool
    issued: bool
    version: str
    credential: dict[str, Any]
    document_store: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    message: str | None = None


class VerifyOpenBadgeRequest(BaseModel):
    """Request to verify an Open Badge credential."""

    version: Literal["v2", "v3"] = Field("v2", description="Open Badges version")
    credential: dict[str, Any] = Field(..., description="Credential or assertion JSON")
    document_store: dict[str, Any] | None = Field(
        None,
        description="Document store for verification",
    )
    recipient_identity: str | None = Field(None, description="Expected recipient identity")


class VerifyOpenBadgeResponse(BaseModel):
    """Response with Open Badge verification result."""

    success: bool
    valid: bool
    version: str
    errors: list[str] = Field(default_factory=list)
    error_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    normalized: dict[str, Any] | None = None
    message: str | None = None


class RequestPresentationRequest(BaseModel):
    """Request to create a presentation request."""
    
    verifier_did: str | None = Field(None, description="Verifier's DID (generated if not provided)")
    requested_credentials: list[str] = Field(
        default=["TravelVisa"],
        description="Types of credentials being requested"
    )
    nonce: str | None = Field(None, description="Challenge nonce (generated if not provided)")
    redirect_uri: str = Field(
        "https://verifier.marty.demo/callback",
        description="Redirect URI after presentation"
    )


class RequestPresentationResponse(BaseModel):
    """Response with presentation request."""
    
    success: bool
    request_id: str
    request_uri: str  # OID4VP request URI
    nonce: str
    verifier_did: str
    message: str


# =============================================================================
# In-memory test state
# =============================================================================

# Track device online/offline state for testing
_device_states: dict[str, bool] = {}  # device_id -> is_online

# Track test credentials
_test_credentials: dict[str, dict] = {}  # credential_id -> credential data

# Issuer key pair (generated on first use)
_issuer_key: dict | None = None

# Pending presentation requests
_presentation_requests: dict[str, dict] = {}  # request_id -> request data


def _get_or_create_issuer_key() -> dict:
    """Get or create a test issuer key pair using marty-rs."""
    global _issuer_key
    
    if _issuer_key is not None:
        return _issuer_key
    
    if MARTY_RS_AVAILABLE:
        try:
            import json
            result_json = marty_rs.generate_ed25519_key()
            _issuer_key = json.loads(result_json)
            logger.info(f"Generated issuer DID: {_issuer_key['did']}")
            return _issuer_key
        except Exception as e:
            logger.error(f"Failed to generate issuer key: {e}")
    
    # Fallback to mock key
    _issuer_key = {
        "did": "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK",
        "jwk": {"kty": "OKP", "crv": "Ed25519", "x": "mock_public_key"},
        "keyId": "key_test_issuer"
    }
    return _issuer_key


def _public_jwk(jwk: dict[str, Any]) -> dict[str, Any]:
    """Strip private key material from a JWK."""
    return {key: value for key, value in jwk.items() if key not in {"d"}}


def _iso_timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _build_ob2_issue_request(
    body: IssueOpenBadgeRequest, issuer_key: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], str]:
    issuer_did = issuer_key["did"]
    verification_method = f"{issuer_did}#key-1"
    badge_id = f"urn:uuid:{uuid4()}"
    assertion_id = f"urn:uuid:{uuid4()}"

    issuer = {"id": issuer_did, "type": "Issuer", "name": body.issuer_name}
    badge = {
        "id": badge_id,
        "type": "BadgeClass",
        "name": body.badge_name,
        "description": body.badge_description,
        "issuer": issuer,
    }
    recipient = {
        "identity": body.recipient_identity,
        "type": "email",
        "hashed": False,
    }
    if body.recipient_name:
        recipient["name"] = body.recipient_name

    assertion = {
        "@context": "https://w3id.org/openbadges/v2",
        "id": assertion_id,
        "type": "Assertion",
        "badge": badge,
        "issuedOn": _iso_timestamp(),
        "recipient": recipient,
    }

    request = {
        "assertion": assertion,
        "signing": {
            "jwk": issuer_key["jwk"],
            "creator": verification_method,
            "verification_type": "signed",
        },
    }

    store = {
        verification_method: {
            "id": verification_method,
            "publicKeyJwk": _public_jwk(issuer_key["jwk"]),
        },
        issuer_did: issuer,
        badge_id: badge,
    }

    return request, store, verification_method


def _build_ob3_issue_request(
    body: IssueOpenBadgeRequest, issuer_key: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], str]:
    issuer_did = issuer_key["did"]
    verification_method = f"{issuer_did}#key-1"
    credential_id = f"urn:uuid:{uuid4()}"
    achievement_id = f"urn:uuid:{uuid4()}"

    credential = {
        "@context": [
            "https://www.w3.org/ns/credentials/v2",
            "https://purl.imsglobal.org/spec/ob/v3p0/context.json",
        ],
        "id": credential_id,
        "type": [
            "OpenBadgeCredential",
            "AchievementCredential",
            "VerifiableCredential",
        ],
        "issuer": {"id": issuer_did, "name": body.issuer_name},
        "issuanceDate": _iso_timestamp(),
        "credentialSubject": {
            "id": body.recipient_identity,
            "type": "AchievementSubject",
            "name": body.recipient_name or body.recipient_identity,
            "achievement": {
                "id": achievement_id,
                "type": "Achievement",
                "name": body.badge_name,
                "description": body.badge_description,
            },
            "recipient": {"identity": body.recipient_identity, "type": "email"},
        },
    }

    request = {
        "credential": credential,
        "signing": {
            "jwk": issuer_key["jwk"],
            "verification_method": verification_method,
            "verification_method_type": "JsonWebKey2020",
            "controller": issuer_did,
            "proof_purpose": "assertionMethod",
        },
    }

    store = {
        verification_method: {
            "id": verification_method,
            "type": "JsonWebKey2020",
            "controller": issuer_did,
            "publicKeyJwk": _public_jwk(issuer_key["jwk"]),
        }
    }

    return request, store, verification_method


def _context_contains(value: dict[str, Any], needle: str) -> bool:
    context = value.get("@context") or value.get("context")
    if isinstance(context, str):
        return needle in context
    if isinstance(context, list):
        return any(isinstance(item, str) and needle in item for item in context)
    return False


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
        marty_rs_available=MARTY_RS_AVAILABLE,
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


@router.post("/issue-credential", response_model=IssueCredentialResponse)
async def issue_credential(body: IssueCredentialRequest):
    """Issue a real signed credential using marty-rs.
    
    This endpoint creates a cryptographically signed VC JWT that can be
    verified by the marty verification stack. Use this for E2E tests that
    need real credentials.
    """
    _check_test_mode()
    
    import json
    
    issuer_key = _get_or_create_issuer_key()
    credential_id = str(uuid4())
    
    # Calculate expiration
    expiration_seconds = body.expiration_days * 24 * 60 * 60
    
    if MARTY_RS_AVAILABLE:
        try:
            # Use marty-rs to create a real signed credential
            result_json = marty_rs.create_verifiable_credential(
                issuer_did=issuer_key["did"],
                issuer_jwk_json=json.dumps(issuer_key["jwk"]),
                subject_id=body.subject_did,
                credential_type=body.credential_type,
                claims_json=json.dumps(body.claims),
                expiration_seconds=expiration_seconds,
            )
            result = json.loads(result_json)
            jwt = result["jwt"]
            credential_id = result["credentialId"]
            
        except Exception as e:
            logger.error(f"Failed to issue credential with marty-rs: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create credential: {e}"
            )
    else:
        # Create mock JWT for testing without marty-rs
        jwt = f"eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.mock_payload_{credential_id}.mock_signature"
    
    # Create OID4VCI offer
    offer_uri = f"openid-credential-offer://?credential_offer_uri=https://issuer.marty.demo/offers/{credential_id}"
    
    # Store for later verification
    _test_credentials[credential_id] = {
        "id": credential_id,
        "credential_type": body.credential_type,
        "claims": body.claims,
        "jwt": jwt,
        "issuer_did": issuer_key["did"],
        "subject_did": body.subject_did,
        "status": "issued",
        "created_at": datetime.utcnow().isoformat(),
    }
    
    logger.info(f"Issued credential: {credential_id} type={body.credential_type}")
    
    return IssueCredentialResponse(
        success=True,
        credential_id=credential_id,
        jwt=jwt,
        offer_uri=offer_uri,
        issuer_did=issuer_key["did"],
        message=f"Credential issued: {credential_id}",
    )


@router.post("/issue-open-badge", response_model=IssueOpenBadgeResponse)
async def issue_open_badge(body: IssueOpenBadgeRequest):
    """Issue an Open Badge (OB2 or OB3) using marty-rs."""
    _check_test_mode()

    issuer_key = _get_or_create_issuer_key()
    warnings: list[str] = []

    if body.version == "v3":
        request, store, _ = _build_ob3_issue_request(body, issuer_key)
        default_version = "3.0"
        issue_fn = getattr(marty_rs, "open_badge_ob3_issue", None) if MARTY_RS_AVAILABLE else None
    else:
        request, store, _ = _build_ob2_issue_request(body, issuer_key)
        default_version = "2.0"
        issue_fn = getattr(marty_rs, "open_badge_ob2_issue", None) if MARTY_RS_AVAILABLE else None

    if MARTY_RS_AVAILABLE and issue_fn is not None:
        try:
            result_json = issue_fn(json.dumps(request))
            result = json.loads(result_json)
            credential = result.get("credential") or {}
            issued = bool(result.get("issued", False))
            version = str(result.get("version", default_version))
            warnings = list(result.get("warnings", []))
        except Exception as e:
            logger.error(f"Failed to issue Open Badge: {e}")
            raise HTTPException(status_code=500, detail=f"Open Badge issuance failed: {e}")
    else:
        warnings.append("marty-rs not available; issued unsigned Open Badge")
        credential = request.get("credential") or request.get("assertion") or {}
        issued = True
        version = default_version

    document_store = store if body.include_document_store else None

    return IssueOpenBadgeResponse(
        success=True,
        issued=issued,
        version=version,
        credential=credential,
        document_store=document_store,
        warnings=warnings,
        message="Open Badge issued",
    )


@router.post("/verify-open-badge", response_model=VerifyOpenBadgeResponse)
async def verify_open_badge(body: VerifyOpenBadgeRequest):
    """Verify an Open Badge (OB2 or OB3) using marty-rs."""
    _check_test_mode()

    warnings: list[str] = []

    if body.version == "v3":
        request = {"credential": body.credential, "document_store": body.document_store}
        verify_fn = getattr(marty_rs, "open_badge_ob3_verify", None) if MARTY_RS_AVAILABLE else None
        default_version = "3.0"
    else:
        request = {
            "assertion": body.credential,
            "document_store": body.document_store,
            "recipient_identity": body.recipient_identity,
        }
        verify_fn = getattr(marty_rs, "open_badge_ob2_verify", None) if MARTY_RS_AVAILABLE else None
        default_version = "2.0"

    if MARTY_RS_AVAILABLE and verify_fn is not None:
        try:
            result_json = verify_fn(json.dumps(request))
            result = json.loads(result_json)
            return VerifyOpenBadgeResponse(
                success=True,
                valid=bool(result.get("valid", False)),
                version=str(result.get("version", default_version)),
                errors=list(result.get("errors", [])),
                error_codes=list(result.get("error_codes", [])),
                warnings=list(result.get("warnings", [])),
                normalized=result.get("normalized"),
                message="Open Badge verification completed",
            )
        except Exception as e:
            logger.error(f"Failed to verify Open Badge: {e}")
            raise HTTPException(status_code=500, detail=f"Open Badge verification failed: {e}")

    warnings.append("marty-rs not available; performed minimal Open Badge checks")
    credential = body.credential
    if body.version == "v3":
        valid = _context_contains(credential, "openbadges/v3") or _context_contains(
            credential, "ob/v3p0/context.json"
        )
        types = credential.get("type", [])
        if isinstance(types, str):
            types = [types]
        valid = bool(valid and ("OpenBadgeCredential" in types or "AchievementCredential" in types))
    else:
        valid = _context_contains(credential, "openbadges/v2") and credential.get("type") == "Assertion"
        valid = bool(valid and credential.get("badge"))

    return VerifyOpenBadgeResponse(
        success=True,
        valid=valid,
        version=default_version,
        warnings=warnings,
        normalized=None,
        message="Open Badge verification completed (minimal checks)",
    )


@router.post("/request-presentation", response_model=RequestPresentationResponse)
async def request_presentation(body: RequestPresentationRequest):
    """Create an OID4VP presentation request.
    
    This creates a presentation request that can be scanned by the wallet
    to initiate a credential presentation flow.
    """
    _check_test_mode()
    
    import json
    import base64
    
    request_id = str(uuid4())
    nonce = body.nonce or str(uuid4())
    
    # Generate or use provided verifier DID
    if body.verifier_did:
        verifier_did = body.verifier_did
    elif MARTY_RS_AVAILABLE:
        try:
            result_json = marty_rs.generate_ed25519_key()
            result = json.loads(result_json)
            verifier_did = result["did"]
        except Exception as e:
            logger.warning(f"Failed to generate verifier key: {e}")
            verifier_did = f"did:key:z6Mk{request_id[:32]}"
    else:
        verifier_did = f"did:key:z6Mk{request_id[:32]}"
    
    # Create presentation request following OID4VP spec
    presentation_request = {
        "client_id": verifier_did,
        "client_id_scheme": "did",
        "response_type": "vp_token",
        "response_mode": "direct_post",
        "nonce": nonce,
        "redirect_uri": body.redirect_uri,
        "presentation_definition": {
            "id": request_id,
            "input_descriptors": [
                {
                    "id": f"descriptor_{i}",
                    "purpose": f"Verify {cred_type}",
                    "constraints": {
                        "fields": [
                            {
                                "path": ["$.type"],
                                "filter": {
                                    "type": "array",
                                    "contains": {"const": cred_type}
                                }
                            }
                        ]
                    }
                }
                for i, cred_type in enumerate(body.requested_credentials)
            ]
        }
    }
    
    # Store request for verification later
    _presentation_requests[request_id] = {
        "id": request_id,
        "verifier_did": verifier_did,
        "nonce": nonce,
        "request": presentation_request,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
    }
    
    # Create OID4VP request URI
    request_uri = f"openid4vp://?request_uri=https://verifier.marty.demo/requests/{request_id}"
    
    logger.info(f"Created presentation request: {request_id}")
    
    return RequestPresentationResponse(
        success=True,
        request_id=request_id,
        request_uri=request_uri,
        nonce=nonce,
        verifier_did=verifier_did,
        message=f"Presentation request created: {request_id}",
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


# =============================================================================
# Verification Endpoint for E2E Tests
# =============================================================================


class VerifyPresentationTestRequest(BaseModel):
    """Request to verify a presentation in test mode."""
    
    vp_jwt: str = Field(..., description="The VP JWT to verify")
    request_id: str | None = Field(None, description="Request ID to validate against")
    expected_nonce: str | None = Field(None, description="Expected nonce")
    expected_audience: str | None = Field(None, description="Expected audience/verifier DID")


class VerifyPresentationTestResponse(BaseModel):
    """Response from test presentation verification."""
    
    success: bool
    valid: bool
    holder_did: str | None = None
    credentials: list[dict[str, Any]] = []
    error: str | None = None
    message: str


@router.post("/verify-presentation", response_model=VerifyPresentationTestResponse)
async def verify_presentation_test(body: VerifyPresentationTestRequest):
    """Verify a presentation JWT for E2E testing.
    
    This performs JWT structure validation and extracts credentials.
    For full cryptographic verification, use the main /api/verifier endpoints.
    """
    _check_test_mode()
    
    import json
    import base64
    
    # If request_id provided, get expected values from stored request
    expected_nonce = body.expected_nonce
    expected_audience = body.expected_audience
    
    if body.request_id and body.request_id in _presentation_requests:
        stored = _presentation_requests[body.request_id]
        expected_nonce = expected_nonce or stored.get("nonce")
        expected_audience = expected_audience or stored.get("verifier_did")
    
    if MARTY_RS_AVAILABLE:
        try:
            # Use marty-rs for JWT verification
            verify_result_json = marty_rs.verify_jwt_claims(
                jwt=body.vp_jwt,
                expected_issuer=None,  # VP issuer is the holder
                expected_audience=expected_audience,
            )
            verify_result = json.loads(verify_result_json)
            
            if not verify_result.get("valid"):
                return VerifyPresentationTestResponse(
                    success=True,
                    valid=False,
                    error=verify_result.get("error", "JWT validation failed"),
                    message="Presentation validation failed",
                )
            
            # Extract credentials from the VP
            creds_json = marty_rs.extract_credentials_from_vp(body.vp_jwt)
            credentials = json.loads(creds_json)
            
            # Check nonce if expected
            payload = verify_result.get("payload", {})
            vp = payload.get("vp", {})
            actual_nonce = vp.get("nonce") or payload.get("nonce")
            
            if expected_nonce and actual_nonce != expected_nonce:
                return VerifyPresentationTestResponse(
                    success=True,
                    valid=False,
                    error=f"Nonce mismatch: expected {expected_nonce}, got {actual_nonce}",
                    message="Nonce validation failed",
                )
            
            holder_did = payload.get("iss") or vp.get("holder")
            
            # Mark request as completed if we have one
            if body.request_id and body.request_id in _presentation_requests:
                _presentation_requests[body.request_id]["status"] = "verified"
            
            logger.info(f"Verified presentation from holder: {holder_did}")
            
            return VerifyPresentationTestResponse(
                success=True,
                valid=True,
                holder_did=holder_did,
                credentials=credentials,
                message=f"Presentation verified successfully with {len(credentials)} credentials",
            )
            
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return VerifyPresentationTestResponse(
                success=False,
                valid=False,
                error=str(e),
                message="Verification encountered an error",
            )
    else:
        # Mock verification without marty-rs
        try:
            # Basic JWT structure check
            parts = body.vp_jwt.split(".")
            if len(parts) != 3:
                return VerifyPresentationTestResponse(
                    success=True,
                    valid=False,
                    error="Invalid JWT structure",
                    message="JWT must have 3 parts",
                )
            
            # Decode payload (without signature verification)
            payload_b64 = parts[1]
            # Add padding
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            
            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            payload = json.loads(payload_bytes)
            
            holder_did = payload.get("iss") or payload.get("vp", {}).get("holder")
            
            return VerifyPresentationTestResponse(
                success=True,
                valid=True,  # Mock always passes
                holder_did=holder_did,
                credentials=[],
                message="Mock verification passed (no crypto validation)",
            )
            
        except Exception as e:
            return VerifyPresentationTestResponse(
                success=False,
                valid=False,
                error=str(e),
                message="Mock verification failed",
            )


@router.get("/presentation-requests")
async def list_presentation_requests():
    """List all pending presentation requests (for debugging)."""
    _check_test_mode()
    
    return {
        "count": len(_presentation_requests),
        "requests": list(_presentation_requests.values()),
    }


@router.delete("/presentation-requests")
async def clear_presentation_requests():
    """Clear all presentation requests."""
    _check_test_mode()
    
    count = len(_presentation_requests)
    _presentation_requests.clear()
    
    return {
        "success": True,
        "cleared": count,
        "message": f"Cleared {count} presentation requests",
    }


# =============================================================================
# Wallet Device Registration (for push notifications)
# =============================================================================

# In-memory wallet device registry
_wallet_devices: dict[str, dict] = {}  # device_id -> device data
_push_notifications: list[dict] = []  # Sent notifications for testing


class WalletRegisterRequest(BaseModel):
    """Request to register a wallet device for push notifications."""
    
    push_token: str = Field(..., description="FCM/APNs push token")
    platform: str = Field("ios", description="Platform (ios/android/web)")
    wallet_did: str | None = Field(None, description="Wallet's DID")
    user_id: str | None = Field(None, description="Associated user ID")


class WalletRegisterResponse(BaseModel):
    """Response after registering wallet device."""
    
    success: bool
    device_id: str
    message: str


class WalletPairRequest(BaseModel):
    """Request to pair wallet with user account."""
    
    pairing_code: str = Field(..., description="QR code pairing code")
    wallet_did: str = Field(..., description="Wallet's DID")
    push_token: str | None = Field(None, description="Push notification token")


class WalletPairResponse(BaseModel):
    """Response after pairing wallet."""
    
    success: bool
    session_id: str
    user_id: str | None
    message: str


class SendPushNotificationRequest(BaseModel):
    """Request to send a push notification to a wallet."""
    
    device_id: str | None = Field(None, description="Target device ID")
    user_id: str | None = Field(None, description="Target user ID")
    notification_type: str = Field("credential_offer", description="Type of notification")
    title: str = Field("New Notification", description="Notification title")
    body: str = Field("", description="Notification body")
    data: dict[str, Any] = Field(default_factory=dict, description="Notification payload data")


class SendPushNotificationResponse(BaseModel):
    """Response after sending push notification."""
    
    success: bool
    notification_id: str
    delivered_to: list[str]
    message: str


@router.post("/wallet/register", response_model=WalletRegisterResponse)
async def register_wallet_device(body: WalletRegisterRequest):
    """Register a wallet device for push notifications.
    
    This endpoint stores the push token for later notification delivery.
    """
    _check_test_mode()
    
    device_id = str(uuid4())
    
    _wallet_devices[device_id] = {
        "device_id": device_id,
        "push_token": body.push_token,
        "platform": body.platform,
        "wallet_did": body.wallet_did,
        "user_id": body.user_id,
        "is_active": True,
        "created_at": datetime.utcnow().isoformat(),
        "last_seen_at": datetime.utcnow().isoformat(),
    }
    
    logger.info(f"Registered wallet device: {device_id} (platform: {body.platform})")
    
    return WalletRegisterResponse(
        success=True,
        device_id=device_id,
        message=f"Device registered successfully",
    )


@router.post("/wallet/pair", response_model=WalletPairResponse)
async def pair_wallet(body: WalletPairRequest):
    """Pair a wallet with a user account using QR code.
    
    The pairing code is obtained by scanning a QR code displayed in the web UI.
    """
    _check_test_mode()
    
    # In a real implementation, this would validate the pairing code
    # and associate the wallet DID with the user's account
    session_id = str(uuid4())
    
    # Mock user lookup - in reality would decode pairing code
    user_id = f"user_{body.pairing_code[:8]}"
    
    # Register device if push token provided
    device_id = None
    if body.push_token:
        device_id = str(uuid4())
        _wallet_devices[device_id] = {
            "device_id": device_id,
            "push_token": body.push_token,
            "platform": "unknown",
            "wallet_did": body.wallet_did,
            "user_id": user_id,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
        }
    
    logger.info(f"Paired wallet {body.wallet_did} with user {user_id}")
    
    return WalletPairResponse(
        success=True,
        session_id=session_id,
        user_id=user_id,
        message="Wallet paired successfully",
    )


@router.get("/wallet/status")
async def get_wallet_status(device_id: str | None = None, user_id: str | None = None):
    """Get wallet device status.
    
    Returns connection status and last seen time for the wallet device.
    """
    _check_test_mode()
    
    if device_id and device_id in _wallet_devices:
        device = _wallet_devices[device_id]
        return {
            "connected": True,
            "device_id": device_id,
            "platform": device.get("platform"),
            "wallet_did": device.get("wallet_did"),
            "last_seen_at": device.get("last_seen_at"),
            "is_active": device.get("is_active", True),
        }
    
    if user_id:
        user_devices = [d for d in _wallet_devices.values() if d.get("user_id") == user_id]
        if user_devices:
            return {
                "connected": True,
                "devices": user_devices,
                "device_count": len(user_devices),
            }
    
    return {
        "connected": False,
        "message": "No wallet device found",
    }


@router.get("/wallet/devices")
async def list_wallet_devices():
    """List all registered wallet devices (for debugging)."""
    _check_test_mode()
    
    return {
        "count": len(_wallet_devices),
        "devices": list(_wallet_devices.values()),
    }


@router.delete("/wallet/devices")
async def clear_wallet_devices():
    """Clear all registered wallet devices."""
    _check_test_mode()
    
    count = len(_wallet_devices)
    _wallet_devices.clear()
    
    return {
        "success": True,
        "cleared": count,
        "message": f"Cleared {count} wallet devices",
    }


@router.post("/send-push-notification", response_model=SendPushNotificationResponse)
async def send_push_notification(body: SendPushNotificationRequest):
    """Send a push notification to a wallet device.
    
    This is a test endpoint that simulates sending push notifications.
    In a real implementation, this would use FCM/APNs.
    """
    _check_test_mode()
    
    notification_id = str(uuid4())
    delivered_to = []
    
    # Find target devices
    target_devices = []
    if body.device_id and body.device_id in _wallet_devices:
        target_devices.append(_wallet_devices[body.device_id])
    elif body.user_id:
        target_devices = [d for d in _wallet_devices.values() if d.get("user_id") == body.user_id]
    
    if not target_devices:
        return SendPushNotificationResponse(
            success=False,
            notification_id=notification_id,
            delivered_to=[],
            message="No target devices found",
        )
    
    # "Send" notification (store for testing)
    notification = {
        "notification_id": notification_id,
        "type": body.notification_type,
        "title": body.title,
        "body": body.body,
        "data": body.data,
        "sent_at": datetime.utcnow().isoformat(),
        "targets": [d["device_id"] for d in target_devices],
    }
    _push_notifications.append(notification)
    delivered_to = [d["device_id"] for d in target_devices]
    
    logger.info(f"Sent push notification {notification_id} to {len(delivered_to)} devices")
    
    return SendPushNotificationResponse(
        success=True,
        notification_id=notification_id,
        delivered_to=delivered_to,
        message=f"Notification sent to {len(delivered_to)} devices",
    )


@router.get("/push-notifications")
async def list_push_notifications():
    """List all sent push notifications (for testing)."""
    _check_test_mode()
    
    return {
        "count": len(_push_notifications),
        "notifications": _push_notifications,
    }


@router.delete("/push-notifications")
async def clear_push_notifications():
    """Clear all push notifications."""
    _check_test_mode()
    
    count = len(_push_notifications)
    _push_notifications.clear()
    
    return {
        "success": True,
        "cleared": count,
        "message": f"Cleared {count} push notifications",
    }


# Pairing codes for QR code wallet pairing
_pairing_codes: dict[str, dict] = {}  # code -> pairing data


@router.post("/wallet/generate-pairing-code")
async def generate_pairing_code(user_id: str | None = None):
    """Generate a pairing code for QR code wallet pairing.
    
    The QR code displayed in the UI contains this code.
    """
    _check_test_mode()
    
    code = str(uuid4())[:8].upper()  # Short code for easy scanning
    
    _pairing_codes[code] = {
        "code": code,
        "user_id": user_id,
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": (datetime.utcnow() + timedelta(minutes=5)).isoformat(),
        "used": False,
    }
    
    # Generate QR content (deep link)
    qr_content = f"marty://pair?code={code}"
    
    return {
        "success": True,
        "code": code,
        "qr_content": qr_content,
        "expires_in_seconds": 300,
    }


# =============================================================================
# Device Registration (for push challenge flow tests)
# =============================================================================

# In-memory device registry for tests
_registered_devices: dict[str, dict] = {}  # device_id -> device data


class DeviceRegisterRequest(BaseModel):
    """Request to register a device for push notifications."""
    
    device_id: str = Field(..., description="Unique device identifier (can be org_id:device_id format)")
    fcm_token: str = Field(..., description="FCM/APNs push token")
    platform: str = Field("web", description="Platform (ios/android/web)")
    app_version: str | None = Field(None, description="App version")
    os_version: str | None = Field(None, description="OS version")
    device_model: str | None = Field(None, description="Device model")
    public_key: str | None = Field(None, description="Base64-encoded DER public key for challenge signing")


# Create a separate router for device endpoints (mounted at /api/devices)
devices_router = APIRouter(prefix="/devices", tags=["devices"])


@devices_router.post("/register", status_code=201)
async def register_device(
    body: DeviceRegisterRequest,
    x_user_id: str | None = None,
):
    """Register a device for push notifications.
    
    Device ID can be in format 'org_id:device_id' to associate with an organization.
    """
    _check_test_mode()
    
    device_id = body.device_id
    org_id = None
    
    # Parse organization ID from device_id if present
    if ":" in device_id:
        org_id, _ = device_id.split(":", 1)
    
    # Check if device already registered (update)
    existing = _registered_devices.get(device_id)
    registration_id = existing.get("registration_id") if existing else str(uuid4())
    
    device_data = {
        "device_id": device_id,
        "registration_id": registration_id,
        "organization_id": org_id,
        "user_id": x_user_id,
        "fcm_token": body.fcm_token,
        "platform": body.platform,
        "app_version": body.app_version,
        "os_version": body.os_version,
        "device_model": body.device_model,
        "public_key": body.public_key,
        "is_active": True,
        "created_at": existing.get("created_at") if existing else datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    
    _registered_devices[device_id] = device_data
    
    logger.info(f"Registered device: {device_id} for user {x_user_id}")
    
    return {
        "device_id": device_id,
        "registration_id": registration_id,
        "organization_id": org_id,
        "success": True,
    }


@devices_router.get("")
async def list_devices(
    user_id: str | None = None,
    org_id: str | None = None,
):
    """List registered devices, optionally filtered by user or organization."""
    _check_test_mode()
    
    devices = list(_registered_devices.values())
    
    if user_id:
        devices = [d for d in devices if d.get("user_id") == user_id]
    
    if org_id:
        devices = [d for d in devices if d.get("organization_id") == org_id]
    
    return devices


@devices_router.get("/{device_id}")
async def get_device(device_id: str):
    """Get a specific device by ID."""
    _check_test_mode()
    
    if device_id not in _registered_devices:
        raise HTTPException(status_code=404, detail="Device not found")
    
    return _registered_devices[device_id]


@devices_router.delete("/{device_id}")
async def unregister_device(device_id: str):
    """Unregister a device."""
    _check_test_mode()
    
    if device_id not in _registered_devices:
        raise HTTPException(status_code=404, detail="Device not found")
    
    del _registered_devices[device_id]
    
    return {"success": True, "message": f"Device {device_id} unregistered"}


@devices_router.delete("")
async def clear_devices():
    """Clear all registered devices (test cleanup)."""
    _check_test_mode()
    
    count = len(_registered_devices)
    _registered_devices.clear()
    
    return {"success": True, "cleared": count}


# =============================================================================
# Push Challenges (for push challenge flow tests)
# =============================================================================

# In-memory challenge store
_push_challenges: dict[str, dict] = {}  # challenge_id -> challenge data


class CreateChallengeRequest(BaseModel):
    """Request to create a push challenge."""
    
    title: str = Field("Authentication Request", description="Challenge title")
    question: str = Field("Do you approve this action?", description="Challenge question")
    nonce: str = Field(..., description="Unique nonce for signing")
    ttl_seconds: int = Field(120, description="Time-to-live in seconds")


class RespondToChallengeRequest(BaseModel):
    """Request to respond to a push challenge."""
    
    response: str = Field(..., description="Response: 'accept' or 'reject'")
    signature: str | None = Field(None, description="Base64-encoded signature of nonce")


# Create push router (mounted at /api/push)
push_router = APIRouter(prefix="/push", tags=["push"])


@push_router.post("/challenges/{device_id}")
async def create_push_challenge(device_id: str, body: CreateChallengeRequest):
    """Create a push challenge for a device."""
    _check_test_mode()
    
    if device_id not in _registered_devices:
        raise HTTPException(status_code=404, detail="Device not registered")
    
    challenge_id = str(uuid4())
    expires_at = datetime.utcnow() + timedelta(seconds=body.ttl_seconds)
    
    challenge = {
        "challenge_id": challenge_id,
        "device_id": device_id,
        "title": body.title,
        "question": body.question,
        "nonce": body.nonce,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": expires_at.isoformat(),
        "response": None,
        "responded_at": None,
    }
    
    _push_challenges[challenge_id] = challenge
    
    logger.info(f"Created push challenge {challenge_id} for device {device_id}")
    
    return challenge


@push_router.get("/challenges/{device_id}/pending")
async def get_pending_challenges(device_id: str):
    """Get pending challenges for a device."""
    _check_test_mode()
    
    now = datetime.utcnow()
    pending = []
    
    for challenge in _push_challenges.values():
        if challenge["device_id"] != device_id:
            continue
        if challenge["status"] != "pending":
            continue
        if datetime.fromisoformat(challenge["expires_at"]) < now:
            continue
        pending.append(challenge)
    
    return pending


@push_router.post("/challenges/{device_id}/{challenge_id}/respond")
async def respond_to_challenge(
    device_id: str,
    challenge_id: str,
    body: RespondToChallengeRequest,
):
    """Respond to a push challenge."""
    _check_test_mode()
    
    if challenge_id not in _push_challenges:
        raise HTTPException(status_code=404, detail="Challenge not found")
    
    challenge = _push_challenges[challenge_id]
    
    if challenge["device_id"] != device_id:
        raise HTTPException(status_code=403, detail="Device mismatch")
    
    if challenge["status"] != "pending":
        raise HTTPException(status_code=400, detail="Challenge already responded")
    
    # In a real implementation, we'd verify the signature here
    # For testing, we accept the response as-is
    
    challenge["status"] = "completed"
    challenge["response"] = body.response
    challenge["responded_at"] = datetime.utcnow().isoformat()
    
    logger.info(f"Challenge {challenge_id} responded with: {body.response}")
    
    return {
        "success": True,
        "challenge_id": challenge_id,
        "response": body.response,
    }


@push_router.delete("/challenges")
async def clear_all_challenges():
    """Clear all challenges (test cleanup)."""
    _check_test_mode()
    
    count = len(_push_challenges)
    _push_challenges.clear()
    
    return {"success": True, "cleared": count}
