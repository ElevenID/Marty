"""
Applicant Service API - FastAPI Router

REST API endpoints for applicant vetting and application management.
Production-grade endpoints with full audit logging, validation, and compliance.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, EmailStr

from .database import init_database, get_db_manager
from .models import (
    ApplicationStatus,
    VettingCheckType,
    VettingCheckStatus,
    BiometricType,
    KYCFieldType,
)
from .service import (
    ApplicantService,
    ApplicationService,
    VettingService,
    ApprovalService,
    KYCService,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/applicants", tags=["Applicants"])

# Global service instances
_applicant_service: ApplicantService | None = None
_application_service: ApplicationService | None = None
_vetting_service: VettingService | None = None
_approval_service: ApprovalService | None = None
_kyc_service: KYCService | None = None


def get_applicant_service() -> ApplicantService:
    """Get or create the applicant service instance."""
    global _applicant_service
    if _applicant_service is None:
        _applicant_service = ApplicantService()
    return _applicant_service


def get_application_service() -> ApplicationService:
    """Get or create the application service instance."""
    global _application_service
    if _application_service is None:
        _application_service = ApplicationService()
    return _application_service


def get_vetting_service() -> VettingService:
    """Get or create the vetting service instance."""
    global _vetting_service
    if _vetting_service is None:
        _vetting_service = VettingService()
    return _vetting_service


def get_approval_service() -> ApprovalService:
    """Get or create the approval service instance."""
    global _approval_service
    if _approval_service is None:
        _approval_service = ApprovalService()
    return _approval_service


def get_kyc_service() -> KYCService:
    """Get or create the KYC service instance."""
    global _kyc_service
    if _kyc_service is None:
        _kyc_service = KYCService()
    return _kyc_service


@router.on_event("startup")
async def startup_event() -> None:
    """Initialize applicant database on API startup."""
    await init_database()
    logger.info("Applicant service initialized")


# ==================== Pydantic Models for API ====================

class AddressModel(BaseModel):
    """Address structure for API."""
    street_line1: str
    street_line2: str | None = None
    city: str
    state_province: str | None = None
    postal_code: str
    country: str = Field(..., min_length=3, max_length=3, description="ISO 3166-1 alpha-3")


class CreateApplicantRequest(BaseModel):
    """Request to create a new applicant."""
    user_id: str = Field(..., description="User account ID from auth system")
    given_name: str = Field(..., min_length=1, max_length=100)
    family_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    date_of_birth: datetime
    nationality: str = Field(..., min_length=3, max_length=3, description="ISO 3166-1 alpha-3")
    phone_number: str | None = None
    address: AddressModel | None = None


class UpdateApplicantRequest(BaseModel):
    """Request to update an applicant."""
    given_name: str | None = None
    family_name: str | None = None
    phone_number: str | None = None
    address: AddressModel | None = None


class ApplicantResponse(BaseModel):
    """Response containing an applicant."""
    id: UUID
    user_id: str
    given_name: str
    family_name: str
    full_name: str
    email: str
    phone_number: str | None
    date_of_birth: datetime
    nationality: str
    address: dict[str, Any]
    is_active: bool
    is_email_verified: bool
    is_phone_verified: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BiometricEnrollRequest(BaseModel):
    """Request to enroll a biometric."""
    biometric_type: BiometricType
    template_data_base64: str = Field(..., description="Base64 encoded ISO 19794 template")
    image_data_base64: str | None = Field(None, description="Base64 encoded image data")
    capture_quality_score: float | None = Field(None, ge=0, le=1)
    capture_device_id: str | None = None
    is_live_capture: bool = True
    metadata: dict[str, Any] | None = None


class BiometricEnrollmentResponse(BaseModel):
    """Response containing a biometric enrollment."""
    id: UUID
    applicant_id: UUID
    biometric_type: BiometricType
    template_format: str
    capture_quality_score: float | None
    capture_device_id: str | None
    is_live_capture: bool
    captured_at: datetime
    is_verified: bool
    verification_score: float | None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CreateApplicationRequest(BaseModel):
    """Request to create a new application."""
    applicant_id: UUID
    document_type: str = Field(..., description="Type of document: PASSPORT, VISA, TRAVEL_PERMIT, etc.")
    issuing_authority: str
    requested_validity_years: int = Field(10, ge=1, le=20)
    travel_purpose: str | None = Field(None, description="Purpose of travel (for visas)")
    destination_countries: list[str] | None = Field(None, description="Destination countries (ISO alpha-3)")
    is_expedited: bool = False
    metadata: dict[str, Any] | None = None


class ApplicationResponse(BaseModel):
    """Response containing an application."""
    id: UUID
    reference_number: str
    applicant_id: UUID
    document_type: str
    status: ApplicationStatus
    issuing_authority: str
    requested_validity_years: int
    travel_purpose: str | None
    destination_countries: list[str]
    is_expedited: bool
    submitted_at: datetime | None
    approved_at: datetime | None
    approved_by: str | None
    issued_at: datetime | None
    issued_document_id: str | None
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ApplicationListResponse(BaseModel):
    """Response containing list of applications."""
    applications: list[ApplicationResponse]
    total: int
    limit: int
    offset: int


class VettingCheckResponse(BaseModel):
    """Response containing a vetting check."""
    id: UUID
    application_id: UUID
    check_type: VettingCheckType
    status: VettingCheckStatus
    is_required: bool
    order: int
    result: dict[str, Any] | None
    notes: str | None
    started_at: datetime | None
    completed_at: datetime | None
    performed_by: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class CompleteCheckRequest(BaseModel):
    """Request to complete a vetting check."""
    passed: bool
    result: dict[str, Any] | None = None
    notes: str | None = None
    performed_by: str | None = None


class ApproveApplicationRequest(BaseModel):
    """Request to approve an application."""
    approved_by: str
    notes: str | None = None


class RejectApplicationRequest(BaseModel):
    """Request to reject an application."""
    rejected_by: str
    reason: str


class KYCSubmissionRequest(BaseModel):
    """Request to submit KYC information."""
    field_type: KYCFieldType
    field_value: str
    document_data_base64: str | None = Field(None, description="Base64 encoded document image")
    document_type: str | None = None
    document_number: str | None = None
    issuing_country: str | None = Field(None, min_length=3, max_length=3)
    issue_date: datetime | None = None
    expiry_date: datetime | None = None
    metadata: dict[str, Any] | None = None


class KYCSubmissionResponse(BaseModel):
    """Response containing a KYC submission."""
    id: UUID
    application_id: UUID
    field_type: KYCFieldType
    field_value: str
    document_type: str | None
    document_number: str | None
    issuing_country: str | None
    issue_date: datetime | None
    expiry_date: datetime | None
    is_verified: bool
    verified_by: str | None
    verified_at: datetime | None
    submitted_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class ApplicationDetailResponse(BaseModel):
    """Detailed application response with all related data."""
    application: ApplicationResponse
    applicant: ApplicantResponse | None
    vetting_checks: list[VettingCheckResponse]
    kyc_submissions: list[KYCSubmissionResponse]


class ApprovedApplicantResponse(BaseModel):
    """Response for approved applicants ready for document issuance."""
    application_id: UUID
    reference_number: str
    applicant_id: UUID
    applicant_name: str
    document_type: str
    approved_at: datetime
    approved_by: str | None


# ==================== Helper Functions ====================

def get_client_info(request: Request) -> tuple[str | None, str | None]:
    """Extract client info from request for audit."""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip_address, user_agent


def get_actor_id(request: Request) -> str:
    """Extract actor ID from request headers or return default."""
    # In production, this would come from JWT token or session
    return request.headers.get("X-Actor-ID", "api_user")


# ==================== Applicant Endpoints ====================

@router.post("", response_model=ApplicantResponse, status_code=201)
async def create_applicant(
    req: CreateApplicantRequest,
    request: Request,
) -> ApplicantResponse:
    """
    Create a new applicant record.
    
    This is the first step in the applicant vetting process.
    After creation, the applicant should enroll their facial biometric.
    
    Args:
        req: Applicant creation request
        
    Returns:
        Created applicant record
        
    Raises:
        400: Applicant already exists
    """
    service = get_applicant_service()
    ip_address, _ = get_client_info(request)
    actor_id = get_actor_id(request)

    try:
        applicant = await service.create_applicant(
            user_id=req.user_id,
            given_name=req.given_name,
            family_name=req.family_name,
            email=req.email,
            date_of_birth=req.date_of_birth,
            nationality=req.nationality,
            phone_number=req.phone_number,
            address=req.address.model_dump() if req.address else None,
            actor_id=actor_id,
            ip_address=ip_address,
        )
        return ApplicantResponse.model_validate(applicant)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{applicant_id}", response_model=ApplicantResponse)
async def get_applicant(applicant_id: UUID) -> ApplicantResponse:
    """
    Get an applicant by ID.
    
    Args:
        applicant_id: UUID of the applicant
        
    Returns:
        Applicant record
        
    Raises:
        404: Applicant not found
    """
    service = get_applicant_service()
    applicant = await service.get_applicant(applicant_id)
    
    if not applicant:
        raise HTTPException(status_code=404, detail=f"Applicant {applicant_id} not found")
    
    return ApplicantResponse.model_validate(applicant)


@router.get("/by-user/{user_id}", response_model=ApplicantResponse)
async def get_applicant_by_user(user_id: str) -> ApplicantResponse:
    """
    Get an applicant by user account ID.
    
    Args:
        user_id: User account ID
        
    Returns:
        Applicant record
        
    Raises:
        404: Applicant not found
    """
    service = get_applicant_service()
    applicant = await service.get_applicant_by_user(user_id)
    
    if not applicant:
        raise HTTPException(status_code=404, detail=f"No applicant found for user {user_id}")
    
    return ApplicantResponse.model_validate(applicant)


@router.patch("/{applicant_id}", response_model=ApplicantResponse)
async def update_applicant(
    applicant_id: UUID,
    req: UpdateApplicantRequest,
    request: Request,
) -> ApplicantResponse:
    """
    Update an applicant's profile.
    
    Args:
        applicant_id: UUID of the applicant
        req: Update request
        
    Returns:
        Updated applicant record
        
    Raises:
        404: Applicant not found
    """
    service = get_applicant_service()
    actor_id = get_actor_id(request)

    updates = {}
    if req.given_name:
        updates["given_name"] = req.given_name
    if req.family_name:
        updates["family_name"] = req.family_name
    if req.phone_number:
        updates["phone_number"] = req.phone_number
    if req.address:
        updates["address"] = req.address.model_dump()

    if updates:
        if "given_name" in updates or "family_name" in updates:
            # Update full_name too
            applicant = await service.get_applicant(applicant_id)
            if applicant:
                given = updates.get("given_name", applicant.given_name)
                family = updates.get("family_name", applicant.family_name)
                updates["full_name"] = f"{given} {family}"

    applicant = await service.update_applicant(applicant_id, updates, actor_id)
    
    if not applicant:
        raise HTTPException(status_code=404, detail=f"Applicant {applicant_id} not found")
    
    return ApplicantResponse.model_validate(applicant)


# ==================== Biometric Endpoints ====================

@router.post("/{applicant_id}/biometrics", response_model=BiometricEnrollmentResponse, status_code=201)
async def enroll_biometric(
    applicant_id: UUID,
    req: BiometricEnrollRequest,
    request: Request,
) -> BiometricEnrollmentResponse:
    """
    Enroll a biometric for an applicant.
    
    For account creation, facial biometric should be captured live.
    Additional biometrics (fingerprint, iris) are captured during application.
    
    Args:
        applicant_id: UUID of the applicant
        req: Biometric enrollment request
        
    Returns:
        Created biometric enrollment record
        
    Raises:
        404: Applicant not found
    """
    service = get_applicant_service()
    
    # Verify applicant exists
    applicant = await service.get_applicant(applicant_id)
    if not applicant:
        raise HTTPException(status_code=404, detail=f"Applicant {applicant_id} not found")

    # Decode base64 data
    try:
        template_data = base64.b64decode(req.template_data_base64)
        image_data = base64.b64decode(req.image_data_base64) if req.image_data_base64 else None
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 encoding: {e}")

    enrollment = await service.enroll_biometric(
        applicant_id=applicant_id,
        biometric_type=req.biometric_type,
        template_data=template_data,
        image_data=image_data,
        capture_quality_score=req.capture_quality_score,
        capture_device_id=req.capture_device_id,
        is_live_capture=req.is_live_capture,
        metadata=req.metadata,
    )

    return BiometricEnrollmentResponse.model_validate(enrollment)


@router.get("/{applicant_id}/biometrics", response_model=list[BiometricEnrollmentResponse])
async def get_applicant_biometrics(
    applicant_id: UUID,
    biometric_type: BiometricType | None = Query(None),
) -> list[BiometricEnrollmentResponse]:
    """
    Get biometric enrollments for an applicant.
    
    Args:
        applicant_id: UUID of the applicant
        biometric_type: Optional filter by type
        
    Returns:
        List of active biometric enrollments
    """
    service = get_applicant_service()
    enrollments = await service.get_applicant_biometrics(applicant_id, biometric_type)
    return [BiometricEnrollmentResponse.model_validate(e) for e in enrollments]


# ==================== Application Endpoints ====================

@router.post("/applications", response_model=ApplicationResponse, status_code=201)
async def create_application(
    req: CreateApplicationRequest,
    request: Request,
) -> ApplicationResponse:
    """
    Create a new travel document application.
    
    The application starts in DRAFT status. Use submit endpoint to begin vetting.
    
    Args:
        req: Application creation request
        
    Returns:
        Created application in DRAFT status
        
    Raises:
        400: Invalid request or applicant not found
    """
    service = get_application_service()
    ip_address, _ = get_client_info(request)
    actor_id = get_actor_id(request)

    try:
        application = await service.create_application(
            applicant_id=req.applicant_id,
            document_type=req.document_type,
            issuing_authority=req.issuing_authority,
            requested_validity_years=req.requested_validity_years,
            travel_purpose=req.travel_purpose,
            destination_countries=req.destination_countries,
            expedited=req.is_expedited,
            metadata=req.metadata,
            actor_id=actor_id,
            ip_address=ip_address,
        )
        return ApplicationResponse.model_validate(application)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/applications/{application_id}/submit", response_model=ApplicationResponse)
async def submit_application(
    application_id: UUID,
    request: Request,
) -> ApplicationResponse:
    """
    Submit an application for vetting.
    
    Transitions from DRAFT to SUBMITTED and creates vetting checks.
    
    Args:
        application_id: UUID of the application
        
    Returns:
        Updated application in SUBMITTED status
        
    Raises:
        400: Invalid state transition
        404: Application not found
    """
    service = get_application_service()
    ip_address, _ = get_client_info(request)
    actor_id = get_actor_id(request)

    try:
        application = await service.submit_application(
            application_id=application_id,
            actor_id=actor_id,
            ip_address=ip_address,
        )
        return ApplicationResponse.model_validate(application)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/applications/{application_id}", response_model=ApplicationDetailResponse)
async def get_application(application_id: UUID) -> ApplicationDetailResponse:
    """
    Get detailed application information.
    
    Includes applicant, vetting checks, and KYC submissions.
    
    Args:
        application_id: UUID of the application
        
    Returns:
        Detailed application information
        
    Raises:
        404: Application not found
    """
    service = get_application_service()
    details = await service.get_application_with_details(application_id)
    
    if not details:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")
    
    return ApplicationDetailResponse(
        application=ApplicationResponse.model_validate(details["application"]),
        applicant=ApplicantResponse.model_validate(details["applicant"]) if details["applicant"] else None,
        vetting_checks=[VettingCheckResponse.model_validate(c) for c in details["vetting_checks"]],
        kyc_submissions=[KYCSubmissionResponse.model_validate(s) for s in details["kyc_submissions"]],
    )


@router.get("/applications/by-reference/{reference_number}", response_model=ApplicationResponse)
async def get_application_by_reference(reference_number: str) -> ApplicationResponse:
    """
    Get application by reference number.
    
    Args:
        reference_number: Application reference number (e.g., APP-20250101-ABC123)
        
    Returns:
        Application record
        
    Raises:
        404: Application not found
    """
    service = get_application_service()
    application = await service.get_application_by_reference(reference_number)
    
    if not application:
        raise HTTPException(status_code=404, detail=f"Application {reference_number} not found")
    
    return ApplicationResponse.model_validate(application)


@router.get("/applications", response_model=ApplicationListResponse)
async def list_applications(
    status: ApplicationStatus | None = Query(None, description="Filter by status"),
    document_type: str | None = Query(None, description="Filter by document type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ApplicationListResponse:
    """
    List applications with optional filters.
    
    Args:
        status: Filter by application status
        document_type: Filter by document type
        limit: Maximum results
        offset: Pagination offset
        
    Returns:
        List of applications with pagination info
    """
    service = get_application_service()
    applications, total = await service.list_applications(
        status=status,
        document_type=document_type,
        limit=limit,
        offset=offset,
    )
    
    return ApplicationListResponse(
        applications=[ApplicationResponse.model_validate(a) for a in applications],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{applicant_id}/applications", response_model=list[ApplicationResponse])
async def get_applicant_applications(
    applicant_id: UUID,
    status: ApplicationStatus | None = Query(None),
) -> list[ApplicationResponse]:
    """
    Get all applications for an applicant.
    
    Args:
        applicant_id: UUID of the applicant
        status: Optional status filter
        
    Returns:
        List of applications for the applicant
    """
    service = get_application_service()
    applications = await service.get_applicant_applications(applicant_id, status)
    return [ApplicationResponse.model_validate(a) for a in applications]


# ==================== Vetting Check Endpoints ====================

@router.get("/applications/{application_id}/checks", response_model=list[VettingCheckResponse])
async def get_vetting_checks(application_id: UUID) -> list[VettingCheckResponse]:
    """
    Get all vetting checks for an application.
    
    Args:
        application_id: UUID of the application
        
    Returns:
        List of vetting checks in order
    """
    service = get_application_service()
    checks = await service.get_vetting_checks(application_id)
    return [VettingCheckResponse.model_validate(c) for c in checks]


@router.post("/checks/{check_id}/start", response_model=VettingCheckResponse)
async def start_vetting_check(
    check_id: UUID,
    request: Request,
) -> VettingCheckResponse:
    """
    Start a vetting check.
    
    Args:
        check_id: UUID of the check
        
    Returns:
        Updated check in IN_PROGRESS status
    """
    service = get_vetting_service()
    actor_id = get_actor_id(request)
    
    check = await service.start_check(check_id, actor_id)
    if not check:
        raise HTTPException(status_code=404, detail=f"Check {check_id} not found")
    
    return VettingCheckResponse.model_validate(check)


@router.post("/checks/{check_id}/complete", response_model=VettingCheckResponse)
async def complete_vetting_check(
    check_id: UUID,
    req: CompleteCheckRequest,
) -> VettingCheckResponse:
    """
    Complete a vetting check with result.
    
    Args:
        check_id: UUID of the check
        req: Completion request with pass/fail and details
        
    Returns:
        Updated check with result
    """
    service = get_vetting_service()
    
    check = await service.complete_check(
        check_id=check_id,
        passed=req.passed,
        result=req.result,
        notes=req.notes,
        performed_by=req.performed_by,
    )
    
    if not check:
        raise HTTPException(status_code=404, detail=f"Check {check_id} not found")
    
    return VettingCheckResponse.model_validate(check)


@router.post("/checks/{check_id}/manual-review", response_model=VettingCheckResponse)
async def request_manual_review(
    check_id: UUID,
    reason: str = Query(..., description="Reason for manual review"),
    request: Request = None,
) -> VettingCheckResponse:
    """
    Flag a check for manual review.
    
    Args:
        check_id: UUID of the check
        reason: Reason for manual review
        
    Returns:
        Updated check in REQUIRES_MANUAL_REVIEW status
    """
    service = get_vetting_service()
    actor_id = get_actor_id(request) if request else "system"
    
    check = await service.request_manual_review(check_id, reason, actor_id)
    if not check:
        raise HTTPException(status_code=404, detail=f"Check {check_id} not found")
    
    return VettingCheckResponse.model_validate(check)


@router.get("/checks/pending", response_model=list[VettingCheckResponse])
async def get_pending_checks(
    check_type: VettingCheckType | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[VettingCheckResponse]:
    """
    Get pending vetting checks for processing.
    
    Args:
        check_type: Filter by check type
        limit: Maximum results
        
    Returns:
        List of pending checks
    """
    service = get_vetting_service()
    checks = await service.get_pending_checks(check_type, limit)
    return [VettingCheckResponse.model_validate(c) for c in checks]


# ==================== KYC Endpoints ====================

@router.post("/applications/{application_id}/kyc", response_model=KYCSubmissionResponse, status_code=201)
async def submit_kyc(
    application_id: UUID,
    req: KYCSubmissionRequest,
    request: Request,
) -> KYCSubmissionResponse:
    """
    Submit KYC information for an application.
    
    Args:
        application_id: UUID of the application
        req: KYC submission request
        
    Returns:
        Created KYC submission
    """
    service = get_kyc_service()
    
    # Decode document data if provided
    document_data = None
    if req.document_data_base64:
        try:
            document_data = base64.b64decode(req.document_data_base64)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64 encoding: {e}")

    submission = await service.submit_kyc_document(
        application_id=application_id,
        field_type=req.field_type,
        field_value=req.field_value,
        document_data=document_data,
        document_type=req.document_type,
        document_number=req.document_number,
        issuing_country=req.issuing_country,
        issue_date=req.issue_date,
        expiry_date=req.expiry_date,
        metadata=req.metadata,
    )

    return KYCSubmissionResponse.model_validate(submission)


@router.get("/applications/{application_id}/kyc", response_model=list[KYCSubmissionResponse])
async def get_kyc_submissions(application_id: UUID) -> list[KYCSubmissionResponse]:
    """
    Get all KYC submissions for an application.
    
    Args:
        application_id: UUID of the application
        
    Returns:
        List of KYC submissions
    """
    service = get_kyc_service()
    submissions = await service.get_kyc_submissions(application_id)
    return [KYCSubmissionResponse.model_validate(s) for s in submissions]


@router.post("/kyc/{submission_id}/verify", response_model=KYCSubmissionResponse)
async def verify_kyc_submission(
    submission_id: UUID,
    verified: bool = Query(...),
    verified_by: str = Query(...),
    notes: str | None = Query(None),
) -> KYCSubmissionResponse:
    """
    Verify or reject a KYC submission.
    
    Args:
        submission_id: UUID of the KYC submission
        verified: Whether the submission is verified
        verified_by: ID of verifying user
        notes: Optional verification notes
        
    Returns:
        Updated KYC submission
    """
    service = get_kyc_service()
    
    submission = await service.verify_kyc_submission(
        submission_id=submission_id,
        verified=verified,
        verified_by=verified_by,
        notes=notes,
    )
    
    if not submission:
        raise HTTPException(status_code=404, detail=f"KYC submission {submission_id} not found")
    
    return KYCSubmissionResponse.model_validate(submission)


# ==================== Approval Endpoints ====================

@router.post("/applications/{application_id}/approve", response_model=ApplicationResponse)
async def approve_application(
    application_id: UUID,
    req: ApproveApplicationRequest,
    request: Request,
) -> ApplicationResponse:
    """
    Approve an application for document issuance.
    
    Requires all mandatory vetting checks to have passed.
    
    Args:
        application_id: UUID of the application
        req: Approval request
        
    Returns:
        Updated application in APPROVED status
        
    Raises:
        400: Cannot approve (checks not passed or invalid state)
    """
    service = get_approval_service()
    ip_address, _ = get_client_info(request)

    try:
        application = await service.approve_application(
            application_id=application_id,
            approved_by=req.approved_by,
            notes=req.notes,
            ip_address=ip_address,
        )
        return ApplicationResponse.model_validate(application)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/applications/{application_id}/reject", response_model=ApplicationResponse)
async def reject_application(
    application_id: UUID,
    req: RejectApplicationRequest,
    request: Request,
) -> ApplicationResponse:
    """
    Reject an application.
    
    Args:
        application_id: UUID of the application
        req: Rejection request
        
    Returns:
        Updated application in REJECTED status
        
    Raises:
        400: Invalid state transition
    """
    service = get_approval_service()
    ip_address, _ = get_client_info(request)

    try:
        application = await service.reject_application(
            application_id=application_id,
            rejected_by=req.rejected_by,
            reason=req.reason,
            ip_address=ip_address,
        )
        return ApplicationResponse.model_validate(application)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/applications/{application_id}/mark-issued", response_model=ApplicationResponse)
async def mark_application_issued(
    application_id: UUID,
    document_id: str = Query(..., description="ID of the issued document"),
    request: Request = None,
) -> ApplicationResponse:
    """
    Mark an application as issued after document creation.
    
    Called by document service after successful issuance.
    
    Args:
        application_id: UUID of the application
        document_id: ID of the issued document
        
    Returns:
        Updated application in ISSUED status
        
    Raises:
        400: Application not approved
    """
    service = get_approval_service()
    actor_id = get_actor_id(request) if request else "system"

    try:
        application = await service.mark_issued(
            application_id=application_id,
            document_id=document_id,
            issued_by=actor_id,
        )
        return ApplicationResponse.model_validate(application)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/applications/approved", response_model=list[ApprovedApplicantResponse])
async def get_approved_applications(
    limit: int = Query(50, ge=1, le=200),
) -> list[ApprovedApplicantResponse]:
    """
    Get approved applications ready for document issuance.
    
    These applications have passed all vetting and are ready
    to have travel documents issued.
    
    Args:
        limit: Maximum results
        
    Returns:
        List of approved applications with applicant info
    """
    approval_service = get_approval_service()
    applicant_service = get_applicant_service()
    
    applications = await approval_service.get_approved_applications(limit)
    
    result = []
    for app in applications:
        applicant = await applicant_service.get_applicant(app.applicant_id)
        if applicant:
            result.append(ApprovedApplicantResponse(
                application_id=app.id,
                reference_number=app.reference_number,
                applicant_id=app.applicant_id,
                applicant_name=applicant.full_name,
                document_type=app.document_type,
                approved_at=app.approved_at,
                approved_by=app.approved_by,
            ))
    
    return result


# ==================== Document Type Configuration ====================

@router.get("/document-types", response_model=list[dict[str, Any]])
async def get_document_types() -> list[dict[str, Any]]:
    """
    Get supported document types with their vetting requirements.
    
    Returns:
        List of document types and their configurations
    """
    from .service import DEFAULT_VETTING_REQUIREMENTS
    
    return [
        {
            "document_type": doc_type,
            "requirements": [
                {
                    "check_type": req["type"].value,
                    "required": req["required"],
                    "order": req["order"],
                }
                for req in requirements
            ],
        }
        for doc_type, requirements in DEFAULT_VETTING_REQUIREMENTS.items()
    ]
