"""
FastAPI Routers for Digital Identity API

Implements REST endpoints with /v1/identity/ prefix.
"""

from __future__ import annotations

import logging
from typing import Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from digital_identity.infrastructure.adapters.rest.schemas import (
    # Trust Profile
    TrustProfileCreate,
    TrustProfileUpdate,
    TrustProfileResponse,
    # Issuer Registry
    TrustProfileIssuerAdd,
    TrustProfileIssuerUpdate,
    TrustProfileIssuerResponse,
    RevocationServicesConfig,
    SystemIssuerOverride,
    # Credential Template
    CredentialTemplateCreate,
    CredentialTemplateUpdate,
    CredentialTemplateResponse,
    # Presentation Policy
    PresentationPolicyCreate,
    PresentationPolicyUpdate,
    PresentationPolicyResponse,
    # Deployment Profile
    DeploymentProfileCreate,
    DeploymentProfileUpdate,
    DeploymentProfileResponse,
    # Lane
    LaneCreate,
    LaneUpdate,
    LaneResponse,
    LaneDeviceAssignment,
    # Flow
    FlowCreate,
    FlowUpdate,
    FlowResponse,
    FlowExecutionStart,
    FlowExecutionApproval,
    FlowExecutionResponse,
    # Revocation Profile
    RevocationProfileCreate,
    RevocationProfileUpdate,
    RevocationProfileResponse,
    # Application Template
    ApplicationTemplateCreate,
    ApplicationTemplateUpdate,
    ApplicationTemplateResponse,
    # Verification Session
    VerificationSessionCreate,
    VerificationSessionUpdate,
    VerificationSessionResponse,
    # Compliance Profile
    ComplianceProfileCreate,
    ComplianceProfileUpdate,
    ComplianceProfileResponse,
    # Trust Framework
    TrustFrameworkCreate,
    TrustFrameworkUpdate,
    TrustFrameworkResponse,
    # Organization Trust Profile
    OrganizationTrustProfileCreate,
    OrganizationTrustProfileUpdate,
    OrganizationTrustProfileResponse,
    # Organization
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationResponse,
    # Webhook
    WebhookCreate,
    WebhookUpdate,
    WebhookResponse,
    # Subscription
    SubscriptionCreate,
    SubscriptionUpdate,
    SubscriptionResponse,
    # API Key
    ApiKeyCreate,
    ApiKeyUpdate,
    ApiKeyResponse,
    # Issuance Record
    IssuanceRecordCreate,
    IssuanceRecordUpdate,
    IssuanceRecordResponse,
    # Policy Set
    PolicySetCreate,
    PolicySetUpdate,
    PolicySetResponse,
    # Wallet Profile
    WalletProfileCreate,
    WalletProfileUpdate,
    WalletProfileResponse,
    # Device Registration
    DeviceRegistrationCreate,
    DeviceRegistrationUpdate,
    DeviceRegistrationResponse,
    # Applicant
    ApplicantCreate,
    ApplicantUpdate,
    ApplicantResponse,
    # Reviewer Lock
    ReviewerLockCreate,
    ReviewerLockResponse,
    # Vetting Check
    VettingCheckCreate,
    VettingCheckUpdate,
    VettingCheckResponse,
    # Biometric Enrollment
    BiometricEnrollmentCreate,
    BiometricEnrollmentUpdate,
    BiometricEnrollmentResponse,
    # Notification Payload
    NotificationPayloadCreate,
    NotificationPayloadResponse,
    NotificationTargetSchema,
    # Common
    ErrorResponse,
)
from digital_identity.infrastructure.adapters.rest.dependencies import (
    get_trust_profile_service,
    get_credential_template_service,
    get_presentation_policy_service,
    get_deployment_profile_service,
    get_lane_service,
    get_flow_service,
    get_issuer_registry_service,
    get_revocation_profile_service,
    get_application_template_service,
    get_verification_session_service,
    get_compliance_profile_service,
    get_trust_framework_service,
    get_organization_trust_profile_service,
    get_organization_service,
    get_webhook_service,
    get_subscription_service,
    get_api_key_service,
    get_issuance_record_service,
    get_policy_set_service,
    get_wallet_profile_service,
    get_device_registration_service,
    get_applicant_service,
    get_reviewer_lock_service,
    get_vetting_check_service,
    get_biometric_enrollment_service,
    get_notification_payload_service,
)
from digital_identity.domain.value_objects import FLOW_STEPS, FlowType

logger = logging.getLogger(__name__)

# =========================================================
# Trust Profile Router
# =========================================================

trust_profile_router = APIRouter(
    prefix="/v1/identity/trust-profiles",
    tags=["Trust Profiles"],
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@trust_profile_router.post(
    "",
    response_model=TrustProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Trust Profile",
    description="Create a new trust profile that defines trust sources and validation policies.",
)
async def create_trust_profile(
    data: TrustProfileCreate,
    service=Depends(get_trust_profile_service),
) -> TrustProfileResponse:
    """Create a new Trust Profile."""
    try:
        profile = await service.create(**data.model_dump())
        return _trust_profile_to_response(profile)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create trust profile")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@trust_profile_router.get(
    "",
    response_model=list[TrustProfileResponse],
    summary="List Trust Profiles",
    description="List all trust profiles with optional filtering.",
)
async def list_trust_profiles(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
    profile_type: str | None = Query(None, description="Filter by profile type"),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
    service=Depends(get_trust_profile_service),
) -> list[TrustProfileResponse]:
    """List Trust Profiles."""
    from digital_identity.domain.value_objects import TrustProfileType
    
    # Convert profile_type string to enum if provided
    profile_type_enum = TrustProfileType(profile_type) if profile_type else None
    
    profiles = await service.list(
        skip=skip,
        limit=limit,
        profile_type=profile_type_enum,
        enabled=enabled,
    )
    return [_trust_profile_to_response(p) for p in profiles]


@trust_profile_router.get(
    "/{profile_id}",
    response_model=TrustProfileResponse,
    summary="Get Trust Profile",
    description="Get a trust profile by ID.",
)
async def get_trust_profile(
    profile_id: str,
    service=Depends(get_trust_profile_service),
) -> TrustProfileResponse:
    """Get a Trust Profile by ID."""
    profile = await service.get(profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust profile not found")
    return _trust_profile_to_response(profile)


@trust_profile_router.get(
    "/by-name/{name}",
    response_model=TrustProfileResponse,
    summary="Get Trust Profile by Name",
    description="Get a trust profile by name.",
)
async def get_trust_profile_by_name(
    name: str,
    service=Depends(get_trust_profile_service),
) -> TrustProfileResponse:
    """Get a Trust Profile by name."""
    profile = await service.get_by_name(name)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust profile not found")
    return _trust_profile_to_response(profile)


@trust_profile_router.patch(
    "/{profile_id}",
    response_model=TrustProfileResponse,
    summary="Update Trust Profile",
    description="Partially update a trust profile.",
)
async def update_trust_profile(
    profile_id: str,
    data: TrustProfileUpdate,
    service=Depends(get_trust_profile_service),
) -> TrustProfileResponse:
    """Update a Trust Profile."""
    try:
        profile = await service.update(profile_id, **data.model_dump(exclude_unset=True))
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust profile not found")
        return _trust_profile_to_response(profile)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@trust_profile_router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Trust Profile",
    description="Delete a trust profile.",
)
async def delete_trust_profile(
    profile_id: str,
    service=Depends(get_trust_profile_service),
) -> None:
    """Delete a Trust Profile."""
    deleted = await service.delete(profile_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust profile not found")


@trust_profile_router.post(
    "/{profile_id}/trust-sources",
    response_model=TrustProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Trust Source",
    description="Add a trust source to an existing trust profile.",
)
async def add_trust_source(
    profile_id: str,
    source_type: str = Query(..., description="Type of trust source (e.g., 'pkd', 'iaca', 'x509_pinned')"),
    source_uri: str | None = Query(None, description="Optional URI for the trust source"),
    config: dict[str, Any] | None = None,
    service=Depends(get_trust_profile_service),
) -> TrustProfileResponse:
    """Add a trust source to a Trust Profile."""
    profile = await service.add_trust_source(
        profile_id=profile_id,
        source_type=source_type,
        source_uri=source_uri,
        config=config,
    )
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust profile not found")
    return _trust_profile_to_response(profile)


@trust_profile_router.post(
    "/{profile_id}/refresh",
    response_model=dict[str, Any],
    summary="Refresh Trust Profile",
    description="Refresh trust anchors from configured sources.",
)
async def refresh_trust_profile(
    profile_id: str,
    service=Depends(get_trust_profile_service),
) -> dict[str, Any]:
    """Refresh a Trust Profile's anchors."""
    result = await service.refresh_trust_data(profile_id)
    return result


# Issuer Management Endpoints

@trust_profile_router.post(
    "/{profile_id}/issuers",
    response_model=TrustProfileIssuerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Issuer to Trust Profile",
    description="Add an issuer to a trust profile with trust level and cascade policy.",
)
async def add_issuer_to_trust_profile(
    profile_id: str,
    data: TrustProfileIssuerAdd,
    issuer_service=Depends(get_issuer_registry_service),
) -> TrustProfileIssuerResponse:
    """Add an issuer to a trust profile."""
    try:
        relationship = await issuer_service.add_issuer_to_trust_profile(
            trust_profile_id=profile_id,
            issuer_id=data.issuer_id,
            trust_level=data.trust_level,
            cascade_policy=data.cascade_revocation_policy,
            relationship_status=data.relationship_status,
        )
        return _trust_profile_issuer_to_response(relationship)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to add issuer to trust profile")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@trust_profile_router.get(
    "/{profile_id}/issuers",
    response_model=list[TrustProfileIssuerResponse],
    summary="List Trust Profile Issuers",
    description="List all issuers associated with a trust profile (includes system issuers).",
)
async def list_trust_profile_issuers(
    profile_id: str,
    include_system: bool = Query(default=True, description="Include system issuers"),
    issuer_service=Depends(get_issuer_registry_service),
) -> list[TrustProfileIssuerResponse]:
    """List issuers for a trust profile."""
    try:
        relationships = await issuer_service.get_trust_profile_issuers(
            profile_id, include_system=include_system
        )
        return [_trust_profile_issuer_to_response(r) for r in relationships]
    except Exception as e:
        logger.exception("Failed to list trust profile issuers")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@trust_profile_router.patch(
    "/{profile_id}/issuers/{issuer_id}",
    response_model=TrustProfileIssuerResponse,
    summary="Update Issuer Relationship",
    description="Update trust level or cascade policy for an issuer.",
)
async def update_trust_profile_issuer(
    profile_id: str,
    issuer_id: str,
    data: TrustProfileIssuerUpdate,
    issuer_service=Depends(get_issuer_registry_service),
) -> TrustProfileIssuerResponse:
    """Update issuer relationship in trust profile."""
    try:
        if data.trust_level is not None:
            relationship = await issuer_service.update_trust_level(
                trust_profile_id=profile_id,
                issuer_id=issuer_id,
                new_level=data.trust_level,
                reason=data.reason,
            )
        else:
            relationship = await issuer_service.update_relationship(
                trust_profile_id=profile_id,
                issuer_id=issuer_id,
                cascade_policy=data.cascade_revocation_policy,
                relationship_status=data.relationship_status,
            )
        return _trust_profile_issuer_to_response(relationship)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to update trust profile issuer")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@trust_profile_router.delete(
    "/{profile_id}/issuers/{issuer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove Issuer from Trust Profile",
    description="Remove an issuer relationship from a trust profile.",
)
async def remove_issuer_from_trust_profile(
    profile_id: str,
    issuer_id: str,
    issuer_service=Depends(get_issuer_registry_service),
) -> None:
    """Remove issuer from trust profile."""
    try:
        await issuer_service.remove_issuer_from_trust_profile(profile_id, issuer_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception("Failed to remove issuer from trust profile")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# Revocation Configuration Endpoints

@trust_profile_router.get(
    "/{profile_id}/revocation-config",
    response_model=RevocationServicesConfig,
    summary="Get Revocation Configuration",
    description="Get revocation services configuration for a trust profile.",
)
async def get_revocation_config(
    profile_id: str,
    service=Depends(get_trust_profile_service),
) -> RevocationServicesConfig:
    """Get revocation configuration."""
    try:
        profile = await service.get(profile_id)
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust profile not found")
        return RevocationServicesConfig(**profile.revocation_services)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get revocation config")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@trust_profile_router.put(
    "/{profile_id}/revocation-config",
    response_model=RevocationServicesConfig,
    summary="Update Revocation Configuration",
    description="Update revocation services configuration for a trust profile.",
)
async def update_revocation_config(
    profile_id: str,
    config: RevocationServicesConfig,
    service=Depends(get_trust_profile_service),
) -> RevocationServicesConfig:
    """Update revocation configuration."""
    try:
        profile = await service.update_revocation_services(profile_id, config.model_dump())
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust profile not found")
        return RevocationServicesConfig(**profile.revocation_services)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to update revocation config")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# System Issuer Override Endpoints

@trust_profile_router.put(
    "/{profile_id}/system-issuer-overrides",
    response_model=dict[str, SystemIssuerOverride],
    summary="Update System Issuer Overrides",
    description="Bulk update system issuer overrides for a trust profile.",
)
async def update_system_issuer_overrides(
    profile_id: str,
    overrides: dict[str, SystemIssuerOverride],
    service=Depends(get_trust_profile_service),
) -> dict[str, SystemIssuerOverride]:
    """Update system issuer overrides."""
    try:
        overrides_dict = {k: v.model_dump() for k, v in overrides.items()}
        profile = await service.update_system_issuer_overrides(profile_id, overrides_dict)
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust profile not found")
        return {k: SystemIssuerOverride(**v) for k, v in profile.system_issuer_overrides.items()}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to update system issuer overrides")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def _trust_profile_issuer_to_response(relationship) -> TrustProfileIssuerResponse:
    """Convert relationship entity to response schema."""
    return TrustProfileIssuerResponse(
        trust_profile_id=relationship.trust_profile_id,
        issuer_id=relationship.issuer_id,
        trust_level=relationship.trust_level,
        relationship_status=relationship.relationship_status,
        cascade_revocation_policy=relationship.cascade_revocation_policy,
        metadata=relationship.metadata,
        created_at=relationship.created_at,
        updated_at=relationship.updated_at,
    )


def _trust_profile_to_response(profile) -> TrustProfileResponse:
    """Convert entity to response schema."""
    return TrustProfileResponse(
        id=profile.id,
        organization_id=profile.organization_id,
        name=profile.name,
        description=profile.description,
        profile_type=profile.profile_type.value,
        enabled=profile.enabled,
        trust_sources=profile.trust_sources,
        allowed_algorithms=[a.value for a in profile.allowed_algorithms],
        supported_formats=[f.value for f in profile.supported_formats],
        revocation_policy={
            "check_mode": profile.revocation_policy.check_mode.value,
            "cache_ttl_seconds": profile.revocation_policy.cache_ttl_seconds,
        },
        time_policy={
            "clock_skew_seconds": profile.time_policy.clock_skew_seconds,
            "max_credential_age_seconds": profile.time_policy.max_credential_age_seconds,
            "require_freshness": profile.time_policy.require_freshness,
            "freshness_window_seconds": profile.time_policy.freshness_window_seconds,
        },
        revocation_profile_id=profile.revocation_profile_id,
        allowed_issuers=profile.allowed_issuers,
        denied_issuers=profile.denied_issuers,
        compliance_status=profile.compliance_status,
        auto_generated=profile.auto_generated,
        revocation_services=getattr(profile, 'revocation_services', None),
        system_issuer_overrides=getattr(profile, 'system_issuer_overrides', None),
        metadata=profile.metadata,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        version=profile.version,
    )


# =========================================================
# Credential Template Router
# =========================================================

credential_template_router = APIRouter(
    prefix="/v1/identity/credential-templates",
    tags=["Credential Templates"],
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@credential_template_router.post(
    "",
    response_model=CredentialTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Credential Template",
    description="Create a new credential template defining schema and claims.",
)
async def create_credential_template(
    data: CredentialTemplateCreate,
    service=Depends(get_credential_template_service),
) -> CredentialTemplateResponse:
    """Create a new Credential Template."""
    try:
        template = await service.create(data.model_dump())
        return _credential_template_to_response(template)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create credential template")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@credential_template_router.get(
    "",
    response_model=list[CredentialTemplateResponse],
    summary="List Credential Templates",
    description="List all credential templates with optional filtering.",
)
async def list_credential_templates(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    format: str | None = Query(None, description="Filter by format"),
    service=Depends(get_credential_template_service),
) -> list[CredentialTemplateResponse]:
    """List Credential Templates."""
    templates = await service.list(skip=skip, limit=limit, format=format)
    return [_credential_template_to_response(t) for t in templates]


@credential_template_router.get(
    "/{template_id}",
    response_model=CredentialTemplateResponse,
    summary="Get Credential Template",
)
async def get_credential_template(
    template_id: str,
    service=Depends(get_credential_template_service),
) -> CredentialTemplateResponse:
    """Get a Credential Template by ID."""
    template = await service.get(template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential template not found")
    return _credential_template_to_response(template)


@credential_template_router.patch(
    "/{template_id}",
    response_model=CredentialTemplateResponse,
    summary="Update Credential Template",
)
async def update_credential_template(
    template_id: str,
    data: CredentialTemplateUpdate,
    service=Depends(get_credential_template_service),
) -> CredentialTemplateResponse:
    """Update a Credential Template."""
    try:
        template = await service.update(template_id, data.model_dump(exclude_unset=True))
        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential template not found")
        return _credential_template_to_response(template)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@credential_template_router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Credential Template",
)
async def delete_credential_template(
    template_id: str,
    service=Depends(get_credential_template_service),
) -> None:
    """Delete a Credential Template."""
    deleted = await service.delete(template_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential template not found")


@credential_template_router.post(
    "/{template_id}/publish",
    response_model=CredentialTemplateResponse,
    summary="Publish Credential Template",
    description="Transition a template from DRAFT to ACTIVE. Validates completeness unless force=true.",
)
async def publish_credential_template(
    template_id: str,
    force: bool = False,
    service=Depends(get_credential_template_service),
) -> CredentialTemplateResponse:
    """Publish a Credential Template (DRAFT → ACTIVE)."""
    try:
        template = await service.publish(template_id, force=force)
        return _credential_template_to_response(template)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@credential_template_router.post(
    "/{template_id}/unpublish",
    response_model=CredentialTemplateResponse,
    summary="Archive Credential Template",
    description="Transition a template to ARCHIVED status.",
)
async def unpublish_credential_template(
    template_id: str,
    reason: str | None = None,
    service=Depends(get_credential_template_service),
) -> CredentialTemplateResponse:
    """Archive a Credential Template (any → ARCHIVED)."""
    try:
        template = await service.unpublish(template_id, reason=reason)
        return _credential_template_to_response(template)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _credential_template_to_response(template) -> CredentialTemplateResponse:
    """Convert entity to response schema."""
    return CredentialTemplateResponse(
        id=template.id,
        organization_id=getattr(template, 'organization_id', ''),
        name=template.name,
        description=template.description,
        credential_type=template.credential_type,
        compliance_profile_id=getattr(template, 'compliance_profile_id', None),
        vct=getattr(template, 'vct', None),
        credential_payload_format=getattr(template, 'format', None) and template.format.value or 'SD_JWT_VC',
        claims=[
            {
                "name": c.name,
                "display_name": c.display_name,
                "type": c.claim_type,
                "required": c.required,
                "selectively_disclosable": c.selectively_disclosable,
                "derived_from": c.derived_from,
                "predicate_type": c.predicate_type,
                "predicate_value": c.predicate_value,
            }
            for c in template.claims
        ],
        validity_rules={
            "ttl_seconds": template.validity_rules.ttl_seconds,
            "renewable": template.validity_rules.renewable,
            "reissue_within_seconds": template.validity_rules.reissue_within_seconds,
            "not_before_offset_seconds": template.validity_rules.not_before_offset_seconds,
        },
        trust_profile_id=template.trust_profile_id,
        revocation_profile_id=getattr(template, 'revocation_profile_id', None),
        issuer_key_id=getattr(template, 'issuer_key_id', None),
        issuer_algorithm=getattr(template, 'issuer_algorithm', None),
        key_access_mode=getattr(template, 'key_access_mode', 'key_vault'),
        auto_generate_artifacts=getattr(template, 'auto_generate_artifacts', False),
        issuer_certificate_chain_pem=getattr(template, 'issuer_certificate_chain_pem', None),
        issuer_did=getattr(template, 'issuer_did', None),
        namespace=template.namespace,
        privacy_posture=getattr(template, 'privacy_posture', None) and template.privacy_posture.to_dict() if hasattr(getattr(template, 'privacy_posture', None), 'to_dict') else None,
        status=getattr(template, 'status', 'DRAFT'),
        display=template.display,
        metadata=template.metadata,
        created_at=template.created_at,
        updated_at=template.updated_at,
        version=template.version,
    )


# =========================================================
# Presentation Policy Router
# =========================================================

presentation_policy_router = APIRouter(
    prefix="/v1/identity/presentation-policies",
    tags=["Presentation Policies"],
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@presentation_policy_router.post(
    "",
    response_model=PresentationPolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Presentation Policy",
)
async def create_presentation_policy(
    data: PresentationPolicyCreate,
    service=Depends(get_presentation_policy_service),
) -> PresentationPolicyResponse:
    """Create a new Presentation Policy."""
    try:
        policy = await service.create(data.model_dump())
        return _presentation_policy_to_response(policy)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create presentation policy")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@presentation_policy_router.get(
    "",
    response_model=list[PresentationPolicyResponse],
    summary="List Presentation Policies",
)
async def list_presentation_policies(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    trust_profile_id: str | None = Query(None),
    service=Depends(get_presentation_policy_service),
) -> list[PresentationPolicyResponse]:
    """List Presentation Policies."""
    policies = await service.list(skip=skip, limit=limit, trust_profile_id=trust_profile_id)
    return [_presentation_policy_to_response(p) for p in policies]


@presentation_policy_router.get(
    "/{policy_id}",
    response_model=PresentationPolicyResponse,
    summary="Get Presentation Policy",
)
async def get_presentation_policy(
    policy_id: str,
    service=Depends(get_presentation_policy_service),
) -> PresentationPolicyResponse:
    """Get a Presentation Policy by ID."""
    policy = await service.get(policy_id)
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Presentation policy not found")
    return _presentation_policy_to_response(policy)


@presentation_policy_router.patch(
    "/{policy_id}",
    response_model=PresentationPolicyResponse,
    summary="Update Presentation Policy",
)
async def update_presentation_policy(
    policy_id: str,
    data: PresentationPolicyUpdate,
    service=Depends(get_presentation_policy_service),
) -> PresentationPolicyResponse:
    """Update a Presentation Policy."""
    try:
        policy = await service.update(policy_id, data.model_dump(exclude_unset=True))
        if not policy:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Presentation policy not found")
        return _presentation_policy_to_response(policy)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@presentation_policy_router.delete(
    "/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Presentation Policy",
)
async def delete_presentation_policy(
    policy_id: str,
    service=Depends(get_presentation_policy_service),
) -> None:
    """Delete a Presentation Policy."""
    deleted = await service.delete(policy_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Presentation policy not found")


@presentation_policy_router.get(
    "/sync",
    response_model=list[PresentationPolicyResponse],
    summary="Sync Presentation Policies",
    description="Authenticated endpoint for syncing policies to verifier/mobile apps. Requires license JWT as Bearer token.",
)
async def sync_presentation_policies(
    if_modified_since: str | None = Header(None, alias="If-Modified-Since"),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    service=Depends(get_presentation_policy_service),
) -> list[PresentationPolicyResponse]:
    """
    Sync Presentation Policies with delta support.
    
    Accepts license JWT as Bearer token for authentication.
    Supports If-Modified-Since header for delta sync.
    """
    # TODO: Validate license JWT and extract org_id
    # For now, return all policies
    # In production, filter by org_id from license claims
    
    modified_since = None
    if if_modified_since:
        try:
            # Parse RFC 2822 date format
            modified_since = datetime.strptime(if_modified_since, "%a, %d %b %Y %H:%M:%S GMT")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid If-Modified-Since header format. Expected RFC 2822 format."
            )
    
    # Get all policies (TODO: filter by org_id and modified_since)
    policies = await service.list(skip=0, limit=1000)
    
    # Filter by modification time if provided
    if modified_since:
        policies = [p for p in policies if p.updated_at > modified_since]
    
    return [_presentation_policy_to_response(p) for p in policies]


def _presentation_policy_to_response(policy) -> PresentationPolicyResponse:
    """Convert entity to response schema."""
    # Build holder_binding as dict (spec shape)
    holder_binding_dict = policy.holder_binding.to_dict()
    return PresentationPolicyResponse(
        id=policy.id,
        organization_id=getattr(policy, 'organization_id', ''),
        name=policy.name,
        description=policy.description,
        purpose=policy.purpose,
        accepted_credential_types=policy.accepted_credential_types,
        required_claims=[
            {
                "claim_name": c.claim_name,
                "credential_type": c.credential_type,
                "accept_predicate": c.accept_predicate,
                "value_constraint": c.value_constraint,
            }
            for c in policy.required_claims
        ],
        holder_binding=holder_binding_dict,
        trust_profile_id=policy.trust_profile_id,
        allowed_issuers=policy.allowed_issuers,
        freshness_requirements={
            "max_age_seconds": policy.freshness_requirements.max_age_seconds,
            "require_not_revoked": policy.freshness_requirements.require_not_revoked,
            "revocation_grace_seconds": policy.freshness_requirements.revocation_grace_seconds,
        },
        prefer_predicates=policy.prefer_predicates,
        single_presentation=policy.single_presentation,
        derived_attribute_preferences=policy.derived_attribute_preferences,
        issuer_constraints=getattr(policy, 'issuer_constraints', {}),
        fallback_policy=policy.fallback_policy.value if hasattr(policy.fallback_policy, 'value') else str(policy.fallback_policy),
        supported_circuits=getattr(policy, 'supported_circuits', []),
        credential_ranking_strategy=policy.credential_ranking_strategy.value,
        credential_ranking_weights=policy.credential_ranking_weights,
        metadata=policy.metadata,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
        version=policy.version,
    )


# =========================================================
# Deployment Profile Router
# =========================================================

deployment_profile_router = APIRouter(
    prefix="/v1/identity/deployment-profiles",
    tags=["Deployment Profiles"],
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@deployment_profile_router.post(
    "",
    response_model=DeploymentProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Deployment Profile",
)
async def create_deployment_profile(
    data: DeploymentProfileCreate,
    service=Depends(get_deployment_profile_service),
) -> DeploymentProfileResponse:
    """Create a new Deployment Profile."""
    try:
        profile = await service.create(data.model_dump())
        return _deployment_profile_to_response(profile)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create deployment profile")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@deployment_profile_router.get(
    "",
    response_model=list[DeploymentProfileResponse],
    summary="List Deployment Profiles",
)
async def list_deployment_profiles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    network_mode: str | None = Query(None),
    service=Depends(get_deployment_profile_service),
) -> list[DeploymentProfileResponse]:
    """List Deployment Profiles."""
    profiles = await service.list(skip=skip, limit=limit, network_mode=network_mode)
    return [_deployment_profile_to_response(p) for p in profiles]


@deployment_profile_router.get(
    "/{profile_id}",
    response_model=DeploymentProfileResponse,
    summary="Get Deployment Profile",
)
async def get_deployment_profile(
    profile_id: str,
    service=Depends(get_deployment_profile_service),
) -> DeploymentProfileResponse:
    """Get a Deployment Profile by ID."""
    profile = await service.get(profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment profile not found")
    return _deployment_profile_to_response(profile)


@deployment_profile_router.patch(
    "/{profile_id}",
    response_model=DeploymentProfileResponse,
    summary="Update Deployment Profile",
)
async def update_deployment_profile(
    profile_id: str,
    data: DeploymentProfileUpdate,
    service=Depends(get_deployment_profile_service),
) -> DeploymentProfileResponse:
    """Update a Deployment Profile."""
    try:
        profile = await service.update(profile_id, data.model_dump(exclude_unset=True))
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment profile not found")
        return _deployment_profile_to_response(profile)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@deployment_profile_router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Deployment Profile",
)
async def delete_deployment_profile(
    profile_id: str,
    service=Depends(get_deployment_profile_service),
) -> None:
    """Delete a Deployment Profile."""
    deleted = await service.delete(profile_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment profile not found")


def _deployment_profile_to_response(profile) -> DeploymentProfileResponse:
    """Convert entity to response schema."""
    return DeploymentProfileResponse(
        id=profile.id,
        organization_id=getattr(profile, 'organization_id', ''),
        name=profile.name,
        description=profile.description,
        site_id=profile.site_id,
        enabled_flow_ids=profile.enabled_flow_ids,
        default_presentation_policy_id=profile.default_presentation_policy_id,
        network_mode=profile.network_mode.value,
        key_access_mode=profile.key_access_mode.value,
        ux_config={
            "language": profile.ux_config.language,
            "theme": profile.ux_config.theme,
            "operator_mode": profile.ux_config.operator_mode,
            "accessibility_mode": profile.ux_config.accessibility_mode,
            "signage_text": profile.ux_config.signage_text,
        },
        update_policy={
            "channel": profile.update_policy.channel,
            "auto_update": profile.update_policy.auto_update,
            "pinned_version": profile.update_policy.pinned_version,
            "rollout_percentage": profile.update_policy.rollout_percentage,
            "rollout_ring": profile.update_policy.rollout_ring,
        },
        lanes=[
            {
                "id": lane.id,
                "name": lane.name,
                "deployment_profile_id": lane.deployment_profile_id,
                "default_policy_id": lane.default_policy_id,
                "device_ids": lane.device_ids,
                "metadata": lane.metadata,
            }
            for lane in (profile.lanes or [])
        ],
        offline_cache_ttl_hours=profile.offline_cache_ttl_hours,
        biometric_required=profile.biometric_required,
        audit_all_events=profile.audit_all_events,
        metadata=profile.metadata,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        version=profile.version,
    )


# =========================================================
# Lane Router
# =========================================================

lane_router = APIRouter(
    prefix="/v1/identity/deployment-profiles",
    tags=["Lanes"],
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@lane_router.post(
    "/{profile_id}/lanes",
    response_model=LaneResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Lane",
)
async def create_lane(
    profile_id: str,
    data: LaneCreate,
    service=Depends(get_lane_service),
) -> LaneResponse:
    """Create a new Lane under a Deployment Profile."""
    try:
        lane = await service.create(
            deployment_profile_id=profile_id,
            **data.model_dump(),
        )
        return _lane_to_response(lane)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create lane")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@lane_router.get(
    "/{profile_id}/lanes",
    response_model=list[LaneResponse],
    summary="List Lanes in a Deployment Profile",
)
async def list_lanes(
    profile_id: str,
    service=Depends(get_lane_service),
) -> list[LaneResponse]:
    """List all Lanes in a Deployment Profile."""
    lanes = await service.list(deployment_profile_id=profile_id)
    return [_lane_to_response(l) for l in lanes]


@lane_router.get(
    "/{profile_id}/lanes/{lane_id}",
    response_model=LaneResponse,
    summary="Get Lane",
)
async def get_lane(
    profile_id: str,
    lane_id: str,
    service=Depends(get_lane_service),
) -> LaneResponse:
    """Get a Lane by ID."""
    lane = await service.get(deployment_profile_id=profile_id, lane_id=lane_id)
    if not lane:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lane not found")
    return _lane_to_response(lane)


@lane_router.patch(
    "/{profile_id}/lanes/{lane_id}",
    response_model=LaneResponse,
    summary="Update Lane",
)
async def update_lane(
    profile_id: str,
    lane_id: str,
    data: LaneUpdate,
    service=Depends(get_lane_service),
) -> LaneResponse:
    """Update a Lane."""
    try:
        lane = await service.update(
            deployment_profile_id=profile_id,
            lane_id=lane_id,
            **data.model_dump(exclude_unset=True),
        )
        if not lane:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lane not found")
        return _lane_to_response(lane)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@lane_router.delete(
    "/{profile_id}/lanes/{lane_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Lane",
)
async def delete_lane(
    profile_id: str,
    lane_id: str,
    service=Depends(get_lane_service),
) -> None:
    """Delete a Lane."""
    deleted = await service.delete(deployment_profile_id=profile_id, lane_id=lane_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lane not found")


@lane_router.post(
    "/{profile_id}/lanes/{lane_id}/assign-devices",
    response_model=LaneResponse,
    summary="Assign Devices to Lane",
)
async def assign_devices_to_lane(
    profile_id: str,
    lane_id: str,
    data: LaneDeviceAssignment,
    service=Depends(get_lane_service),
) -> LaneResponse:
    """Assign devices to a Lane."""
    try:
        lane = await service.assign_devices(
            deployment_profile_id=profile_id,
            lane_id=lane_id,
            device_ids=data.device_ids,
        )
        if not lane:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lane not found")
        return _lane_to_response(lane)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _lane_to_response(lane) -> LaneResponse:
    """Convert Lane entity to response schema."""
    return LaneResponse(
        id=lane.id,
        name=lane.name,
        deployment_profile_id=lane.deployment_profile_id,
        default_policy_id=lane.default_policy_id,
        device_ids=lane.device_ids,
        metadata=lane.metadata,
        created_at=lane.created_at,
        updated_at=lane.updated_at,
        version=lane.version,
    )


# =========================================================
# Flow Router
# =========================================================

flow_router = APIRouter(
    prefix="/v1/identity/flows",
    tags=["Flows"],
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@flow_router.post(
    "",
    response_model=FlowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Flow",
    description="Create a new flow combining trust profile, credential template, and policies.",
)
async def create_flow(
    data: FlowCreate,
    service=Depends(get_flow_service),
) -> FlowResponse:
    """Create a new Flow."""
    try:
        flow = await service.create(data.model_dump())
        return _flow_to_response(flow)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create flow")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@flow_router.get(
    "",
    response_model=list[FlowResponse],
    summary="List Flows",
)
async def list_flows(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    flow_type: str | None = Query(None),
    enabled: bool | None = Query(None),
    service=Depends(get_flow_service),
) -> list[FlowResponse]:
    """List Flows."""
    flows = await service.list(skip=skip, limit=limit, flow_type=flow_type, enabled=enabled)
    return [_flow_to_response(f) for f in flows]


@flow_router.get(
    "/{flow_id}",
    response_model=FlowResponse,
    summary="Get Flow",
)
async def get_flow(
    flow_id: str,
    service=Depends(get_flow_service),
) -> FlowResponse:
    """Get a Flow by ID."""
    flow = await service.get(flow_id)
    if not flow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found")
    return _flow_to_response(flow)


@flow_router.patch(
    "/{flow_id}",
    response_model=FlowResponse,
    summary="Update Flow",
)
async def update_flow(
    flow_id: str,
    data: FlowUpdate,
    service=Depends(get_flow_service),
) -> FlowResponse:
    """Update a Flow."""
    try:
        flow = await service.update(flow_id, data.model_dump(exclude_unset=True))
        if not flow:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found")
        return _flow_to_response(flow)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@flow_router.delete(
    "/{flow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Flow",
)
async def delete_flow(
    flow_id: str,
    service=Depends(get_flow_service),
) -> None:
    """Delete a Flow."""
    deleted = await service.delete(flow_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found")


@flow_router.post(
    "/{flow_id}/executions",
    response_model=FlowExecutionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start Flow Execution",
    description="Start a new execution of this flow.",
)
async def start_flow_execution(
    flow_id: str,
    data: FlowExecutionStart,
    service=Depends(get_flow_service),
) -> FlowExecutionResponse:
    """Start a flow execution."""
    try:
        execution = await service.start_execution(
            flow_id=flow_id,
            context=data.context_data,
        )
        return _flow_execution_to_response(execution)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Failed to start flow execution")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@flow_router.get(
    "/{flow_id}/executions",
    response_model=list[FlowExecutionResponse],
    summary="List Flow Executions",
)
async def list_flow_executions(
    flow_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: str | None = Query(None),
    service=Depends(get_flow_service),
) -> list[FlowExecutionResponse]:
    """List executions for a flow."""
    executions = await service.list_executions(
        flow_id=flow_id,
        skip=skip,
        limit=limit,
        status=status,
    )
    return [_flow_execution_to_response(e) for e in executions]


@flow_router.get(
    "/{flow_id}/executions/{execution_id}",
    response_model=FlowExecutionResponse,
    summary="Get Flow Execution",
)
async def get_flow_execution(
    flow_id: str,
    execution_id: str,
    service=Depends(get_flow_service),
) -> FlowExecutionResponse:
    """Get a flow execution by ID."""
    execution = await service.get_execution(execution_id)
    if not execution or execution.flow_id != flow_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flow execution not found")
    return _flow_execution_to_response(execution)


@flow_router.post(
    "/{flow_id}/executions/{execution_id}/approve",
    response_model=FlowExecutionResponse,
    summary="Approve Flow Execution",
    description="Approve a flow execution that is awaiting approval.",
)
async def approve_flow_execution(
    flow_id: str,
    execution_id: str,
    data: FlowExecutionApproval,
    service=Depends(get_flow_service),
) -> FlowExecutionResponse:
    """Approve a pending flow execution."""
    try:
        execution = await service.approve_execution(execution_id)
        if not execution:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flow execution not found")
        return _flow_execution_to_response(execution)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@flow_router.post(
    "/{flow_id}/executions/{execution_id}/reject",
    response_model=FlowExecutionResponse,
    summary="Reject Flow Execution",
    description="Reject a flow execution that is awaiting approval.",
)
async def reject_flow_execution(
    flow_id: str,
    execution_id: str,
    data: FlowExecutionApproval,
    service=Depends(get_flow_service),
) -> FlowExecutionResponse:
    """Reject a pending flow execution."""
    try:
        execution = await service.reject_execution(execution_id, reason=data.reason)
        if not execution:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flow execution not found")
        return _flow_execution_to_response(execution)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _flow_to_response(flow) -> FlowResponse:
    """Convert entity to response schema."""
    # Get fixed steps for this flow type
    steps = [s.value for s in FLOW_STEPS.get(flow.flow_type, [])]
    
    return FlowResponse(
        id=flow.id,
        organization_id=getattr(flow, 'organization_id', ''),
        name=flow.name,
        description=flow.description,
        flow_type=flow.flow_type.value,
        trust_profile_id=flow.trust_profile_id,
        credential_template_id=flow.credential_template_id,
        application_template_id=getattr(flow, 'application_template_id', None),
        presentation_policy_id=flow.presentation_policy_id,
        deployment_profile_ids=flow.deployment_profile_ids,
        approval_strategy=flow.approval_strategy.value,
        enabled=flow.enabled,
        status=getattr(flow, 'status', 'DRAFT'),
        hooks=flow.hooks,
        trigger=getattr(flow, 'trigger', None),
        flow_category=flow.flow_category,
        steps=steps,  # Include fixed protocol steps
        metadata=flow.metadata,
        created_at=flow.created_at,
        updated_at=flow.updated_at,
        version=flow.version,
    )


def _flow_execution_to_response(execution) -> FlowExecutionResponse:
    """Convert entity to response schema."""
    return FlowExecutionResponse(
        id=execution.id,
        flow_id=execution.flow_id,
        flow_type=getattr(execution, 'flow_type', ''),
        organization_id=getattr(execution, 'organization_id', ''),
        status=execution.status.value,
        current_step=execution.current_step,
        current_step_index=execution.current_step_index,
        step_results=execution.step_results,
        context_data=execution.context_data,
        issued_credential_id=execution.issued_credential_id,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        expires_at=getattr(execution, 'expires_at', None),
        error_code=execution.error_code,
        metadata=execution.metadata,
        created_at=execution.created_at,
        updated_at=execution.updated_at,
        version=execution.version,
    )


# =========================================================
# Revocation Profile Router
# =========================================================

revocation_profile_router = APIRouter(
    prefix="/v1/identity/revocation-profiles",
    tags=["Revocation Profiles"],
    responses={404: {"model": ErrorResponse}},
)


@revocation_profile_router.post(
    "",
    response_model=RevocationProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Revocation Profile",
)
async def create_revocation_profile(
    data: RevocationProfileCreate,
    service=Depends(get_revocation_profile_service),
) -> RevocationProfileResponse:
    """Create a new Revocation Profile."""
    try:
        profile = await service.create(**data.model_dump())
        return _revocation_profile_to_response(profile)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@revocation_profile_router.get(
    "",
    response_model=list[RevocationProfileResponse],
    summary="List Revocation Profiles",
)
async def list_revocation_profiles(
    skip: int = 0,
    limit: int = 100,
    organization_id: str | None = None,
    service=Depends(get_revocation_profile_service),
) -> list[RevocationProfileResponse]:
    """List Revocation Profiles."""
    profiles = await service.list(skip=skip, limit=limit, organization_id=organization_id)
    return [_revocation_profile_to_response(p) for p in profiles]


@revocation_profile_router.get(
    "/{profile_id}",
    response_model=RevocationProfileResponse,
    summary="Get Revocation Profile",
)
async def get_revocation_profile(
    profile_id: str,
    service=Depends(get_revocation_profile_service),
) -> RevocationProfileResponse:
    """Get a Revocation Profile by ID."""
    profile = await service.get(profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revocation profile not found")
    return _revocation_profile_to_response(profile)


@revocation_profile_router.patch(
    "/{profile_id}",
    response_model=RevocationProfileResponse,
    summary="Update Revocation Profile",
)
async def update_revocation_profile(
    profile_id: str,
    data: RevocationProfileUpdate,
    service=Depends(get_revocation_profile_service),
) -> RevocationProfileResponse:
    """Update a Revocation Profile."""
    try:
        profile = await service.update(profile_id, **data.model_dump(exclude_unset=True))
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revocation profile not found")
        return _revocation_profile_to_response(profile)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@revocation_profile_router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Revocation Profile",
)
async def delete_revocation_profile(
    profile_id: str,
    service=Depends(get_revocation_profile_service),
) -> None:
    """Delete a Revocation Profile."""
    deleted = await service.delete(profile_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revocation profile not found")


def _revocation_profile_to_response(profile) -> RevocationProfileResponse:
    """Convert entity to response schema."""
    return RevocationProfileResponse(
        id=profile.id,
        organization_id=profile.organization_id,
        name=profile.name,
        revocation_mechanism=profile.revocation_mechanism,
        mechanism_priority=profile.mechanism_priority,
        check_mode=profile.check_mode.value if hasattr(profile.check_mode, 'value') else profile.check_mode,
        cache_ttl_seconds=profile.cache_ttl_seconds,
        offline_grace_seconds=profile.offline_grace_seconds,
        issuer_config=profile.issuer_config,
        status_list_url=profile.status_list_url,
        metadata=profile.metadata,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        version=profile.version,
    )


# =========================================================
# Application Template Router
# =========================================================

application_template_router = APIRouter(
    prefix="/v1/identity/application-templates",
    tags=["Application Templates"],
    responses={404: {"model": ErrorResponse}},
)


@application_template_router.post(
    "",
    response_model=ApplicationTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Application Template",
)
async def create_application_template(
    data: ApplicationTemplateCreate,
    service=Depends(get_application_template_service),
) -> ApplicationTemplateResponse:
    """Create a new Application Template."""
    try:
        template = await service.create(**data.model_dump())
        return _application_template_to_response(template)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@application_template_router.get(
    "",
    response_model=list[ApplicationTemplateResponse],
    summary="List Application Templates",
)
async def list_application_templates(
    skip: int = 0,
    limit: int = 100,
    organization_id: str | None = None,
    service=Depends(get_application_template_service),
) -> list[ApplicationTemplateResponse]:
    """List Application Templates."""
    templates = await service.list(skip=skip, limit=limit, organization_id=organization_id)
    return [_application_template_to_response(t) for t in templates]


@application_template_router.get(
    "/{template_id}",
    response_model=ApplicationTemplateResponse,
    summary="Get Application Template",
)
async def get_application_template(
    template_id: str,
    service=Depends(get_application_template_service),
) -> ApplicationTemplateResponse:
    """Get an Application Template by ID."""
    template = await service.get(template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application template not found")
    return _application_template_to_response(template)


@application_template_router.patch(
    "/{template_id}",
    response_model=ApplicationTemplateResponse,
    summary="Update Application Template",
)
async def update_application_template(
    template_id: str,
    data: ApplicationTemplateUpdate,
    service=Depends(get_application_template_service),
) -> ApplicationTemplateResponse:
    """Update an Application Template."""
    try:
        template = await service.update(template_id, **data.model_dump(exclude_unset=True))
        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application template not found")
        return _application_template_to_response(template)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@application_template_router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Application Template",
)
async def delete_application_template(
    template_id: str,
    service=Depends(get_application_template_service),
) -> None:
    """Delete an Application Template."""
    deleted = await service.delete(template_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application template not found")


def _application_template_to_response(template) -> ApplicationTemplateResponse:
    """Convert entity to response schema."""
    return ApplicationTemplateResponse(
        id=template.id,
        name=template.name,
        organization_id=template.organization_id,
        description=template.description,
        status=template.status,
        evidence_requirements=[
            {
                "evidence_type": r.evidence_type.value if hasattr(r.evidence_type, "value") else str(r.evidence_type),
                "required": r.required,
                "provider_config": r.provider_config,
                "description": r.description,
                "auto_validate": r.auto_validate,
            }
            for r in template.evidence_requirements
        ],
        form_fields=template.form_fields,
        claim_collection_rules=template.claim_collection_rules,
        approval_strategy=template.approval_strategy.value if hasattr(template.approval_strategy, "value") else str(template.approval_strategy),
        application_validity_days=template.application_validity_days,
        notifications=template.notifications,
        ui_config=template.ui_config,
        metadata=template.metadata,
        created_at=template.created_at,
        updated_at=template.updated_at,
        version=template.version,
    )


# =========================================================
# Verification Session Router
# =========================================================

verification_session_router = APIRouter(
    prefix="/v1/identity/verification-sessions",
    tags=["Verification Sessions"],
    responses={404: {"model": ErrorResponse}},
)


@verification_session_router.post(
    "",
    response_model=VerificationSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Verification Session",
)
async def create_verification_session(
    data: VerificationSessionCreate,
    service=Depends(get_verification_session_service),
) -> VerificationSessionResponse:
    """Create a new Verification Session in PENDING state."""
    try:
        session = await service.create(**data.model_dump())
        return _verification_session_to_response(session)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@verification_session_router.get(
    "",
    response_model=list[VerificationSessionResponse],
    summary="List Verification Sessions",
)
async def list_verification_sessions(
    flow_id: str | None = None,
    filter_status: str | None = Query(default=None, alias="status"),
    skip: int = 0,
    limit: int = 100,
    service=Depends(get_verification_session_service),
) -> list[VerificationSessionResponse]:
    """List Verification Sessions filtered by flow_id or status."""
    try:
        if flow_id:
            sessions = await service.list_by_flow(flow_id, skip=skip, limit=limit)
        elif filter_status:
            sessions = await service.list_by_status(filter_status, skip=skip, limit=limit)
        else:
            sessions = []
        return [_verification_session_to_response(s) for s in sessions]
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@verification_session_router.get(
    "/{session_id}",
    response_model=VerificationSessionResponse,
    summary="Get Verification Session",
)
async def get_verification_session(
    session_id: str,
    service=Depends(get_verification_session_service),
) -> VerificationSessionResponse:
    """Get a Verification Session by ID."""
    session = await service.get(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification session not found")
    return _verification_session_to_response(session)


@verification_session_router.patch(
    "/{session_id}",
    response_model=VerificationSessionResponse,
    summary="Update Verification Session",
)
async def update_verification_session(
    session_id: str,
    data: VerificationSessionUpdate,
    service=Depends(get_verification_session_service),
) -> VerificationSessionResponse:
    """Update a Verification Session (status transitions, result, holder_id)."""
    try:
        session = await service.update(session_id, **data.model_dump(exclude_unset=True))
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification session not found")
        return _verification_session_to_response(session)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@verification_session_router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Verification Session",
)
async def delete_verification_session(
    session_id: str,
    service=Depends(get_verification_session_service),
) -> None:
    """Delete a Verification Session."""
    deleted = await service.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Verification session not found")


def _verification_session_to_response(session) -> VerificationSessionResponse:
    """Convert entity to response schema."""
    return VerificationSessionResponse(
        id=session.id,
        flow_id=session.flow_id,
        presentation_policy_id=session.presentation_policy_id,
        flow_instance_id=session.flow_instance_id,
        deployment_profile_id=session.deployment_profile_id,
        verifier_nonce=session.verifier_nonce,
        holder_id=session.holder_id,
        status=session.status,
        result=session.result,
        expires_at=session.expires_at,
        completed_at=session.completed_at,
        error=session.error,
        created_at=session.created_at,
        updated_at=session.updated_at,
        version=session.version,
    )


# =========================================================
# Compliance Profile Router
# =========================================================

compliance_profile_router = APIRouter(
    prefix="/v1/identity/compliance-profiles",
    tags=["Compliance Profiles"],
    responses={404: {"model": ErrorResponse}},
)


@compliance_profile_router.post(
    "",
    response_model=ComplianceProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Compliance Profile",
)
async def create_compliance_profile(
    data: ComplianceProfileCreate,
    service=Depends(get_compliance_profile_service),
) -> ComplianceProfileResponse:
    """Create a custom (non-system) Compliance Profile."""
    try:
        profile = await service.create(**data.model_dump())
        return _compliance_profile_to_response(profile)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@compliance_profile_router.get(
    "",
    response_model=list[ComplianceProfileResponse],
    summary="List Compliance Profiles",
)
async def list_compliance_profiles(
    skip: int = 0,
    limit: int = 100,
    organization_id: str | None = None,
    is_system: bool | None = None,
    discoverable_only: bool = False,
    service=Depends(get_compliance_profile_service),
) -> list[ComplianceProfileResponse]:
    """List Compliance Profiles (system presets and custom)."""
    profiles = await service.list(
        skip=skip,
        limit=limit,
        organization_id=organization_id,
        is_system=is_system,
        discoverable_only=discoverable_only,
    )
    return [_compliance_profile_to_response(p) for p in profiles]


@compliance_profile_router.get(
    "/{profile_id}",
    response_model=ComplianceProfileResponse,
    summary="Get Compliance Profile",
)
async def get_compliance_profile(
    profile_id: str,
    service=Depends(get_compliance_profile_service),
) -> ComplianceProfileResponse:
    """Get a Compliance Profile by ID."""
    profile = await service.get(profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compliance profile not found")
    return _compliance_profile_to_response(profile)


@compliance_profile_router.patch(
    "/{profile_id}",
    response_model=ComplianceProfileResponse,
    summary="Update Compliance Profile",
)
async def update_compliance_profile(
    profile_id: str,
    data: ComplianceProfileUpdate,
    service=Depends(get_compliance_profile_service),
) -> ComplianceProfileResponse:
    """Update a custom Compliance Profile (system profiles are immutable)."""
    try:
        profile = await service.update(profile_id, **data.model_dump(exclude_unset=True))
        if not profile:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compliance profile not found")
        return _compliance_profile_to_response(profile)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@compliance_profile_router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Compliance Profile",
)
async def delete_compliance_profile(
    profile_id: str,
    service=Depends(get_compliance_profile_service),
) -> None:
    """Delete a custom Compliance Profile."""
    try:
        deleted = await service.delete(profile_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compliance profile not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _compliance_profile_to_response(profile) -> ComplianceProfileResponse:
    """Convert entity to response schema."""
    return ComplianceProfileResponse(
        id=profile.id,
        name=profile.name,
        compliance_code=profile.compliance_code,
        credential_format=profile.credential_format.value if hasattr(profile.credential_format, "value") else str(profile.credential_format),
        organization_id=profile.organization_id,
        description=profile.description,
        issuance_protocol=profile.issuance_protocol,
        trust_profile_constraints=profile.trust_profile_constraints,
        is_system=profile.is_system,
        discoverable=profile.discoverable,
        metadata=profile.metadata,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        version=profile.version,
    )


# =========================================================
# Trust Framework Router
# =========================================================

trust_framework_router = APIRouter(
    prefix="/v1/identity/trust-frameworks",
    tags=["trust-frameworks"],
)


@trust_framework_router.post("", response_model=TrustFrameworkResponse, status_code=status.HTTP_201_CREATED)
async def create_trust_framework(
    data: TrustFrameworkCreate,
    service=Depends(get_trust_framework_service),
):
    """Create a new Trust Framework."""
    try:
        framework = await service.create(**data.model_dump(exclude_none=True))
        return _trust_framework_to_response(framework)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@trust_framework_router.get("", response_model=list[TrustFrameworkResponse])
async def list_trust_frameworks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    service=Depends(get_trust_framework_service),
):
    """List all Trust Frameworks."""
    frameworks = await service.list(skip=skip, limit=limit)
    return [_trust_framework_to_response(f) for f in frameworks]


@trust_framework_router.get("/{framework_id}", response_model=TrustFrameworkResponse)
async def get_trust_framework(
    framework_id: str,
    service=Depends(get_trust_framework_service),
):
    """Get a Trust Framework by ID."""
    framework = await service.get(framework_id)
    if not framework:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust Framework not found")
    return _trust_framework_to_response(framework)


@trust_framework_router.patch("/{framework_id}", response_model=TrustFrameworkResponse)
async def update_trust_framework(
    framework_id: str,
    data: TrustFrameworkUpdate,
    service=Depends(get_trust_framework_service),
):
    """Update a Trust Framework."""
    try:
        framework = await service.update(framework_id, **data.model_dump(exclude_none=True))
        if not framework:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust Framework not found")
        return _trust_framework_to_response(framework)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@trust_framework_router.delete("/{framework_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trust_framework(
    framework_id: str,
    service=Depends(get_trust_framework_service),
):
    """Delete a Trust Framework."""
    try:
        deleted = await service.delete(framework_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust Framework not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


def _trust_framework_to_response(framework) -> TrustFrameworkResponse:
    """Convert entity to response schema."""
    return TrustFrameworkResponse(
        id=framework.id,
        code=framework.code,
        display_name=framework.display_name,
        description=framework.description,
        pkd_endpoints=framework.pkd_endpoints,
        default_algorithms=[a.value if hasattr(a, "value") else str(a) for a in framework.default_algorithms],
        default_formats=[f.value if hasattr(f, "value") else str(f) for f in framework.default_formats],
        validation_ruleset=framework.validation_ruleset,
        sync_config=framework.sync_config,
        is_system=framework.is_system,
        created_at=framework.created_at,
        updated_at=framework.updated_at,
    )


# =========================================================
# Organization Trust Profile Router
# =========================================================

org_trust_profile_router = APIRouter(
    prefix="/v1/identity/organization-trust-profiles",
    tags=["organization-trust-profiles"],
)


@org_trust_profile_router.post("", response_model=OrganizationTrustProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_org_trust_profile(
    data: OrganizationTrustProfileCreate,
    service=Depends(get_organization_trust_profile_service),
):
    """Create a new Organization Trust Profile."""
    profile = await service.create(**data.model_dump(exclude_none=True))
    return _org_trust_profile_to_response(profile)


@org_trust_profile_router.get("", response_model=list[OrganizationTrustProfileResponse])
async def list_org_trust_profiles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    organization_id: str | None = Query(None),
    framework_id: str | None = Query(None),
    service=Depends(get_organization_trust_profile_service),
):
    """List Organization Trust Profiles."""
    profiles = await service.list(
        skip=skip,
        limit=limit,
        organization_id=organization_id,
        framework_id=framework_id,
    )
    return [_org_trust_profile_to_response(p) for p in profiles]


@org_trust_profile_router.get("/{profile_id}", response_model=OrganizationTrustProfileResponse)
async def get_org_trust_profile(
    profile_id: str,
    service=Depends(get_organization_trust_profile_service),
):
    """Get an Organization Trust Profile by ID."""
    profile = await service.get(profile_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization Trust Profile not found")
    return _org_trust_profile_to_response(profile)


@org_trust_profile_router.patch("/{profile_id}", response_model=OrganizationTrustProfileResponse)
async def update_org_trust_profile(
    profile_id: str,
    data: OrganizationTrustProfileUpdate,
    service=Depends(get_organization_trust_profile_service),
):
    """Update an Organization Trust Profile."""
    profile = await service.update(profile_id, **data.model_dump(exclude_none=True))
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization Trust Profile not found")
    return _org_trust_profile_to_response(profile)


@org_trust_profile_router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org_trust_profile(
    profile_id: str,
    service=Depends(get_organization_trust_profile_service),
):
    """Delete an Organization Trust Profile."""
    deleted = await service.delete(profile_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization Trust Profile not found")


def _org_trust_profile_to_response(profile) -> OrganizationTrustProfileResponse:
    """Convert entity to response schema."""
    from dataclasses import asdict
    return OrganizationTrustProfileResponse(
        id=profile.id,
        organization_id=profile.organization_id,
        framework_id=profile.framework_id,
        name=profile.name,
        display_name=profile.display_name,
        description=profile.description,
        enabled=profile.enabled,
        use_case_tags=profile.use_case_tags,
        compliance_status=profile.compliance_status,
        auto_generated=profile.auto_generated,
        revocation_policy=asdict(profile.revocation_policy) if profile.revocation_policy else None,
        time_policy=asdict(profile.time_policy) if profile.time_policy else None,
        allowed_algorithms=[a.value if hasattr(a, "value") else str(a) for a in profile.allowed_algorithms] if profile.allowed_algorithms is not None else None,
        allowed_formats=[f.value if hasattr(f, "value") else str(f) for f in profile.allowed_formats] if profile.allowed_formats is not None else None,
        allowed_issuers=profile.allowed_issuers,
        denied_issuers=profile.denied_issuers,
        jurisdiction_filter=profile.jurisdiction_filter,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        version=profile.version,
    )


# =========================================================
# Organization Router
# =========================================================

organization_router = APIRouter(
    prefix="/v1/identity/organizations",
    tags=["organizations"],
)


@organization_router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    data: OrganizationCreate,
    service=Depends(get_organization_service),
):
    """Create a new Organization."""
    try:
        org = await service.create(**data.model_dump(exclude_none=True))
        return _organization_to_response(org)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@organization_router.get("", response_model=list[OrganizationResponse])
async def list_organizations(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status_filter: str | None = Query(None, alias="status"),
    visibility: str | None = Query(None),
    service=Depends(get_organization_service),
):
    """List Organizations."""
    orgs = await service.list(skip=skip, limit=limit, status=status_filter, visibility=visibility)
    return [_organization_to_response(o) for o in orgs]


@organization_router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: str,
    service=Depends(get_organization_service),
):
    """Get an Organization by ID."""
    org = await service.get(org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return _organization_to_response(org)


@organization_router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: str,
    data: OrganizationUpdate,
    service=Depends(get_organization_service),
):
    """Update an Organization."""
    try:
        org = await service.update(org_id, **data.model_dump(exclude_none=True))
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
        return _organization_to_response(org)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@organization_router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    org_id: str,
    service=Depends(get_organization_service),
):
    """Soft-delete an Organization."""
    deleted = await service.delete(org_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")


def _organization_to_response(org) -> OrganizationResponse:
    """Convert entity to response schema."""
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        display_name=org.display_name,
        description=org.description,
        visibility=org.visibility,
        owner_id=org.owner_id,
        join_code=org.join_code,
        status=org.status,
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


# =========================================================
# Webhook Router
# =========================================================

webhook_router = APIRouter(
    prefix="/v1/identity/webhooks",
    tags=["webhooks"],
)


@webhook_router.post("", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    data: WebhookCreate,
    service=Depends(get_webhook_service),
):
    """Create a new Webhook."""
    webhook = await service.create(**data.model_dump(exclude_none=True))
    return _webhook_to_response(webhook)


@webhook_router.get("", response_model=list[WebhookResponse])
async def list_webhooks(
    organization_id: str = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    enabled: bool | None = Query(None),
    service=Depends(get_webhook_service),
):
    """List Webhooks for an organization."""
    items = await service.list(organization_id=organization_id, skip=skip, limit=limit, enabled=enabled)
    return [_webhook_to_response(w) for w in items]


@webhook_router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook_id: str,
    service=Depends(get_webhook_service),
):
    """Get a Webhook by ID."""
    webhook = await service.get(webhook_id)
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return _webhook_to_response(webhook)


@webhook_router.patch("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: str,
    data: WebhookUpdate,
    service=Depends(get_webhook_service),
):
    """Update a Webhook."""
    webhook = await service.update(webhook_id, **data.model_dump(exclude_none=True))
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return _webhook_to_response(webhook)


@webhook_router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: str,
    service=Depends(get_webhook_service),
):
    """Delete a Webhook."""
    deleted = await service.delete(webhook_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")


def _webhook_to_response(webhook) -> WebhookResponse:
    """Convert entity to response schema."""
    return WebhookResponse(
        id=webhook.id,
        organization_id=webhook.organization_id,
        name=webhook.name,
        description=webhook.description,
        endpoint_url=webhook.endpoint_url,
        events=webhook.events,
        signing_secret_masked=webhook.signing_secret_masked,
        enabled=webhook.enabled,
        api_version=webhook.api_version,
        filter=webhook.filter,
        delivery_config=webhook.delivery_config,
        status=webhook.status,
        failure_count=webhook.failure_count,
        last_triggered_at=webhook.last_triggered_at,
        last_success_at=webhook.last_success_at,
        created_at=webhook.created_at,
        updated_at=webhook.updated_at,
    )


# =========================================================
# Subscription Router
# =========================================================

subscription_router = APIRouter(
    prefix="/v1/identity/subscriptions",
    tags=["subscriptions"],
)


@subscription_router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    data: SubscriptionCreate,
    service=Depends(get_subscription_service),
):
    """Create a new Subscription."""
    sub = await service.create(**data.model_dump(exclude_none=True))
    return _subscription_to_response(sub)


@subscription_router.get("", response_model=list[SubscriptionResponse])
async def list_subscriptions(
    organization_id: str = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    enabled: bool | None = Query(None),
    service=Depends(get_subscription_service),
):
    """List Subscriptions for an organization."""
    items = await service.list(organization_id=organization_id, skip=skip, limit=limit, enabled=enabled)
    return [_subscription_to_response(s) for s in items]


@subscription_router.get("/{sub_id}", response_model=SubscriptionResponse)
async def get_subscription(
    sub_id: str,
    service=Depends(get_subscription_service),
):
    """Get a Subscription by ID."""
    sub = await service.get(sub_id)
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    return _subscription_to_response(sub)


@subscription_router.patch("/{sub_id}", response_model=SubscriptionResponse)
async def update_subscription(
    sub_id: str,
    data: SubscriptionUpdate,
    service=Depends(get_subscription_service),
):
    """Update a Subscription."""
    sub = await service.update(sub_id, **data.model_dump(exclude_none=True))
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    return _subscription_to_response(sub)


@subscription_router.delete("/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    sub_id: str,
    service=Depends(get_subscription_service),
):
    """Delete a Subscription."""
    deleted = await service.delete(sub_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")


def _subscription_to_response(sub) -> SubscriptionResponse:
    """Convert entity to response schema."""
    return SubscriptionResponse(
        id=sub.id,
        organization_id=sub.organization_id,
        name=sub.name,
        description=sub.description,
        event_types=sub.event_types,
        delivery=sub.delivery,
        filter=sub.filter,
        enabled=sub.enabled,
        retry_policy=sub.retry_policy,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


# =========================================================
# API Key Router
# =========================================================

api_key_router = APIRouter(
    prefix="/v1/identity/api-keys",
    tags=["api-keys"],
)


@api_key_router.post("", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: ApiKeyCreate,
    service=Depends(get_api_key_service),
):
    """Create a new API Key."""
    try:
        key = await service.create(**data.model_dump(exclude_none=True))
        return _api_key_to_response(key)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@api_key_router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    organization_id: str = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    enabled: bool | None = Query(None),
    scope_type: str | None = Query(None),
    service=Depends(get_api_key_service),
):
    """List API Keys for an organization."""
    items = await service.list(
        organization_id=organization_id, skip=skip, limit=limit,
        enabled=enabled, scope_type=scope_type,
    )
    return [_api_key_to_response(k) for k in items]


@api_key_router.get("/{key_id}", response_model=ApiKeyResponse)
async def get_api_key(
    key_id: str,
    service=Depends(get_api_key_service),
):
    """Get an API Key by ID."""
    key = await service.get(key_id)
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key not found")
    return _api_key_to_response(key)


@api_key_router.patch("/{key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    key_id: str,
    data: ApiKeyUpdate,
    service=Depends(get_api_key_service),
):
    """Update an API Key."""
    try:
        key = await service.update(key_id, **data.model_dump(exclude_none=True))
        if not key:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key not found")
        return _api_key_to_response(key)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@api_key_router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: str,
    service=Depends(get_api_key_service),
):
    """Delete an API Key."""
    deleted = await service.delete(key_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key not found")


def _api_key_to_response(key) -> ApiKeyResponse:
    """Convert entity to response schema."""
    return ApiKeyResponse(
        id=key.id,
        organization_id=key.organization_id,
        name=key.name,
        description=key.description,
        key_prefix=key.key_prefix,
        scope_type=key.scope_type,
        deployment_profile_id=key.deployment_profile_id,
        scopes=key.scopes,
        enabled=key.enabled,
        expires_at=key.expires_at,
        last_used_at=key.last_used_at,
        created_at=key.created_at,
        updated_at=key.updated_at,
    )


# =========================================================
# Issuance Record Router
# =========================================================

issuance_record_router = APIRouter(
    prefix="/v1/identity/issuance-records",
    tags=["issuance-records"],
)


@issuance_record_router.post("", response_model=IssuanceRecordResponse, status_code=status.HTTP_201_CREATED)
async def create_issuance_record(data: IssuanceRecordCreate, service=Depends(get_issuance_record_service)):
    try:
        entity = await service.create(**data.model_dump(exclude_none=True))
        return _issuance_record_to_response(entity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@issuance_record_router.get("", response_model=list[IssuanceRecordResponse])
async def list_issuance_records(
    flow_id: str | None = Query(None),
    holder_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    service=Depends(get_issuance_record_service),
):
    items = await service.list(flow_id=flow_id, holder_id=holder_id, status=status_filter, skip=skip, limit=limit)
    return [_issuance_record_to_response(i) for i in items]


@issuance_record_router.get("/{record_id}", response_model=IssuanceRecordResponse)
async def get_issuance_record(record_id: str, service=Depends(get_issuance_record_service)):
    entity = await service.get(record_id)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issuance record not found")
    return _issuance_record_to_response(entity)


@issuance_record_router.patch("/{record_id}", response_model=IssuanceRecordResponse)
async def update_issuance_record(record_id: str, data: IssuanceRecordUpdate, service=Depends(get_issuance_record_service)):
    try:
        entity = await service.update(record_id, **data.model_dump(exclude_unset=True))
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issuance record not found")
        return _issuance_record_to_response(entity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@issuance_record_router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_issuance_record(record_id: str, service=Depends(get_issuance_record_service)):
    deleted = await service.delete(record_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issuance record not found")


def _issuance_record_to_response(entity) -> IssuanceRecordResponse:
    return IssuanceRecordResponse(
        id=entity.id, flow_id=entity.flow_id, flow_execution_id=entity.flow_execution_id,
        application_id=entity.application_id, credential_template_id=entity.credential_template_id,
        holder_id=entity.holder_id, credential_id=entity.credential_id,
        credential_format=entity.credential_format, offer_uri=entity.offer_uri,
        offer_expires_at=entity.offer_expires_at, status=entity.status,
        revocation_index=entity.revocation_index, valid_from=entity.valid_from,
        valid_until=entity.valid_until, created_at=entity.created_at, claimed_at=entity.claimed_at,
    )


# =========================================================
# Policy Set Router
# =========================================================

policy_set_router = APIRouter(
    prefix="/v1/identity/policy-sets",
    tags=["policy-sets"],
)


@policy_set_router.post("", response_model=PolicySetResponse, status_code=status.HTTP_201_CREATED)
async def create_policy_set(data: PolicySetCreate, service=Depends(get_policy_set_service)):
    try:
        entity = await service.create(**data.model_dump(exclude_none=True))
        return _policy_set_to_response(entity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@policy_set_router.get("", response_model=list[PolicySetResponse])
async def list_policy_sets(
    organization_id: str = Query(...),
    policy_type: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    service=Depends(get_policy_set_service),
):
    items = await service.list(organization_id=organization_id, policy_type=policy_type, status=status_filter, skip=skip, limit=limit)
    return [_policy_set_to_response(i) for i in items]


@policy_set_router.get("/{policy_set_id}", response_model=PolicySetResponse)
async def get_policy_set(policy_set_id: str, service=Depends(get_policy_set_service)):
    entity = await service.get(policy_set_id)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy set not found")
    return _policy_set_to_response(entity)


@policy_set_router.patch("/{policy_set_id}", response_model=PolicySetResponse)
async def update_policy_set(policy_set_id: str, data: PolicySetUpdate, service=Depends(get_policy_set_service)):
    try:
        entity = await service.update(policy_set_id, **data.model_dump(exclude_unset=True))
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy set not found")
        return _policy_set_to_response(entity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@policy_set_router.delete("/{policy_set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy_set(policy_set_id: str, service=Depends(get_policy_set_service)):
    deleted = await service.delete(policy_set_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy set not found")


def _policy_set_to_response(entity) -> PolicySetResponse:
    return PolicySetResponse(
        id=entity.id, organization_id=entity.organization_id, name=entity.name,
        description=entity.description, policy_type=entity.policy_type,
        cedar_policies=entity.cedar_policies or [], cedar_schema_version=entity.cedar_schema_version,
        status=entity.status, created_at=entity.created_at, updated_at=entity.updated_at,
    )


# =========================================================
# Wallet Profile Router
# =========================================================

wallet_profile_router = APIRouter(
    prefix="/v1/identity/wallet-profiles",
    tags=["wallet-profiles"],
)


@wallet_profile_router.post("", response_model=WalletProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_wallet_profile(data: WalletProfileCreate, service=Depends(get_wallet_profile_service)):
    try:
        entity = await service.create(**data.model_dump(exclude_none=True))
        return _wallet_profile_to_response(entity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@wallet_profile_router.get("", response_model=list[WalletProfileResponse])
async def list_wallet_profiles(
    organization_id: str | None = Query(None),
    credential_format: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    service=Depends(get_wallet_profile_service),
):
    items = await service.list(organization_id=organization_id, credential_format=credential_format, skip=skip, limit=limit)
    return [_wallet_profile_to_response(i) for i in items]


@wallet_profile_router.get("/{profile_id}", response_model=WalletProfileResponse)
async def get_wallet_profile(profile_id: str, service=Depends(get_wallet_profile_service)):
    entity = await service.get(profile_id)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet profile not found")
    return _wallet_profile_to_response(entity)


@wallet_profile_router.patch("/{profile_id}", response_model=WalletProfileResponse)
async def update_wallet_profile(profile_id: str, data: WalletProfileUpdate, service=Depends(get_wallet_profile_service)):
    try:
        entity = await service.update(profile_id, **data.model_dump(exclude_unset=True))
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet profile not found")
        return _wallet_profile_to_response(entity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@wallet_profile_router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wallet_profile(profile_id: str, service=Depends(get_wallet_profile_service)):
    deleted = await service.delete(profile_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet profile not found")


def _wallet_profile_to_response(entity) -> WalletProfileResponse:
    return WalletProfileResponse(
        id=entity.id, organization_id=entity.organization_id,
        is_override=entity.is_override, override_precedence=entity.override_precedence,
        name=entity.name, description=entity.description,
        credential_format=entity.credential_format, issuance_protocol=entity.issuance_protocol,
        compliance_profile_code=entity.compliance_profile_code, wallet_apps=entity.wallet_apps,
        merge_strategy=entity.merge_strategy, specifications=entity.specifications,
        supported_platforms=entity.supported_platforms, deep_link_pattern=entity.deep_link_pattern,
        created_at=entity.created_at, updated_at=entity.updated_at,
    )


# =========================================================
# Device Registration Router
# =========================================================

device_registration_router = APIRouter(
    prefix="/v1/identity/device-registrations",
    tags=["device-registrations"],
)


@device_registration_router.post("", response_model=DeviceRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def create_device_registration(data: DeviceRegistrationCreate, service=Depends(get_device_registration_service)):
    try:
        entity = await service.create(**data.model_dump(exclude_none=True))
        return _device_registration_to_response(entity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@device_registration_router.get("", response_model=list[DeviceRegistrationResponse])
async def list_device_registrations(
    user_id: str = Query(...),
    is_active: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    service=Depends(get_device_registration_service),
):
    items = await service.list(user_id=user_id, is_active=is_active, skip=skip, limit=limit)
    return [_device_registration_to_response(i) for i in items]


@device_registration_router.get("/{registration_id}", response_model=DeviceRegistrationResponse)
async def get_device_registration(registration_id: str, service=Depends(get_device_registration_service)):
    entity = await service.get(registration_id)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device registration not found")
    return _device_registration_to_response(entity)


@device_registration_router.patch("/{registration_id}", response_model=DeviceRegistrationResponse)
async def update_device_registration(registration_id: str, data: DeviceRegistrationUpdate, service=Depends(get_device_registration_service)):
    try:
        entity = await service.update(registration_id, **data.model_dump(exclude_unset=True))
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device registration not found")
        return _device_registration_to_response(entity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@device_registration_router.delete("/{registration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device_registration(registration_id: str, service=Depends(get_device_registration_service)):
    deleted = await service.delete(registration_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device registration not found")


def _device_registration_to_response(entity) -> DeviceRegistrationResponse:
    return DeviceRegistrationResponse(
        id=entity.id, user_id=entity.user_id, organization_id=entity.organization_id,
        device_id=entity.device_id, platform=entity.platform, fcm_token=entity.fcm_token,
        app_version=entity.app_version, os_version=entity.os_version,
        device_model=entity.device_model, preferences=entity.preferences,
        public_key_der=entity.public_key_der, public_key_kid=entity.public_key_kid,
        key_valid_from=entity.key_valid_from, key_valid_until=entity.key_valid_until,
        is_active=entity.is_active, created_at=entity.created_at,
        updated_at=entity.updated_at, last_seen_at=entity.last_seen_at,
    )


# =========================================================
# Applicant Router
# =========================================================

applicant_router = APIRouter(
    prefix="/v1/identity/applicants",
    tags=["applicants"],
)


@applicant_router.post("", response_model=ApplicantResponse, status_code=status.HTTP_201_CREATED)
async def create_applicant(data: ApplicantCreate, service=Depends(get_applicant_service)):
    try:
        entity = await service.create(**data.model_dump(exclude_none=True))
        return _applicant_to_response(entity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@applicant_router.get("", response_model=list[ApplicantResponse])
async def list_applicants(
    organization_id: str = Query(...),
    flow_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    service=Depends(get_applicant_service),
):
    items = await service.list(organization_id=organization_id, flow_id=flow_id, status=status_filter, skip=skip, limit=limit)
    return [_applicant_to_response(i) for i in items]


@applicant_router.get("/{applicant_id}", response_model=ApplicantResponse)
async def get_applicant(applicant_id: str, service=Depends(get_applicant_service)):
    entity = await service.get(applicant_id)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Applicant not found")
    return _applicant_to_response(entity)


@applicant_router.patch("/{applicant_id}", response_model=ApplicantResponse)
async def update_applicant(applicant_id: str, data: ApplicantUpdate, service=Depends(get_applicant_service)):
    try:
        entity = await service.update(applicant_id, **data.model_dump(exclude_unset=True))
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Applicant not found")
        return _applicant_to_response(entity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@applicant_router.delete("/{applicant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_applicant(applicant_id: str, service=Depends(get_applicant_service)):
    deleted = await service.delete(applicant_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Applicant not found")


def _applicant_to_response(entity) -> ApplicantResponse:
    return ApplicantResponse(
        id=entity.id, organization_id=entity.organization_id, flow_id=entity.flow_id,
        credential_template_id=entity.credential_template_id, user_id=entity.user_id,
        external_id=entity.external_id, given_name=entity.given_name,
        family_name=entity.family_name, email=entity.email, phone=entity.phone,
        status=entity.status, reviewer_id=entity.reviewer_id,
        reviewer_lock_expires_at=entity.reviewer_lock_expires_at,
        submitted_at=entity.submitted_at, reviewed_at=entity.reviewed_at,
        approved_at=entity.approved_at, credentialed_at=entity.credentialed_at,
        rejection_reason=entity.rejection_reason, rejection_code=entity.rejection_code,
        application_data=entity.application_data, vetting_checks=entity.vetting_checks,
        issued_credential_id=entity.issued_credential_id, metadata=entity.metadata,
        created_at=entity.created_at, updated_at=entity.updated_at,
    )


# =========================================================
# Reviewer Lock Router
# =========================================================

reviewer_lock_router = APIRouter(
    prefix="/v1/identity/reviewer-locks",
    tags=["reviewer-locks"],
)


@reviewer_lock_router.post("", response_model=ReviewerLockResponse, status_code=status.HTTP_201_CREATED)
async def acquire_reviewer_lock(data: ReviewerLockCreate, service=Depends(get_reviewer_lock_service)):
    try:
        entity = await service.acquire(
            applicant_id=data.applicant_id,
            organization_id=data.organization_id,
            holder_user_id=data.holder_user_id,
            ttl_seconds=data.ttl_seconds,
        )
        return _reviewer_lock_to_response(entity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@reviewer_lock_router.get("/{lock_id}", response_model=ReviewerLockResponse)
async def get_reviewer_lock(lock_id: str, service=Depends(get_reviewer_lock_service)):
    entity = await service.get(lock_id)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reviewer lock not found")
    return _reviewer_lock_to_response(entity)


@reviewer_lock_router.post("/{lock_id}/release", status_code=status.HTTP_204_NO_CONTENT)
async def release_reviewer_lock(lock_id: str, service=Depends(get_reviewer_lock_service)):
    released = await service.release(lock_id)
    if not released:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reviewer lock not found")


@reviewer_lock_router.delete("/{lock_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reviewer_lock(lock_id: str, service=Depends(get_reviewer_lock_service)):
    deleted = await service.delete(lock_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reviewer lock not found")


def _reviewer_lock_to_response(entity) -> ReviewerLockResponse:
    return ReviewerLockResponse(
        id=entity.id, applicant_id=entity.applicant_id,
        organization_id=entity.organization_id, holder_user_id=entity.holder_user_id,
        ttl_seconds=entity.ttl_seconds, expires_at=entity.expires_at,
        released_at=entity.released_at, status=entity.status,
        created_at=entity.created_at,
    )


# =========================================================
# Vetting Check Router
# =========================================================

vetting_check_router = APIRouter(
    prefix="/v1/identity/vetting-checks",
    tags=["vetting-checks"],
)


@vetting_check_router.post("", response_model=VettingCheckResponse, status_code=status.HTTP_201_CREATED)
async def create_vetting_check(data: VettingCheckCreate, service=Depends(get_vetting_check_service)):
    try:
        entity = await service.create(**data.model_dump(exclude_none=True))
        return _vetting_check_to_response(entity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@vetting_check_router.get("", response_model=list[VettingCheckResponse])
async def list_vetting_checks(
    applicant_id: str = Query(...),
    status_filter: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    service=Depends(get_vetting_check_service),
):
    items = await service.list(applicant_id=applicant_id, status=status_filter, skip=skip, limit=limit)
    return [_vetting_check_to_response(i) for i in items]


@vetting_check_router.get("/{check_id}", response_model=VettingCheckResponse)
async def get_vetting_check(check_id: str, service=Depends(get_vetting_check_service)):
    entity = await service.get(check_id)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vetting check not found")
    return _vetting_check_to_response(entity)


@vetting_check_router.patch("/{check_id}", response_model=VettingCheckResponse)
async def update_vetting_check(check_id: str, data: VettingCheckUpdate, service=Depends(get_vetting_check_service)):
    try:
        entity = await service.update(check_id, **data.model_dump(exclude_unset=True))
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vetting check not found")
        return _vetting_check_to_response(entity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@vetting_check_router.delete("/{check_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vetting_check(check_id: str, service=Depends(get_vetting_check_service)):
    deleted = await service.delete(check_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vetting check not found")


def _vetting_check_to_response(entity) -> VettingCheckResponse:
    return VettingCheckResponse(
        id=entity.id, applicant_id=entity.applicant_id,
        organization_id=entity.organization_id, check_type=entity.check_type,
        provider=entity.provider, provider_reference_id=entity.provider_reference_id,
        status=entity.status, score=entity.score, threshold=entity.threshold,
        failure_reason=entity.failure_reason, evidence_refs=entity.evidence_refs,
        performed_by=entity.performed_by, started_at=entity.started_at,
        completed_at=entity.completed_at, expires_at=entity.expires_at,
        raw_result=entity.raw_result, created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


# =========================================================
# Biometric Enrollment Router
# =========================================================

biometric_enrollment_router = APIRouter(
    prefix="/v1/identity/biometric-enrollments",
    tags=["biometric-enrollments"],
)


@biometric_enrollment_router.post("", response_model=BiometricEnrollmentResponse, status_code=status.HTTP_201_CREATED)
async def create_biometric_enrollment(data: BiometricEnrollmentCreate, service=Depends(get_biometric_enrollment_service)):
    try:
        entity = await service.create(**data.model_dump(exclude_none=True))
        return _biometric_enrollment_to_response(entity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@biometric_enrollment_router.get("", response_model=list[BiometricEnrollmentResponse])
async def list_biometric_enrollments(
    applicant_id: str = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    service=Depends(get_biometric_enrollment_service),
):
    items = await service.list(applicant_id=applicant_id, skip=skip, limit=limit)
    return [_biometric_enrollment_to_response(i) for i in items]


@biometric_enrollment_router.get("/{enrollment_id}", response_model=BiometricEnrollmentResponse)
async def get_biometric_enrollment(enrollment_id: str, service=Depends(get_biometric_enrollment_service)):
    entity = await service.get(enrollment_id)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Biometric enrollment not found")
    return _biometric_enrollment_to_response(entity)


@biometric_enrollment_router.patch("/{enrollment_id}", response_model=BiometricEnrollmentResponse)
async def update_biometric_enrollment(enrollment_id: str, data: BiometricEnrollmentUpdate, service=Depends(get_biometric_enrollment_service)):
    try:
        entity = await service.update(enrollment_id, **data.model_dump(exclude_unset=True))
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Biometric enrollment not found")
        return _biometric_enrollment_to_response(entity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@biometric_enrollment_router.delete("/{enrollment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_biometric_enrollment(enrollment_id: str, service=Depends(get_biometric_enrollment_service)):
    deleted = await service.delete(enrollment_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Biometric enrollment not found")


def _biometric_enrollment_to_response(entity) -> BiometricEnrollmentResponse:
    return BiometricEnrollmentResponse(
        id=entity.id, applicant_id=entity.applicant_id,
        organization_id=entity.organization_id, modality=entity.modality,
        template_hash=entity.template_hash, hash_algorithm=entity.hash_algorithm,
        provider=entity.provider, capture_device=entity.capture_device,
        quality_score=entity.quality_score, liveness_verified=entity.liveness_verified,
        status=entity.status, revoked_at=entity.revoked_at,
        revocation_reason=entity.revocation_reason, created_at=entity.created_at,
    )


# =========================================================
# Notification Payload Router
# =========================================================

notification_payload_router = APIRouter(
    prefix="/v1/identity/notification-payloads",
    tags=["notification-payloads"],
)


@notification_payload_router.post("", response_model=NotificationPayloadResponse, status_code=status.HTTP_201_CREATED)
async def create_notification_payload(data: NotificationPayloadCreate, service=Depends(get_notification_payload_service)):
    try:
        entity = await service.create(
            event_type=data.event_type,
            subscription_id="",
            payload=data.model_dump(exclude_none=True),
            title=data.title,
            body=data.body,
            priority=data.priority,
            target=data.target.model_dump(exclude_none=True),
            data=data.data,
            ttl_seconds=data.ttl_seconds,
            collapse_key=data.collapse_key,
            correlation_id=data.correlation_id,
        )
        return _notification_payload_to_response(entity)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@notification_payload_router.get("", response_model=list[NotificationPayloadResponse])
async def list_notification_payloads(
    event_type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    service=Depends(get_notification_payload_service),
):
    items = await service.list(event_type=event_type, skip=skip, limit=limit)
    return [_notification_payload_to_response(i) for i in items]


@notification_payload_router.get("/{payload_id}", response_model=NotificationPayloadResponse)
async def get_notification_payload(payload_id: str, service=Depends(get_notification_payload_service)):
    entity = await service.get(payload_id)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification payload not found")
    return _notification_payload_to_response(entity)


@notification_payload_router.delete("/{payload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification_payload(payload_id: str, service=Depends(get_notification_payload_service)):
    deleted = await service.delete(payload_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification payload not found")


def _notification_payload_to_response(entity) -> NotificationPayloadResponse:
    target = entity.target if isinstance(entity.target, dict) else {}
    return NotificationPayloadResponse(
        id=entity.id, title=entity.title, body=entity.body,
        data=entity.data, event_type=entity.event_type, priority=entity.priority,
        target=target, ttl_seconds=entity.ttl_seconds,
        collapse_key=entity.collapse_key, correlation_id=entity.correlation_id,
        created_at=entity.created_at,
    )
