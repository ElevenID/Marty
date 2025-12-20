"""
Marty Demo UI Application
A minimal FastAPI web interface for demonstrating the Marty platform capabilities.

Features:
- Issue credentials (Passport, MDL, mDoc)
- View logs and traces via Jaeger integration
- Verify presentations
- Monitor system health
- Demo data management
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.protobuf import empty_pb2

from marty_plugin.legacy_apps.ui_app.grpc_clients import GrpcClientFactory
from marty_plugin.legacy_apps.ui_app.config import get_settings
from marty_plugin.proto.v1 import csca_service_pb2, pkd_service_pb2, trust_anchor_pb2

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
settings = get_settings()
grpc_factory = GrpcClientFactory(settings)

ISSUER_API_ADDR = os.getenv("UI_ISSUER_API_ADDR", "http://issuer-api-demo:8000")
PASSPORT_ENGINE_ADDR = os.getenv("UI_PASSPORT_ENGINE_ADDR", "passport-engine-demo:8084")
INSPECTION_SYSTEM_ADDR = os.getenv("UI_INSPECTION_SYSTEM_ADDR", "inspection-system-demo:8083")
MDL_ENGINE_ADDR = os.getenv("UI_MDL_ENGINE_ADDR", "mdl-engine-demo:8085")
MDOC_ENGINE_ADDR = os.getenv("UI_MDOC_ENGINE_ADDR", "mdoc-engine-demo:8086")
TRUST_ANCHOR_ADDR = os.getenv("UI_TRUST_ANCHOR_ADDR", "trust-anchor-demo:8080")
JAEGER_ADDR = os.getenv("UI_JAEGER_ADDR", "http://jaeger-demo:16686")
GRAFANA_ADDR = os.getenv("UI_GRAFANA_ADDR", "http://grafana-demo:3000")

UI_TITLE = os.getenv("UI_TITLE", "Marty Demo Console")
UI_ENVIRONMENT = os.getenv("UI_ENVIRONMENT", "demo")
ENABLE_MOCK_DATA = os.getenv("UI_ENABLE_MOCK_DATA", "true").lower() == "true"

# FastAPI app
app = FastAPI(
    title="Marty Demo UI API",
    description="API for the Marty platform demo UI",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class IssueCredentialRequest(BaseModel):
    credential_type: str
    subject_id: str
    holder_name: str
    birth_date: str
    document_number: Optional[str] = None
    issuing_country: Optional[str] = None
    issuing_state: Optional[str] = None
    license_class: Optional[str] = None

class VerifyPresentationRequest(BaseModel):
    presentation_data: Dict[str, Any]
    verification_policy: str = "standard"

@app.get("/api/config")
async def get_config():
    """Get UI configuration."""
    return {
        "ui_title": UI_TITLE,
        "ui_environment": UI_ENVIRONMENT,
        "jaeger_url": JAEGER_ADDR,
        "grafana_url": GRAFANA_ADDR,
        "demo_mode": ENABLE_MOCK_DATA,
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/status")
async def api_status():
    """API endpoint for system status."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            services = {}

            # Check each service
            service_endpoints = {
                "issuer_api": f"{ISSUER_API_ADDR}/health",
                "jaeger": f"{JAEGER_ADDR}/api/services",
                "grafana": f"{GRAFANA_ADDR}/api/health",
            }

            for service, endpoint in service_endpoints.items():
                try:
                    response = await client.get(endpoint)
                    services[service] = {
                        "status": "healthy" if response.status_code < 400 else "unhealthy",
                        "response_time_ms": response.elapsed.total_seconds() * 1000,
                    }
                except Exception as e:
                    services[service] = {"status": "unavailable", "error": str(e)}

            return {
                "overall_status": (
                    "healthy"
                    if all(s.get("status") == "healthy" for s in services.values())
                    else "degraded"
                ),
                "services": services,
                "timestamp": datetime.now().isoformat(),
            }

    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}

@app.get("/api/issue/options")
async def get_issuance_options():
    """Get options for credential issuance."""
    return {
        "credential_types": [
            {"value": "PassportCredential", "label": "Passport Credential"},
            {"value": "MDLCredential", "label": "Mobile Driver's License"},
            {"value": "mDocCredential", "label": "Mobile Document"},
        ],
        "countries": ["USA", "CAN", "GBR", "AUS", "DEU", "FRA", "JPN"],
        "states": ["California", "Texas", "New York", "Florida", "Nevada", "Illinois"],
    }

@app.post("/api/issue")
async def issue_credential(request: IssueCredentialRequest):
    """Process credential issuance."""
    try:
        # Build credential request based on type
        base_claims = {"holder_name": request.holder_name, "birth_date": request.birth_date}

        if request.credential_type == "PassportCredential":
            base_claims.update(
                {"document_number": request.document_number, "issuing_country": request.issuing_country}
            )
        elif request.credential_type == "MDLCredential":
            base_claims.update(
                {
                    "license_number": request.document_number,
                    "issuing_state": request.issuing_state,
                    "license_class": request.license_class,
                }
            )

        credential_request = {
            "subject_id": request.subject_id,
            "credential_type": request.credential_type,
            "base_claims": base_claims,
            "selective_disclosures": {
                "address": "Demo Address for selective disclosure",
                "phone": "+1-555-DEMO",
            },
        }

        # Call issuer API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ISSUER_API_ADDR}/v1/credentials/offer", json=credential_request
            )

            if response.status_code in [200, 201]:
                credential_data = response.json()
                return {
                    "success": True,
                    "credential_data": credential_data,
                    "credential_id": credential_data.get("credential_id", "N/A"),
                }
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to issue credential: {response.text}"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error issuing credential: {e}")
        raise HTTPException(status_code=500, detail=f"Error issuing credential: {str(e)}")

@app.post("/api/verify")
async def verify_presentation(request: VerifyPresentationRequest):
    """Process presentation verification."""
    try:
        presentation = request.presentation_data
        
        # For demo purposes, simulate verification
        # In a real implementation, this would call the inspection system
        verification_result = {
            "verified": True,
            "verification_time": datetime.now().isoformat(),
            "policy_applied": request.verification_policy,
            "checks": {
                "signature_valid": True,
                "not_expired": True,
                "issuer_trusted": True,
                "revocation_status": "not_revoked",
            },
            "credential_info": {
                "type": presentation.get("type", ["VerifiablePresentation"]),
                "holder": presentation.get("holder", "Unknown"),
                "credentials_count": len(presentation.get("verifiableCredential", [])),
            },
        }

        return {
            "verification_result": verification_result,
            "presentation_summary": presentation,
        }

    except Exception as e:
        logger.error(f"Error verifying presentation: {e}")
        raise HTTPException(status_code=500, detail=f"Error verifying presentation: {str(e)}")

@app.get("/api/demo-data")
async def get_demo_data():
    """Get sample demo data."""
    return {
        "passports": [
            {"document_number": "P123456789", "country": "USA", "holder": "John Doe"},
            {"document_number": "P987654321", "country": "CAN", "holder": "Jane Smith"},
        ],
        "mdls": [
            {"license_number": "DL123456789", "state": "California", "holder": "John Doe"},
            {"license_number": "DL987654321", "state": "Texas", "holder": "Jane Smith"},
        ],
        "credentials_issued": [
            {"id": "cred-001", "type": "PassportCredential", "subject": "demo-user-001"},
            {"id": "cred-002", "type": "MDLCredential", "subject": "demo-user-002"},
        ],
    }

# Admin API Endpoints

@app.get("/api/admin/csca")
async def list_csca_certificates():
    """List CSCA certificates via PKD service."""
    try:
        with grpc_factory.pkd_service() as stub:
            response = stub.ListTrustAnchors(empty_pb2.Empty())
            return {
                "certificates": [
                    {
                        "id": anchor.certificate_id,
                        "subject": anchor.subject,
                        "not_after": anchor.not_after,
                        "revoked": anchor.revoked,
                        "pem": anchor.certificate_pem
                    }
                    for anchor in response.anchors
                ]
            }
    except Exception as e:
        logger.error(f"Error listing CSCA certificates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class CreateCscaRequest(BaseModel):
    subject_name: str
    key_algorithm: str = "RSA"
    key_size: int = 2048
    validity_days: int = 365

@app.post("/api/admin/csca")
async def create_csca_certificate(request: CreateCscaRequest):
    """Create a new CSCA certificate."""
    try:
        with grpc_factory.csca_service() as stub:
            grpc_req = csca_service_pb2.CreateCertificateRequest(
                subject_name=request.subject_name,
                key_algorithm=request.key_algorithm,
                key_size=request.key_size,
                validity_days=request.validity_days
            )
            response = stub.CreateCertificate(grpc_req)
            return {
                "success": True,
                "certificate_id": response.certificate_id,
                "pem": response.pem
            }
    except Exception as e:
        logger.error(f"Error creating CSCA certificate: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/pkd/sync")
async def sync_pkd(force_refresh: bool = False):
    """Trigger PKD synchronization."""
    try:
        with grpc_factory.pkd_service() as stub:
            response = stub.Sync(pkd_service_pb2.SyncRequest(force_refresh=force_refresh))
            return {"success": response.success, "message": response.message}
    except Exception as e:
        logger.error(f"Error syncing PKD: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class VerifyTrustRequest(BaseModel):
    entity_id: str

@app.post("/api/admin/trust-anchor/verify")
async def verify_trust(request: VerifyTrustRequest):
    """Verify trust for an entity."""
    try:
        with grpc_factory.trust_anchor() as stub:
            response = stub.VerifyTrust(trust_anchor_pb2.TrustRequest(entity=request.entity_id))
            return {"is_trusted": response.is_trusted}
    except Exception as e:
        logger.error(f"Error verifying trust: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
