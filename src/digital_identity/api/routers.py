"""
Digital Identity API Routers

FastAPI endpoints for Compliance Profiles and Application Templates.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from digital_identity.api.schemas import (
    ApplicationTemplateCreate,
    ApplicationTemplateListResponse,
    ApplicationTemplateResponse,
    ApplicationTemplateUpdate,
    ArtifactValidationRequest,
    ArtifactValidationResponse,
    ComplianceProfileCreate,
    ComplianceProfileListResponse,
    ComplianceProfileResponse,
    ComplianceProfileUpdate,
)
from digital_identity.application.services.issuer_artifact_service import (
    IssuerArtifactMissingError,
    IssuerArtifactService,
)
from digital_identity.domain.entities import ApplicationTemplate, ComplianceProfile
from digital_identity.domain.value_objects import (
    CredentialFormat,
    ARTIFACT_REQUIREMENTS,
)

logger = logging.getLogger(__name__)

# Routers
compliance_profile_router = APIRouter(
    prefix="/v1/compliance-profiles",
    tags=["compliance-profiles"]
)

application_template_router = APIRouter(
    prefix="/v1/application-templates",
    tags=["application-templates"]
)


# =============================================================================
# Dependencies (to be configured by application)
# =============================================================================

async def get_compliance_profile_service():
    """Get ComplianceProfileService instance."""
    raise NotImplementedError("ComplianceProfileService dependency not configured")


async def get_application_template_service():
    """Get ApplicationTemplateService instance."""
    raise NotImplementedError("ApplicationTemplateService dependency not configured")


async def get_issuer_artifact_service() -> IssuerArtifactService:
    """Get IssuerArtifactService instance."""
    raise NotImplementedError("IssuerArtifactService dependency not configured")


# =============================================================================
# Compliance Profile Endpoints
# =============================================================================

@compliance_profile_router.post(
    "",
    response_model=ComplianceProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Compliance Profile",
    description="Create a new compliance profile to abstract credential format complexity."
)
async def create_compliance_profile(
    request: ComplianceProfileCreate,
    service=Depends(get_compliance_profile_service),
) -> ComplianceProfileResponse:
    """Create a new compliance profile."""
    try:
        # Check for duplicate code
        existing = await service.get_by_code(request.compliance_code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Compliance profile with code '{request.compliance_code}' already exists"
            )
        
        # Create profile
        profile = await service.create(
            name=request.name,
            compliance_code=request.compliance_code,
            credential_format=request.credential_format,
            description=request.description,
            issuer_artifact_requirements=request.issuer_artifact_requirements,
            default_verification_rules=request.default_verification_rules,
            trust_profile_constraints=request.trust_profile_constraints,
            metadata=request.metadata,
        )
        
        return ComplianceProfileResponse.model_validate(profile)
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("Failed to create compliance profile")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create compliance profile"
        )


@compliance_profile_router.get(
    "",
    response_model=ComplianceProfileListResponse,
    summary="List Compliance Profiles",
    description="List all compliance profiles with optional filtering."
)
async def list_compliance_profiles(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    include_system: bool = Query(True, description="Include system presets"),
    service=Depends(get_compliance_profile_service),
) -> ComplianceProfileListResponse:
    """List compliance profiles."""
    try:
        profiles, total = await service.list(
            page=page,
            page_size=page_size,
            include_system=include_system,
        )
        
        return ComplianceProfileListResponse(
            items=[ComplianceProfileResponse.model_validate(p) for p in profiles],
            total=total,
            page=page,
            page_size=page_size,
        )
    
    except Exception as e:
        logger.exception("Failed to list compliance profiles")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list compliance profiles"
        )


@compliance_profile_router.get(
    "/{profile_id}",
    response_model=ComplianceProfileResponse,
    summary="Get Compliance Profile",
    description="Get a compliance profile by ID."
)
async def get_compliance_profile(
    profile_id: str,
    service=Depends(get_compliance_profile_service),
) -> ComplianceProfileResponse:
    """Get compliance profile by ID."""
    try:
        profile = await service.get(profile_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Compliance profile '{profile_id}' not found"
            )
        
        return ComplianceProfileResponse.model_validate(profile)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get compliance profile")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get compliance profile"
        )


@compliance_profile_router.put(
    "/{profile_id}",
    response_model=ComplianceProfileResponse,
    summary="Update Compliance Profile",
    description="Update a compliance profile. System profiles cannot be modified."
)
async def update_compliance_profile(
    profile_id: str,
    request: ComplianceProfileUpdate,
    service=Depends(get_compliance_profile_service),
) -> ComplianceProfileResponse:
    """Update compliance profile."""
    try:
        # Get existing profile
        profile = await service.get(profile_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Compliance profile '{profile_id}' not found"
            )
        
        # Check if system profile
        if profile.is_system:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify system compliance profiles"
            )
        
        # Update profile
        updated = await service.update(profile_id, request.model_dump(exclude_unset=True))
        
        return ComplianceProfileResponse.model_validate(updated)
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("Failed to update compliance profile")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update compliance profile"
        )


@compliance_profile_router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Compliance Profile",
    description="Delete a compliance profile. System profiles cannot be deleted."
)
async def delete_compliance_profile(
    profile_id: str,
    service=Depends(get_compliance_profile_service),
) -> None:
    """Delete compliance profile."""
    try:
        # Get existing profile
        profile = await service.get(profile_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Compliance profile '{profile_id}' not found"
            )
        
        # Check if system profile
        if profile.is_system:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete system compliance profiles"
            )
        
        await service.delete(profile_id)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete compliance profile")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete compliance profile"
        )


# =============================================================================
# Application Template Endpoints
# =============================================================================

@application_template_router.post(
    "",
    response_model=ApplicationTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Application Template",
    description="Create a new application template for credential issuance."
)
async def create_application_template(
    request: ApplicationTemplateCreate,
    environment: str = Query("development", description="Environment: development, staging, production"),
    service=Depends(get_application_template_service),
    artifact_service: IssuerArtifactService = Depends(get_issuer_artifact_service),
) -> ApplicationTemplateResponse:
    """Create a new application template."""
    try:
        # Create template
        template = await service.create(
            name=request.name,
            credential_template_id=request.credential_template_id,
            compliance_profile_id=request.compliance_profile_id,
            description=request.description,
            evidence_requirements=request.evidence_requirements,
            claim_verification_rules=request.claim_verification_rules,
            issuer_key_id=request.issuer_key_id,
            issuer_certificate_chain_pem=request.issuer_certificate_chain_pem,
            issuer_did=request.issuer_did,
            auto_generate_artifacts=request.auto_generate_artifacts,
            approval_strategy=request.approval_strategy,
            application_validity_days=request.application_validity_days,
            metadata=request.metadata,
        )
        
        # Ensure issuer artifacts (may auto-generate in dev)
        compliance_profile = await service.get_compliance_profile(request.compliance_profile_id)
        template = await artifact_service.ensure_issuer_artifacts(
            template,
            compliance_profile,
            environment=environment,
        )
        
        # Save updated template
        template = await service.update(template.id, template)
        
        return ApplicationTemplateResponse.model_validate(template)
    
    except IssuerArtifactMissingError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing issuer artifacts: {', '.join(e.errors)}"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("Failed to create application template")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create application template"
        )


@application_template_router.get(
    "",
    response_model=ApplicationTemplateListResponse,
    summary="List Application Templates",
    description="List all application templates."
)
async def list_application_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    compliance_profile_id: str | None = Query(None, description="Filter by compliance profile"),
    service=Depends(get_application_template_service),
) -> ApplicationTemplateListResponse:
    """List application templates."""
    try:
        templates, total = await service.list(
            page=page,
            page_size=page_size,
            compliance_profile_id=compliance_profile_id,
        )
        
        return ApplicationTemplateListResponse(
            items=[ApplicationTemplateResponse.model_validate(t) for t in templates],
            total=total,
            page=page,
            page_size=page_size,
        )
    
    except Exception as e:
        logger.exception("Failed to list application templates")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list application templates"
        )


@application_template_router.get(
    "/{template_id}",
    response_model=ApplicationTemplateResponse,
    summary="Get Application Template",
    description="Get an application template by ID."
)
async def get_application_template(
    template_id: str,
    service=Depends(get_application_template_service),
) -> ApplicationTemplateResponse:
    """Get application template by ID."""
    try:
        template = await service.get(template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application template '{template_id}' not found"
            )
        
        return ApplicationTemplateResponse.model_validate(template)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get application template")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get application template"
        )


@application_template_router.put(
    "/{template_id}",
    response_model=ApplicationTemplateResponse,
    summary="Update Application Template",
    description="Update an application template."
)
async def update_application_template(
    template_id: str,
    request: ApplicationTemplateUpdate,
    service=Depends(get_application_template_service),
) -> ApplicationTemplateResponse:
    """Update application template."""
    try:
        # Get existing template
        template = await service.get(template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application template '{template_id}' not found"
            )
        
        # Update template
        updated = await service.update(template_id, request.model_dump(exclude_unset=True))
        
        return ApplicationTemplateResponse.model_validate(updated)
    
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("Failed to update application template")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update application template"
        )


@application_template_router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Application Template",
    description="Delete an application template."
)
async def delete_application_template(
    template_id: str,
    service=Depends(get_application_template_service),
) -> None:
    """Delete application template."""
    try:
        template = await service.get(template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application template '{template_id}' not found"
            )
        
        await service.delete(template_id)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete application template")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete application template"
        )


# =============================================================================
# Artifact Validation Endpoint
# =============================================================================

@application_template_router.post(
    "/validate-artifacts",
    response_model=ArtifactValidationResponse,
    summary="Validate Issuer Artifacts",
    description="Validate that required issuer artifacts are present for a credential format."
)
async def validate_issuer_artifacts(
    request: ArtifactValidationRequest,
    artifact_service: IssuerArtifactService = Depends(get_issuer_artifact_service),
) -> ArtifactValidationResponse:
    """Validate issuer artifacts for a credential format."""
    try:
        errors = await artifact_service.validate_artifacts_for_format(
            credential_format=CredentialFormat(request.credential_format),
            issuer_key_id=request.issuer_key_id,
            issuer_certificate_chain_pem=request.issuer_certificate_chain_pem,
            issuer_did=request.issuer_did,
        )
        
        return ArtifactValidationResponse(
            valid=len(errors) == 0,
            errors=errors,
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception("Failed to validate issuer artifacts")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to validate issuer artifacts"
        )
