"""OID4VCI Issuer API - FastAPI REST facade for Document Signer gRPC service."""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from io import BytesIO
from typing import Any
from urllib.parse import urlencode

import grpc
import qrcode
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from marty_plugin.proto.v1 import document_signer_pb2, document_signer_pb2_grpc

# Import wallet backup router
try:
    from wallet.backup_api import router as wallet_backup_router
    WALLET_BACKUP_AVAILABLE = True
except ImportError:
    WALLET_BACKUP_AVAILABLE = False
    wallet_backup_router = None

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Marty OID4VCI Issuer API",
    description="OpenID for Verifiable Credential Issuance - Microsoft Authenticator Compatible",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# gRPC client setup - configured via environment variables
DOCUMENT_SIGNER_HOST = os.getenv("DOCUMENT_SIGNER_HOST", "localhost")
DOCUMENT_SIGNER_PORT = os.getenv("DOCUMENT_SIGNER_PORT", "8082")
GRPC_DOCUMENT_SIGNER_ADDRESS = f"{DOCUMENT_SIGNER_HOST}:{DOCUMENT_SIGNER_PORT}"
GRPC_TLS_ENABLED = os.getenv("GRPC_TLS_ENABLED", "false").lower() in ("true", "1", "yes")
GRPC_TLS_CA_CERT = os.getenv("GRPC_TLS_CA_CERT")
GRPC_TLS_CLIENT_CERT = os.getenv("GRPC_TLS_CLIENT_CERT")
GRPC_TLS_CLIENT_KEY = os.getenv("GRPC_TLS_CLIENT_KEY")
channel: grpc.Channel | None = None
document_signer_stub: document_signer_pb2_grpc.DocumentSignerStub | None = None

# Microsoft Authenticator / Entra Verified ID Configuration
ISSUER_BASE_URL = os.getenv("ISSUER_BASE_URL", "https://issuer.marty.local")
VERIFIER_BASE_URL = os.getenv("VERIFIER_BASE_URL", "https://verifier.marty.local")
CREDENTIAL_ISSUER_DID = os.getenv("CREDENTIAL_ISSUER_DID", "did:web:issuer.marty.local")

# SSE notification configuration for push delivery
SSE_NOTIFICATION_URL = os.getenv("SSE_NOTIFICATION_URL", "")


async def notify_credential_issued(device_id: str, credential_id: str, credential_type: str) -> None:
    """Send SSE notification when a credential is issued (for wallet push delivery)."""
    if not SSE_NOTIFICATION_URL:
        logger.debug("SSE notification URL not configured, skipping push notification")
        return
    
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{SSE_NOTIFICATION_URL}/api/events/push/send",
                params={"device_id": device_id},
                json={
                    "title": "Credential Issued",
                    "question": f"Your {credential_type} credential is ready",
                    "nonce": str(uuid.uuid4()),
                    "credential_id": credential_id,
                    "data": {"event": "credential_issued", "credential_type": credential_type},
                    "ttl_seconds": 300,
                },
                timeout=5.0,
            )
            logger.info(f"SSE notification sent for credential {credential_id} to device {device_id}")
    except Exception as e:
        logger.warning(f"Failed to send SSE notification: {e}")


def _read_tls_file(path: str | None) -> bytes | None:
    if not path:
        return None
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("TLS file not found: %s", path)
        return None


def get_grpc_client() -> document_signer_pb2_grpc.DocumentSignerStub:
    """Get or create the gRPC client."""
    global channel, document_signer_stub

    if document_signer_stub is None:
        if GRPC_TLS_ENABLED:
            credentials = grpc.ssl_channel_credentials(
                root_certificates=_read_tls_file(GRPC_TLS_CA_CERT),
                private_key=_read_tls_file(GRPC_TLS_CLIENT_KEY),
                certificate_chain=_read_tls_file(GRPC_TLS_CLIENT_CERT),
            )
            channel = grpc.secure_channel(GRPC_DOCUMENT_SIGNER_ADDRESS, credentials)
            logger.info("gRPC TLS channel to document-signer at %s", GRPC_DOCUMENT_SIGNER_ADDRESS)
        else:
            channel = grpc.insecure_channel(GRPC_DOCUMENT_SIGNER_ADDRESS)
        document_signer_stub = document_signer_pb2_grpc.DocumentSignerStub(channel)

    return document_signer_stub


def get_bearer_token(authorization: str = Header(None)) -> str:
    """Extract bearer token from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization[7:]  # Remove "Bearer " prefix


def generate_qr_code(data: str) -> str:
    """Generate base64-encoded QR code for the given data."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, "PNG")
    buffer.seek(0)

    return base64.b64encode(buffer.getvalue()).decode()


# Pydantic models for OID4VCI
class CredentialOfferRequest(BaseModel):
    """Request to create a credential offer."""

    subject_id: str = Field(..., description="Subject identifier for the credential")
    credential_type: str = Field(
        default="VerifiableCredential", description="Type of credential to issue"
    )
    base_claims: dict[str, Any] = Field(..., description="Base claims for the credential")
    selective_disclosures: dict[str, Any] = Field(
        ..., description="Claims available for selective disclosure"
    )
    metadata: dict[str, Any] | None = Field(default=None, description="Additional metadata")


class TokenRequest(BaseModel):
    """Token request for OID4VCI."""

    grant_type: str = Field(..., description="Grant type (pre-authorized_code)")
    pre_authorized_code: str = Field(alias="pre-authorized_code", description="Pre-authorized code")
    wallet_attestation: dict[str, Any] | None = Field(
        default=None, description="Wallet attestation"
    )


class CredentialRequest(BaseModel):
    """Credential request for OID4VCI."""

    format: str = Field(default="sd-jwt", description="Credential format")
    disclose_claims: list[str] = Field(default_factory=list, description="Claims to disclose")
    audience: str | None = Field(default=None, description="Intended audience")
    nonce: str | None = Field(default=None, description="Nonce for proof of possession")
    wallet_attestation: dict[str, Any] | None = Field(
        default=None, description="Wallet attestation"
    )


class QROfferRequest(BaseModel):
    """Request to generate QR code for credential offer."""

    credential_type: str = Field(
        default="MartyDigitalPassport", description="Type of credential to offer"
    )
    subject_claims: dict[str, Any] = Field(..., description="Subject claims for the credential")
    issuer_metadata: dict[str, Any] | None = Field(
        default=None, description="Additional issuer metadata"
    )


@app.get("/.well-known/openid-credential-issuer")
async def openid_credential_issuer_metadata() -> dict[str, Any]:
    """Return OpenID Credential Issuer metadata for Microsoft Authenticator compatibility."""
    return {
        "credential_issuer": ISSUER_BASE_URL,
        "authorization_servers": [ISSUER_BASE_URL],
        "credential_endpoint": f"{ISSUER_BASE_URL}/credential",
        "token_endpoint": f"{ISSUER_BASE_URL}/token",
        "credentials_supported": [
            {
                "format": "jwt_vc_json",
                "credential_definition": {
                    "type": ["VerifiableCredential", "MartyDigitalPassport"],
                    "credentialSubject": {
                        "given_name": {"display": [{"name": "Given Name", "locale": "en"}]},
                        "family_name": {"display": [{"name": "Family Name", "locale": "en"}]},
                        "nationality": {"display": [{"name": "Nationality", "locale": "en"}]},
                        "date_of_birth": {"display": [{"name": "Date of Birth", "locale": "en"}]},
                        "passport_number": {
                            "display": [{"name": "Passport Number", "locale": "en"}]
                        },
                        "issuing_country": {
                            "display": [{"name": "Issuing Country", "locale": "en"}]
                        },
                        "expiry_date": {"display": [{"name": "Expiry Date", "locale": "en"}]},
                    },
                },
                "display": [
                    {
                        "name": "Marty Digital Passport",
                        "locale": "en",
                        "background_color": "#1e3a8a",
                        "text_color": "#FFFFFF",
                        "logo": {
                            "url": f"{ISSUER_BASE_URL}/static/marty-logo.png",
                            "alt_text": "Marty Digital Identity",
                        },
                    }
                ],
            },
            {
                "format": "sd-jwt",
                "credential_definition": {
                    "type": ["VerifiableCredential"],
                    "credentialSubject": {
                        "given_name": {"display": [{"name": "Given Name", "locale": "en"}]},
                        "family_name": {"display": [{"name": "Family Name", "locale": "en"}]},
                        "email": {"display": [{"name": "Email", "locale": "en"}]},
                        "birthdate": {"display": [{"name": "Date of Birth", "locale": "en"}]},
                    },
                },
                "display": [
                    {
                        "name": "Verifiable Credential",
                        "locale": "en",
                        "background_color": "#12107c",
                        "text_color": "#FFFFFF",
                    }
                ],
            },
        ],
        "display": [
            {
                "name": "Marty Digital Identity Issuer",
                "locale": "en",
                "logo": {
                    "url": f"{ISSUER_BASE_URL}/static/marty-issuer-logo.png",
                    "alt_text": "Marty Digital Identity Issuer Logo",
                },
            }
        ],
    }


@app.post("/credential-offer")
async def create_credential_offer(request: CredentialOfferRequest) -> dict[str, Any]:
    """Create a credential offer."""
    try:
        client = get_grpc_client()

        grpc_request = document_signer_pb2.CreateCredentialOfferRequest(
            subject_id=request.subject_id,
            credential_type=request.credential_type,
            base_claims_json=json.dumps(request.base_claims),
            selective_disclosures_json=json.dumps(request.selective_disclosures),
            metadata_json=json.dumps(request.metadata) if request.metadata else "",
        )

        response = await client.CreateCredentialOffer(grpc_request)

        if response.error and response.error.code != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to create credential offer: {response.error.message}",
            )

        return {
            "offer_id": response.offer_id,
            "credential_offer": json.loads(response.credential_offer),
            "pre_authorized_code": response.pre_authorized_code,
            "expires_in": response.expires_in,
        }

    except grpc.RpcError as e:
        logger.exception("gRPC error creating credential offer")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Service error: {e.details()}",
        ) from e
    except Exception as e:
        logger.exception("Unexpected error creating credential offer")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error"
        ) from e


@app.post("/token")
async def token_endpoint(request: TokenRequest) -> dict[str, Any]:
    """Token endpoint for OID4VCI flow."""
    if request.grant_type != "urn:ietf:params:oauth:grant-type:pre-authorized_code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported grant type"
        )

    try:
        client = get_grpc_client()

        grpc_request = document_signer_pb2.RedeemPreAuthorizedCodeRequest(
            pre_authorized_code=request.pre_authorized_code,
            wallet_attestation=(
                json.dumps(request.wallet_attestation) if request.wallet_attestation else ""
            ),
        )

        response = await client.RedeemPreAuthorizedCode(grpc_request)

        if response.error and response.error.code != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to redeem code: {response.error.message}",
            )

        return {
            "access_token": response.access_token,
            "token_type": "Bearer",
            "expires_in": response.expires_in,
            "c_nonce": response.c_nonce,
        }

    except grpc.RpcError as e:
        logger.exception("gRPC error redeeming pre-authorized code")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Service error: {e.details()}",
        ) from e
    except Exception as e:
        logger.exception("Unexpected error redeeming pre-authorized code")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error"
        ) from e


@app.post("/credential")
async def credential_endpoint(
    request: CredentialRequest, access_token: str = Depends(get_bearer_token)
) -> dict[str, Any]:
    """Credential endpoint for OID4VCI flow."""
    try:
        client = get_grpc_client()

        grpc_request = document_signer_pb2.IssueSdJwtCredentialRequest(
            access_token=access_token,
            disclose_claims=request.disclose_claims,
            audience=request.audience or "",
            nonce=request.nonce or "",
            wallet_attestation=(
                json.dumps(request.wallet_attestation) if request.wallet_attestation else ""
            ),
        )

        response = await client.IssueSdJwtCredential(grpc_request)

        if response.error and response.error.code != 0:
            if response.error.code == 6:  # TOKEN_INVALID
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired access token",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to issue credential: {response.error.message}",
            )

        # Format the response based on requested format
        if request.format == "jwt_vc_json":
            # Microsoft Authenticator expects JWT VC JSON format
            return {
                "credential": response.credential,
                "format": "jwt_vc_json",
                "credential_id": response.credential_id,
                "expires_in": response.expires_in,
            }
        else:
            # Default SD-JWT format
            return {
                "credential": response.credential,
                "disclosures": response.disclosures,
                "format": response.format,
                "credential_id": response.credential_id,
                "expires_in": response.expires_in,
                "sd_jwt_location": response.sd_jwt_location,
                "disclosures_location": response.disclosures_location,
                "issuer": response.issuer,
                "credential_type": response.credential_type,
                "subject_id": response.subject_id,
            }

    except grpc.RpcError as e:
        logger.exception("gRPC error issuing credential")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Service error: {e.details()}",
        ) from e
    except Exception as e:
        logger.exception("Unexpected error issuing credential")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error"
        ) from e


@app.post("/offer")
async def create_qr_offer(request: QROfferRequest) -> dict[str, Any]:
    """Create a QR code offer for credential issuance compatible with Microsoft Authenticator."""
    try:
        # Create a credential offer
        offer_id = str(uuid.uuid4())
        pre_authorized_code = str(uuid.uuid4()).replace("-", "")

        # Construct the credential offer object compatible with Microsoft Authenticator
        credential_offer = {
            "credential_issuer": ISSUER_BASE_URL,
            "credentials": [
                {
                    "format": "jwt_vc_json",
                    "credential_definition": {
                        "type": ["VerifiableCredential", request.credential_type]
                    },
                }
            ],
            "grants": {
                "urn:ietf:params:oauth:grant-type:pre-authorized_code": {
                    "pre-authorized_code": pre_authorized_code,
                    "user_pin_required": False,
                }
            },
        }

        # Create the credential offer URI for Microsoft Authenticator
        offer_uri_params = {"credential_offer": json.dumps(credential_offer)}
        offer_uri = f"openid-credential-offer://?{urlencode(offer_uri_params)}"

        # Generate QR code
        qr_code_data = generate_qr_code(offer_uri)

        return {
            "offer_id": offer_id,
            "credential_offer_uri": offer_uri,
            "credential_offer": credential_offer,
            "pre_authorized_code": pre_authorized_code,
            "qr_code": f"data:image/png;base64,{qr_code_data}",
            "expires_in": 3600,  # 1 hour
        }

    except Exception as e:
        logger.exception("Unexpected error creating QR offer")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error"
        ) from e


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


# Include wallet backup router if available
if WALLET_BACKUP_AVAILABLE and wallet_backup_router:
    app.include_router(wallet_backup_router)
    logger.info("Wallet backup API routes registered")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
