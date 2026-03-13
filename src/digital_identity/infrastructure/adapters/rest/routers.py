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
        organization_id=getattr(profile, 'organization_id', ''),
        name=profile.name,
        description=profile.description,
        profile_type=profile.profile_type.value,
        enabled=profile.enabled,
        trust_sources=profile.trust_sources,
        allowed_algorithms=[a.value for a in profile.allowed_algorithms],
        supported_formats=[f.value for f in profile.supported_formats],
        revocation_policy={
            "check_mode": profile.revocation_policy.mode.value,
            "check_ocsp": profile.revocation_policy.check_ocsp,
            "check_crl": profile.revocation_policy.check_crl,
            "check_status_list": profile.revocation_policy.check_status_list,
            "cache_ttl_seconds": int(profile.revocation_policy.cache_ttl.total_seconds()),
        },
        time_policy={
            "clock_skew_seconds": int(profile.time_policy.clock_skew_tolerance.total_seconds()),
            "max_credential_age_seconds": int(profile.time_policy.max_credential_age.total_seconds()) if profile.time_policy.max_credential_age else None,
            "require_freshness": False,
            "freshness_window_seconds": None,
        },
        revocation_profile_id=getattr(profile, 'revocation_profile_id', None),
        allowed_issuers=profile.allowed_issuers,
        denied_issuers=profile.denied_issuers,
        compliance_status=getattr(profile, 'compliance_status', 'SETUP_REQUIRED'),
        auto_generated=getattr(profile, 'auto_generated', False),
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


def _credential_template_to_response(template) -> CredentialTemplateResponse:
    """Convert entity to response schema."""
    return CredentialTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        credential_type=template.credential_type,
        schema_uri=template.schema_uri,
        claims=[
            {
                "name": c.name,
                "display_name": c.display_name,
                "data_type": c.data_type,
                "required": c.required,
                "selectively_disclosable": c.selectively_disclosable,
                "derived_from": c.derived_from,
                "predicate_type": c.predicate_type,
                "predicate_value": c.predicate_value,
            }
            for c in template.claims
        ],
        validity_rules={
            "default_ttl_days": template.validity_rules.default_ttl.days,
            "allow_reissue": template.validity_rules.allow_reissue,
        },
        issuer_key_ids=template.issuer_key_ids,
        trust_profile_id=template.trust_profile_id,
        format=template.format.value,
        namespace=template.namespace,
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
    return PresentationPolicyResponse(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        purpose=policy.purpose,
        accepted_credential_types=policy.accepted_credential_types,
        required_claims=[
            {
                "claim_name": c.claim_name,
                "credential_type": c.credential_type,
                "accept_predicate": c.accept_predicate,
                "required_value": c.required_value,
            }
            for c in policy.required_claims
        ],
        holder_binding=policy.holder_binding.value,
        trust_profile_id=policy.trust_profile_id,
        allowed_issuers=policy.allowed_issuers,
        freshness_requirements={
            "max_proof_age_seconds": policy.freshness_requirements.max_proof_age.total_seconds(),
            "require_live_revocation_check": policy.freshness_requirements.require_live_revocation_check,
        },
        prefer_predicates=policy.prefer_predicates,
        single_presentation=policy.single_presentation,
        derived_attribute_preferences=policy.derived_attribute_preferences,
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
            "show_operator_mode": profile.ux_config.show_operator_mode,
            "accessibility_enabled": profile.ux_config.accessibility_enabled,
            "signage_text": profile.ux_config.signage_text,
        },
        update_policy={
            "auto_update": profile.update_policy.auto_update,
            "update_channel": profile.update_policy.update_channel,
            "rollout_percentage": profile.update_policy.rollout_percentage,
            "rollout_ring": profile.update_policy.rollout_ring,
        },
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
        name=flow.name,
        description=flow.description,
        flow_type=flow.flow_type.value,
        trust_profile_id=flow.trust_profile_id,
        credential_template_id=flow.credential_template_id,
        presentation_policy_id=flow.presentation_policy_id,
        deployment_profile_ids=flow.deployment_profile_ids,
        approval_strategy=flow.approval_strategy.value,
        enabled=flow.enabled,
        hooks=flow.hooks,
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
