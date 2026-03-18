"""OID4VP Verifier API - FastAPI REST facade for credential verification compatible with Microsoft Authenticator."""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any
from urllib.parse import urlencode

import grpc
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from marty_plugin.proto.v1 import inspection_system_pb2, inspection_system_pb2_grpc

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Marty OID4VP Verifier API",
    description="OpenID for Verifiable Presentations - Microsoft Authenticator Compatible",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# gRPC client setup - configured via environment variables
INSPECTION_SYSTEM_HOST = os.environ.get("INSPECTION_SYSTEM_HOST", "localhost")
INSPECTION_SYSTEM_PORT = os.environ.get("INSPECTION_SYSTEM_PORT", "8083")
GRPC_INSPECTION_SYSTEM_ADDRESS = f"{INSPECTION_SYSTEM_HOST}:{INSPECTION_SYSTEM_PORT}"
GRPC_TLS_ENABLED = os.environ.get("GRPC_TLS_ENABLED", "false").lower() in ("true", "1", "yes")
GRPC_TLS_CA_CERT = os.environ.get("GRPC_TLS_CA_CERT")
GRPC_TLS_CLIENT_CERT = os.environ.get("GRPC_TLS_CLIENT_CERT")
GRPC_TLS_CLIENT_KEY = os.environ.get("GRPC_TLS_CLIENT_KEY")
channel: grpc.Channel | None = None
inspection_system_stub: inspection_system_pb2_grpc.InspectionSystemStub | None = None

# Microsoft Authenticator / Entra Verified ID Configuration
VERIFIER_BASE_URL = "https://verifier.marty.local"  # Should come from config
VERIFIER_DID = "did:web:verifier.marty.local"  # Should come from config


def _read_tls_file(path: str | None) -> bytes | None:
    if not path:
        return None
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("TLS file not found: %s", path)
        return None


def get_grpc_client() -> inspection_system_pb2_grpc.InspectionSystemStub:
    """Get or create the gRPC client."""
    global channel, inspection_system_stub

    if inspection_system_stub is None:
        if GRPC_TLS_ENABLED:
            credentials = grpc.ssl_channel_credentials(
                root_certificates=_read_tls_file(GRPC_TLS_CA_CERT),
                private_key=_read_tls_file(GRPC_TLS_CLIENT_KEY),
                certificate_chain=_read_tls_file(GRPC_TLS_CLIENT_CERT),
            )
            channel = grpc.secure_channel(GRPC_INSPECTION_SYSTEM_ADDRESS, credentials)
            logger.info("gRPC TLS channel to inspection-system at %s", GRPC_INSPECTION_SYSTEM_ADDRESS)
        else:
            channel = grpc.insecure_channel(GRPC_INSPECTION_SYSTEM_ADDRESS)
        inspection_system_stub = inspection_system_pb2_grpc.InspectionSystemStub(channel)

    return inspection_system_stub


# Pydantic models for OID4VP
class PresentationDefinition(BaseModel):
    """Presentation definition for requesting specific credentials."""

    id: str = Field(..., description="Unique identifier for the presentation definition")
    input_descriptors: list[dict[str, Any]] = Field(
        ..., description="Descriptors for required credentials"
    )
    purpose: str | None = Field(default=None, description="Purpose of the verification")
    format: dict[str, Any] | None = Field(default=None, description="Supported credential formats")


class VerificationRequest(BaseModel):
    """Request to initiate credential verification."""

    presentation_definition: PresentationDefinition = Field(
        ..., description="Defines what credentials are required"
    )
    client_id: str = Field(..., description="Client identifier for the verifier")
    redirect_uri: str | None = Field(default=None, description="URI to redirect after verification")
    state: str | None = Field(default=None, description="State parameter for correlation")
    nonce: str | None = Field(default=None, description="Nonce for replay protection")


class VerifiablePresentationSubmission(BaseModel):
    """Verifiable presentation submission from wallet."""

    vp_token: str = Field(..., description="The verifiable presentation token")
    presentation_submission: dict[str, Any] = Field(
        ..., description="Presentation submission descriptor"
    )
    state: str | None = Field(default=None, description="State parameter for correlation")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/verification-requests")
async def create_verification_request(request: VerificationRequest) -> dict[str, Any]:
    """Create a verification request compatible with Microsoft Authenticator."""
    try:
        request_id = str(uuid.uuid4())

        # Create presentation request compatible with Microsoft Authenticator
        presentation_request = {
            "client_id": request.client_id,
            "client_id_scheme": "did",
            "response_type": "vp_token",
            "response_mode": "direct_post",
            "presentation_definition": request.presentation_definition.dict(),
            "nonce": request.nonce or str(uuid.uuid4()),
            "state": request.state or str(uuid.uuid4()),
            "redirect_uri": request.redirect_uri or f"{VERIFIER_BASE_URL}/verification-response",
        }

        # Create the authorization request URI for Microsoft Authenticator
        auth_params = {
            "client_id": request.client_id,
            "request_uri": f"{VERIFIER_BASE_URL}/verification-requests/{request_id}",
            "response_type": "vp_token",
            "response_mode": "direct_post",
        }
        auth_uri = f"openid4vp://?{urlencode(auth_params)}"

        return {
            "request_id": request_id,
            "authorization_request_uri": auth_uri,
            "presentation_request": presentation_request,
            "expires_in": 300,  # 5 minutes
        }

    except Exception as e:
        logger.exception("Unexpected error creating verification request")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error"
        ) from e


@app.get("/verification-requests/{request_id}")
async def get_verification_request(request_id: str) -> dict[str, Any]:
    """Get a verification request by ID."""
    # In a real implementation, this would retrieve from storage
    # For now, return a sample presentation definition
    return {
        "client_id": VERIFIER_DID,
        "client_id_scheme": "did",
        "response_type": "vp_token",
        "response_mode": "direct_post",
        "presentation_definition": {
            "id": "marty_passport_verification",
            "input_descriptors": [
                {
                    "id": "marty_digital_passport",
                    "name": "Marty Digital Passport",
                    "purpose": "Verify identity using Marty Digital Passport",
                    "format": {"jwt_vc_json": {"alg": ["ES256", "RS256"]}},
                    "constraints": {
                        "fields": [
                            {
                                "path": ["$.type"],
                                "filter": {
                                    "type": "array",
                                    "contains": {"const": "MartyDigitalPassport"},
                                },
                            }
                        ]
                    },
                }
            ],
        },
        "nonce": str(uuid.uuid4()),
        "state": request_id,
        "redirect_uri": f"{VERIFIER_BASE_URL}/verification-response",
    }


@app.post("/verification-response")
async def handle_verification_response(request: Request) -> dict[str, Any]:
    """Handle verification response from Microsoft Authenticator."""
    try:
        # Get form data from Microsoft Authenticator
        form_data = await request.form()
        vp_token = form_data.get("vp_token")
        presentation_submission = form_data.get("presentation_submission")
        state = form_data.get("state")

        if not vp_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Missing vp_token in submission"
            )

        # Parse presentation submission
        if presentation_submission:
            presentation_submission = json.loads(presentation_submission)

        # Verify the presentation using the inspection system
        verification_result = await verify_presentation(vp_token)

        return {
            "verification_id": str(uuid.uuid4()),
            "state": state,
            "status": "verified" if verification_result["valid"] else "failed",
            "verification_result": verification_result,
            "timestamp": verification_result.get("timestamp"),
        }

    except Exception as e:
        logger.exception("Error handling verification response")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Verification failed: {str(e)}"
        ) from e


@app.post("/verify")
async def verify_credential(submission: VerifiablePresentationSubmission) -> dict[str, Any]:
    """Direct verification endpoint for testing and integration."""
    try:
        verification_result = await verify_presentation(submission.vp_token)

        return {
            "verification_id": str(uuid.uuid4()),
            "state": submission.state,
            "status": "verified" if verification_result["valid"] else "failed",
            "verification_result": verification_result,
            "presentation_submission": submission.presentation_submission,
        }

    except Exception as e:
        logger.exception("Error verifying credential")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Verification failed: {str(e)}"
        ) from e


async def verify_presentation(vp_token: str) -> dict[str, Any]:
    """Verify a verifiable presentation using the inspection system."""
    try:
        client = get_grpc_client()

        # Create inspection request
        inspection_request = inspection_system_pb2.InspectRequest(
            document_data=vp_token.encode(), document_type="VERIFIABLE_PRESENTATION"
        )

        # Call inspection system
        response = await client.Inspect(inspection_request)

        # Parse the inspection result
        result_data = {}
        if hasattr(response, "result") and response.result:
            try:
                result_data = json.loads(response.result)
            except json.JSONDecodeError:
                result_data = {"raw_result": response.result}

        # Determine if verification was successful
        is_valid = (
            hasattr(response, "success")
            and response.success
            and result_data.get("signature_valid", False)
            and result_data.get("trust_chain_valid", False)
        )

        return {
            "valid": is_valid,
            "signature_valid": result_data.get("signature_valid", False),
            "trust_chain_valid": result_data.get("trust_chain_valid", False),
            "issuer": result_data.get("issuer", "unknown"),
            "subject": result_data.get("subject", {}),
            "expiry": result_data.get("expiry"),
            "timestamp": result_data.get("timestamp"),
            "details": result_data,
        }

    except grpc.RpcError as e:
        logger.exception("gRPC error during verification")
        return {"valid": False, "error": f"Service error: {e.details()}", "timestamp": None}
    except Exception as e:
        logger.exception("Unexpected error during verification")
        return {"valid": False, "error": f"Verification error: {str(e)}", "timestamp": None}


        return {"valid": False, "error": f"Verification error: {str(e)}", "timestamp": None}


@app.get("/presentation-definition/marty-passport")
async def get_marty_passport_presentation_definition() -> dict[str, Any]:
        "input_descriptors": [
            {
                "id": "marty_digital_passport",
                "name": "Marty Digital Passport",
                "purpose": "Verify identity using Marty Digital Passport",
                "format": {"jwt_vc_json": {"alg": ["ES256", "RS256"]}},
                "constraints": {
                    "fields": [
                        {
                            "path": ["$.type"],
                            "filter": {
                                "type": "array",
                                "contains": {"const": "MartyDigitalPassport"},
                            },
                        },
                        {
                            "path": ["$.credentialSubject.given_name"],
                            "filter": {"type": "string"},
                            "intent_to_retain": False,
                        },
                        {
                            "path": ["$.credentialSubject.family_name"],
                            "filter": {"type": "string"},
                            "intent_to_retain": False,
                        },
                    ]
                },
            }
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
