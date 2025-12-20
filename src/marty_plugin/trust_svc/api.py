"""
Trust Services REST API

FastAPI application providing trust status queries, snapshots, and administrative endpoints.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import TrustServiceConfig, config
from .database import DatabaseManager
from .models import (
    CRLRefreshRequest,
    CRLRefreshResponse,
    DevJobRequest,
    DevJobResponse,
    DSCListResponse,
    MasterListUploadRequest,
    MasterListUploadResponse,
    RevocationStatus,
    ServiceStatusResponse,
    SnapshotResponse,
    TrustAnchorListResponse,
    TrustStatusRequest,
    TrustStatusResponse,
)
from .revocation import RevocationProcessor

logger = logging.getLogger(__name__)

# Global service instances
db_manager: DatabaseManager | None = None
revocation_processor: RevocationProcessor | None = None
app_start_time = datetime.now(timezone.utc)


def get_db_manager() -> DatabaseManager:
    """Dependency to get database manager."""
    if not db_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database not initialized"
        )
    return db_manager


def get_revocation_processor() -> RevocationProcessor:
    """Dependency to get revocation processor."""
    if not revocation_processor:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Revocation processor not initialized",
        )
    return revocation_processor


def create_app(config_obj: TrustServiceConfig = config) -> FastAPI:
    """Create FastAPI application with trust services."""

    app = FastAPI(
        title="Trust Services API",
        description="Centralized trust management for Marty passport verification",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup_event():
        """Initialize services on startup."""
        global db_manager, revocation_processor

        try:
            # Initialize database
            db_manager = DatabaseManager(config_obj)
            await db_manager.initialize()

            # Initialize revocation processor
            revocation_processor = RevocationProcessor(
                db_manager, config_obj.pkd.ocsp_timeout_seconds
            )
            await revocation_processor.initialize()

            logger.info("Trust services initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize trust services: {e}")
            raise

    @app.on_event("shutdown")
    async def shutdown_event():
        """Cleanup on shutdown."""
        if revocation_processor:
            await revocation_processor.close()
        if db_manager:
            await db_manager.close()
        logger.info("Trust services shut down")

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        db_healthy = await db_manager.health_check() if db_manager else False

        return {
            "status": "healthy" if db_healthy else "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database": db_healthy,
        }

    # Trust query endpoints
    @app.post("/api/v1/trust/status", response_model=TrustStatusResponse)
    async def get_trust_status(
        request: TrustStatusRequest,
        db: DatabaseManager = Depends(get_db_manager),
        revocation: RevocationProcessor = Depends(get_revocation_processor),
    ):
        """Get comprehensive trust status for a certificate."""
        try:
            # Get certificate from database
            dscs = await db.get_dsc_certificates(certificate_hash=request.certificate_hash)

            if not dscs:
                return TrustStatusResponse(certificate_hash=request.certificate_hash, found=False)

            dsc = dscs[0]

            # Get chain validation info if requested
            trust_path = []
            chain_valid = None
            trust_anchor = None

            if request.include_chain:
                chain_result = await db.validate_certificate_chain(request.certificate_hash)
                chain_valid = chain_result["valid"]
                if chain_result["trust_anchor_id"]:
                    trust_anchor = chain_result["trust_anchor_id"]
                    trust_path = [request.certificate_hash, trust_anchor]

            # Check current revocation status
            if dsc["revocation_status"] == RevocationStatus.UNKNOWN.value:
                # Trigger revocation check
                revocation_result = await revocation.check_certificate_revocation_status(
                    request.certificate_hash
                )
                if revocation_result["found"]:
                    dsc["revocation_status"] = revocation_result["current_status"]

            return TrustStatusResponse(
                certificate_hash=request.certificate_hash,
                found=True,
                trust_status=RevocationStatus(dsc["revocation_status"]),
                trust_anchor=trust_anchor,
                chain_valid=chain_valid,
                revocation_checked_at=dsc["revocation_checked_at"],
                expires_at=dsc["valid_to"],
                trust_path=trust_path,
                metadata={
                    "country_code": dsc["country_code"],
                    "serial_number": dsc["serial_number"],
                    "issuer_dn": dsc["issuer_dn"],
                    "algorithm": dsc["signature_algorithm"],
                },
            )

        except Exception as e:
            logger.error(f"Trust status check failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Trust status check failed",
            )

    @app.get("/api/v1/trust/anchors/{country_code}", response_model=TrustAnchorListResponse)
    async def get_trust_anchors(country_code: str, db: DatabaseManager = Depends(get_db_manager)):
        """Get trust anchors for a specific country."""
        try:
            trust_anchors_data = await db.get_trust_anchors(
                country_code=country_code.upper(), active_only=True
            )

            # Convert to response models
            from .models import TrustAnchor

            trust_anchors = [TrustAnchor(**ta) for ta in trust_anchors_data]

            total_count = len(trust_anchors)
            valid_count = sum(1 for ta in trust_anchors if ta.valid_to > datetime.now(timezone.utc))
            expired_count = total_count - valid_count

            return TrustAnchorListResponse(
                country_code=country_code.upper(),
                trust_anchors=trust_anchors,
                total_count=total_count,
                valid_count=valid_count,
                expired_count=expired_count,
            )

        except Exception as e:
            logger.error(f"Trust anchors query failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Trust anchors query failed",
            )

    @app.get("/api/v1/trust/dsc/{country_code}", response_model=DSCListResponse)
    async def get_dsc_certificates(
        country_code: str,
        status_filter: str | None = None,
        db: DatabaseManager = Depends(get_db_manager),
    ):
        """Get DSC certificates for a specific country."""
        try:
            revocation_status = None
            if status_filter:
                try:
                    revocation_status = RevocationStatus(status_filter)
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid status filter: {status_filter}",
                    )

            dscs_data = await db.get_dsc_certificates(
                country_code=country_code.upper(), revocation_status=revocation_status
            )

            # Convert to response models
            from .models import DSCCertificate

            certificates = [DSCCertificate(**dsc) for dsc in dscs_data]

            # Calculate status counts
            status_counts = {}
            for cert in certificates:
                status = cert.revocation_status.value
                status_counts[status] = status_counts.get(status, 0) + 1

            return DSCListResponse(
                country_code=country_code.upper(),
                certificates=certificates,
                total_count=len(certificates),
                status_counts=status_counts,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"DSC certificates query failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="DSC certificates query failed",
            )

    @app.get("/api/v1/trust/snapshot/latest", response_model=SnapshotResponse)
    async def get_latest_snapshot(db: DatabaseManager = Depends(get_db_manager)):
        """Get the latest trust snapshot."""
        try:
            snapshot_data = await db.get_latest_snapshot()

            if not snapshot_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="No trust snapshots available"
                )

            from .models import TrustSnapshot

            snapshot = TrustSnapshot(**snapshot_data)

            # Calculate age
            age_seconds = int((datetime.now(timezone.utc) - snapshot.snapshot_time).total_seconds())

            # TODO: Verify signature
            signature_valid = snapshot.signature is not None

            return SnapshotResponse(
                snapshot=snapshot, signature_valid=signature_valid, age_seconds=age_seconds
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Snapshot query failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Snapshot query failed"
            )

    # Administrative endpoints
    @app.post("/api/v1/admin/masterlist/upload", response_model=MasterListUploadResponse)
    async def upload_master_list(
        request: MasterListUploadRequest, db: DatabaseManager = Depends(get_db_manager)
    ):
        """Upload and process a master list."""
        try:
            # TODO: Implement master list parsing using existing PKD service logic
            # For now, return a mock response

            return MasterListUploadResponse(
                success=True,
                message=f"Master list uploaded for {request.country_code}",
                certificates_processed=0,
                trust_anchors_added=0,
                dscs_added=0,
                errors=[],
            )

        except Exception as e:
            logger.error(f"Master list upload failed: {e}")
            return MasterListUploadResponse(
                success=False,
                message="Master list upload failed",
                certificates_processed=0,
                trust_anchors_added=0,
                dscs_added=0,
                errors=[str(e)],
            )

    @app.post("/api/v1/admin/crl/refresh", response_model=CRLRefreshResponse)
    async def refresh_crls(
        request: CRLRefreshRequest = CRLRefreshRequest(),
        revocation: RevocationProcessor = Depends(get_revocation_processor),
    ):
        """Refresh CRLs from known sources."""
        try:
            result = await revocation.refresh_all_crls(request.force_refresh)

            return CRLRefreshResponse(
                success=result["success"],
                message=f"CRL refresh completed: {result['crls_processed']} processed",
                crls_processed=result["crls_processed"],
                revoked_certificates_found=result["total_revoked"],
                errors=result["errors"],
            )

        except Exception as e:
            logger.error(f"CRL refresh failed: {e}")
            return CRLRefreshResponse(
                success=False,
                message="CRL refresh failed",
                crls_processed=0,
                revoked_certificates_found=0,
                errors=[str(e)],
            )

    @app.post("/api/v1/admin/snapshot/create")
    async def create_trust_snapshot(db: DatabaseManager = Depends(get_db_manager)):
        """Create a new trust snapshot."""
        try:
            # Generate snapshot hash
            timestamp = datetime.now(timezone.utc)
            snapshot_content = f"TRUST_SNAPSHOT_{timestamp.isoformat()}"
            snapshot_hash = hashlib.sha256(snapshot_content.encode()).hexdigest()

            # TODO: Generate KMS signature
            signature = f"MOCK_KMS_SIGNATURE_{int(timestamp.timestamp())}"

            # Create snapshot
            snapshot_id = await db.create_trust_snapshot(
                snapshot_hash=snapshot_hash,
                signature=signature,
                metadata={"created_by": "api_request", "timestamp": timestamp.isoformat()},
            )

            return {
                "success": True,
                "snapshot_id": snapshot_id,
                "snapshot_hash": snapshot_hash,
                "created_at": timestamp.isoformat(),
            }

        except Exception as e:
            logger.error(f"Snapshot creation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Snapshot creation failed"
            )

    @app.get("/api/v1/admin/status", response_model=ServiceStatusResponse)
    async def get_service_status(db: DatabaseManager = Depends(get_db_manager)):
        """Get comprehensive service status."""
        try:
            # Get uptime
            uptime_seconds = int((datetime.now(timezone.utc) - app_start_time).total_seconds())

            # Check subsystems
            db_connected = await db.health_check()

            # Get latest snapshot age
            latest_snapshot = await db.get_latest_snapshot()
            last_snapshot_age = None
            if latest_snapshot:
                last_snapshot_age = int(
                    (datetime.now(timezone.utc) - latest_snapshot["snapshot_time"]).total_seconds()
                )

            # Get certificate counts
            trust_anchors = await db.get_trust_anchors()
            dscs = await db.get_dsc_certificates()

            certificate_counts = {
                "trust_anchors": len(trust_anchors),
                "dsc_certificates": len(dscs),
                "active_trust_anchors": len(
                    [ta for ta in trust_anchors if ta["status"] == "active"]
                ),
                "good_dscs": len([dsc for dsc in dscs if dsc["revocation_status"] == "good"]),
                "bad_dscs": len([dsc for dsc in dscs if dsc["revocation_status"] == "bad"]),
                "unknown_dscs": len([dsc for dsc in dscs if dsc["revocation_status"] == "unknown"]),
            }

            # TODO: Get recent job executions
            recent_jobs = []

            return ServiceStatusResponse(
                status="healthy" if db_connected else "unhealthy",
                version="1.0.0",
                uptime_seconds=uptime_seconds,
                database_connected=db_connected,
                kms_available=True,  # TODO: Check KMS connectivity
                job_scheduler_running=True,  # TODO: Check scheduler status
                last_snapshot_age_seconds=last_snapshot_age,
                certificate_counts=certificate_counts,
                recent_jobs=recent_jobs,
            )

        except Exception as e:
            logger.error(f"Status check failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Status check failed"
            )

    # Development endpoints
    @app.post("/api/v1/dev/load-synthetic", response_model=DevJobResponse)
    async def load_synthetic_data(
        request: DevJobRequest = DevJobRequest(), db: DatabaseManager = Depends(get_db_manager)
    ):
        """Load synthetic master list data for development."""
        try:
            job_id = await db.start_job(
                job_name="dev_load_synthetic", job_type="load_synthetic", metadata=request.dict()
            )

            start_time = datetime.now(timezone.utc)

            # TODO: Implement synthetic data loading
            # For now, return mock statistics

            statistics = {
                "master_list": {
                    "country": request.country_code,
                    "certificates": request.certificate_count,
                    "valid_certificates": request.certificate_count - 2,
                    "expired_certificates": 2,
                },
                "trust_anchors": {"loaded": 1, "skipped": 0},
                "dsc_certificates": {
                    "loaded": request.certificate_count - 1,
                    "revocation_status": {
                        "good": int((request.certificate_count - 1) * 0.8),
                        "bad": int((request.certificate_count - 1) * 0.1),
                        "unknown": int((request.certificate_count - 1) * 0.1),
                    },
                },
            }

            # Complete job
            await db.complete_job(
                job_id=job_id,
                status="completed",
                records_processed=request.certificate_count,
                metadata={"statistics": statistics},
            )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            return DevJobResponse(
                success=True,
                job_id=job_id,
                message=f"Synthetic data loaded for {request.country_code}",
                statistics=statistics,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.error(f"Synthetic data loading failed: {e}")
            return DevJobResponse(
                success=False,
                job_id="",
                message="Synthetic data loading failed",
                statistics={},
                duration_seconds=0,
            )

    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host=config.service.host,
        port=config.service.port,
        log_level=config.service.log_level.lower(),
        reload=True,
    )
