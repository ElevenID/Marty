"""
Onboarding API Router

Handles post-registration user onboarding:
- GET /api/onboarding/status - Check if user needs onboarding
- GET /api/onboarding/organizations - List discoverable vendor organizations
- POST /api/onboarding/join-with-code - Join organization using invite code
- POST /api/onboarding/request-membership - Request to join an organization
- POST /api/onboarding/complete - Complete onboarding with role/org selection
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from subscription.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMember,
    MembershipMode,
    MemberRole,
    MembershipRequestStatus,
)
from subscription.database import get_db_session
from .keycloak_admin import KeycloakAdminClient, get_keycloak_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


# =============================================================================
# Request/Response Models
# =============================================================================


class OnboardingStatusResponse(BaseModel):
    """Onboarding status response."""
    
    needs_onboarding: bool
    user_type: str | None = None
    organization_id: str | None = None
    organization_name: str | None = None
    completed_at: str | None = None
    pending_request: dict | None = None  # If user has a pending membership request


class OrganizationInfo(BaseModel):
    """Organization info for listing."""
    
    id: str
    name: str
    description: str | None = None
    member_count: int = 0
    membership_mode: str = "invite_only"  # invite_only, approval, open
    is_discoverable: bool = True


class OrganizationsListResponse(BaseModel):
    """List of available organizations."""
    
    organizations: list[OrganizationInfo]


class JoinWithCodeRequest(BaseModel):
    """Request to join organization with invite code."""
    
    invite_code: str = Field(..., description="The invitation code provided by the organization")


class JoinWithCodeResponse(BaseModel):
    """Response after joining with invite code."""
    
    success: bool
    organization_id: str | None = None
    organization_name: str | None = None
    message: str


class RequestMembershipRequest(BaseModel):
    """Request to join an organization that requires approval."""
    
    organization_id: str = Field(..., description="Organization ID to request membership for")
    message: str | None = Field(None, description="Optional message to include with request")


class RequestMembershipResponse(BaseModel):
    """Response after submitting membership request."""
    
    success: bool
    request_id: str | None = None
    organization_name: str | None = None
    message: str


class CompleteOnboardingRequest(BaseModel):
    """Request to complete onboarding."""
    
    user_type: str = Field(..., description="User type: 'applicant' or 'vendor'")
    organization_id: str | None = Field(
        None, 
        description="Organization ID to associate with (for applicants selecting open org)"
    )
    # Vendor new organization fields
    organization_name: str | None = Field(
        None,
        description="Name for new organization (required for vendors creating new org)"
    )
    organization_description: str | None = Field(
        None,
        description="Description for new organization"
    )
    # New organization settings (for vendors creating org)
    is_discoverable: bool = Field(
        False,
        description="Whether organization should appear in public listings"
    )
    membership_mode: Literal["invite_only", "approval", "open"] = Field(
        "invite_only",
        description="How users can join: invite_only, approval (request), or open"
    )
    # Explicit confirmation
    confirm_organization: bool = Field(
        False,
        description="User explicitly confirms they want to join this organization"
    )


class CompleteOnboardingResponse(BaseModel):
    """Response after completing onboarding."""
    
    success: bool
    user_type: str
    organization_id: str | None = None
    organization_name: str | None = None
    membership_status: str | None = None  # joined, pending_approval, none
    invite_code: str | None = None  # For vendors, their org's invite code
    message: str


# =============================================================================
# Organization Settings Storage (Database-backed)
# =============================================================================


async def get_org_settings(org_id: str, db: AsyncSession) -> dict:
    """Get organization settings from database."""
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        return {
            "is_discoverable": False,
            "membership_mode": "invite_only",
            "invite_code": None,
        }
    
    # Get the first active reusable invite code if any
    result = await db.execute(
        select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == org_id,
            OrganizationInvitation.is_reusable == True,
            OrganizationInvitation.is_active == True,
        ).limit(1)
    )
    invitation = result.scalar_one_or_none()
    
    return {
        "is_discoverable": org.is_discoverable,
        "membership_mode": org.membership_mode.value if org.membership_mode else "invite_only",
        "invite_code": invitation.code if invitation else None,
    }


async def set_org_settings(org_id: str, settings: dict, db: AsyncSession) -> None:
    """Update or create organization settings in database.
    
    If the organization doesn't exist (e.g., was just created in Keycloak),
    this will create a new Organization record in the local database.
    """
    import re
    
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        # Create new organization record in local database
        # This happens when org was just created in Keycloak
        org_name = settings.get("name", f"org-{org_id[:8]}")
        # Generate a slug from the name
        slug = re.sub(r'[^a-z0-9]+', '-', org_name.lower()).strip('-')
        # Ensure uniqueness by adding a suffix if needed
        slug = f"{slug}-{org_id[:8]}"
        
        org = Organization(
            id=org_id,
            name=org_name,
            slug=slug,
            is_active=True,
            is_discoverable=settings.get("is_discoverable", False),
            membership_mode=MembershipMode(settings.get("membership_mode", "invite_only")),
        )
        db.add(org)
        logger.info(f"Created local organization record: {org_id} ({org_name})")
    else:
        # Update existing organization
        if "is_discoverable" in settings:
            org.is_discoverable = settings["is_discoverable"]
        
        if "membership_mode" in settings:
            mode_value = settings["membership_mode"]
            if isinstance(mode_value, str):
                org.membership_mode = MembershipMode(mode_value)
            else:
                org.membership_mode = mode_value
    
    await db.commit()


async def generate_invite_code(org_id: str, db: AsyncSession, created_by: str | None = None) -> str:
    """Generate a new invite code for an organization."""
    # Deactivate any existing reusable codes
    result = await db.execute(
        select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == org_id,
            OrganizationInvitation.is_reusable == True,
            OrganizationInvitation.is_active == True,
        )
    )
    existing = result.scalars().all()
    for inv in existing:
        inv.is_active = False
    
    # Generate new code (8 characters, alphanumeric)
    new_code = secrets.token_urlsafe(6).upper()[:8]
    
    # Create new invitation
    invitation = OrganizationInvitation(
        id=str(uuid4()),
        organization_id=org_id,
        code=new_code,
        role=MemberRole.MEMBER,
        is_reusable=True,
        max_uses=None,  # Unlimited
        created_by=created_by,
    )
    
    db.add(invitation)
    await db.commit()
    
    return new_code


async def validate_invite_code(code: str, db: AsyncSession) -> str | None:
    """Validate an invite code and return the org_id if valid."""
    result = await db.execute(
        select(OrganizationInvitation).where(
            OrganizationInvitation.code == code.upper().strip(),
            OrganizationInvitation.is_active == True,
        )
    )
    invitation = result.scalar_one_or_none()
    
    if not invitation or not invitation.is_valid:
        return None
    
    return invitation.organization_id


async def use_invite_code(code: str, db: AsyncSession) -> bool:
    """Increment usage count for an invite code."""
    result = await db.execute(
        select(OrganizationInvitation).where(
            OrganizationInvitation.code == code.upper().strip(),
        )
    )
    invitation = result.scalar_one_or_none()
    
    if invitation:
        invitation.uses_count += 1
        await db.commit()
        return True
    return False


# In-memory storage for membership requests (until we add a proper table)
# Key: request_id -> request data
_membership_requests: dict[str, dict] = {}


# =============================================================================
# Dependencies
# =============================================================================


async def get_current_user_id(request: Request) -> str:
    """Get current user ID from session."""
    # Cookie name matches auth config
    session_id = request.cookies.get("marty_session")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    import redis.asyncio as redis
    import os
    import json
    
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    redis_client = redis.from_url(redis_url, decode_responses=True)
    
    try:
        # Redis key format matches session manager: marty:session:{session_id}
        session_json = await redis_client.get(f"marty:session:{session_id}")
        if not session_json:
            raise HTTPException(status_code=401, detail="Session expired")
        
        session_data = json.loads(session_json)
        user_id = session_data.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid session")
        
        return user_id
    finally:
        await redis_client.aclose()


async def get_session_data(request: Request) -> dict[str, Any]:
    """Get full session data from Redis using the session cookie."""
    # Cookie name matches auth config
    session_id = request.cookies.get("marty_session")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    import redis.asyncio as redis
    import os
    import json
    
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    redis_client = redis.from_url(redis_url, decode_responses=True)
    
    try:
        # Redis key format matches session manager: marty:session:{session_id}
        session_json = await redis_client.get(f"marty:session:{session_id}")
        if not session_json:
            raise HTTPException(status_code=401, detail="Session expired")
        
        session_data = json.loads(session_json)
        # Flatten attributes into main dict for easier access
        attributes = session_data.get("attributes", {})
        result = {
            **session_data,
            **attributes,
            "_session_id": session_id,
        }
        return result
    finally:
        await redis_client.aclose()


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    session: dict = Depends(get_session_data),
) -> OnboardingStatusResponse:
    """
    Check if the current user needs onboarding.
    
    Uses session data stored during login - no Keycloak admin API calls needed.
    
    A user needs onboarding if:
    - They don't have an 'onboarding_completed' attribute
    - They have the default 'applicant' user_type
    """
    user_id = session.get("user_id")
    user_email = session.get("email", "")
    user_type = session.get("user_type", "applicant")
    
    # Check for pending membership request
    pending_request = None
    for req_id, req in _membership_requests.items():
        if req.get("user_id") == user_id and req.get("status") == "pending":
            pending_request = {
                "request_id": req_id,
                "organization_id": req.get("organization_id"),
                "organization_name": req.get("organization_name"),
                "submitted_at": req.get("created_at"),
            }
            break
    
    try:
        # Check onboarding status from session attributes (set during login)
        onboarding_completed = session.get("onboarding_completed")
        organization_id = session.get("organization_id")
        organization_name = session.get("organization_name")
        
        if onboarding_completed:
            return OnboardingStatusResponse(
                needs_onboarding=False,
                user_type=user_type,
                organization_id=organization_id,
                organization_name=organization_name,
                completed_at=onboarding_completed,
                pending_request=pending_request,
            )
        
        # Check if user has vendor or administrator role (stored in session)
        roles = session.get("roles", [])
        
        if "vendor" in roles or "administrator" in roles:
            return OnboardingStatusResponse(
                needs_onboarding=False,
                user_type="vendor" if "vendor" in roles else "administrator",
                organization_id=organization_id,
                organization_name=organization_name,
                pending_request=pending_request,
            )
        
        # New users without onboarding_completed need onboarding
        return OnboardingStatusResponse(
            needs_onboarding=True,
            user_type=user_type,
            pending_request=pending_request,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking onboarding status: {e}")
        raise HTTPException(status_code=500, detail="Failed to check onboarding status")


@router.get("/organizations", response_model=OrganizationsListResponse)
async def list_organizations(
    user_id: str = Depends(get_current_user_id),
    keycloak: KeycloakAdminClient = Depends(get_keycloak_admin),
    db: AsyncSession = Depends(get_db_session),
) -> OrganizationsListResponse:
    """
    List discoverable vendor organizations.
    
    Only returns organizations that are:
    - Enabled
    - Marked as discoverable
    """
    try:
        orgs = await keycloak.list_organizations()
        
        org_list = []
        for org in orgs:
            if not org.get("enabled", True):
                continue
            
            org_id = org["id"]
            settings = await get_org_settings(org_id, db)
            
            # Only show discoverable organizations
            if not settings.get("is_discoverable", False):
                continue
            
            # Get member count
            try:
                members = await keycloak.get_organization_members(org_id)
                member_count = len(members)
            except Exception:
                member_count = 0
            
            org_list.append(OrganizationInfo(
                id=org_id,
                name=org.get("name", "Unknown"),
                description=org.get("description"),
                member_count=member_count,
                membership_mode=settings.get("membership_mode", "invite_only"),
                is_discoverable=True,
            ))
        
        return OrganizationsListResponse(organizations=org_list)
        
    except Exception as e:
        logger.error(f"Error listing organizations: {e}")
        raise HTTPException(status_code=500, detail="Failed to list organizations")


@router.post("/join-with-code", response_model=JoinWithCodeResponse)
async def join_with_invite_code(
    request_data: JoinWithCodeRequest,
    session: dict = Depends(get_session_data),
    keycloak: KeycloakAdminClient = Depends(get_keycloak_admin),
    db: AsyncSession = Depends(get_db_session),
) -> JoinWithCodeResponse:
    """
    Join an organization using an invite code.
    
    This allows users to join organizations that aren't discoverable
    or that require a code even if they allow requests.
    """
    user_id = session.get("user_id")
    user_email = session.get("email", "")
    session_id = session.get("_session_id")
    
    # Validate the invite code
    org_id = await validate_invite_code(request_data.invite_code, db)
    if not org_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired invite code. Please check the code and try again."
        )
    
    try:
        # Get organization info
        org = await keycloak.get_organization(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        
        org_name = org.get("name", "Unknown")
        
        # Add user to organization in Keycloak
        await keycloak.add_user_to_organization(org_id, user_id)
        
        # Update user attributes
        attributes = {
            "organization_id": [org_id],
            "organization_name": [org_name],
            "joined_via": ["invite_code"],
            "onboarding_completed": [datetime.utcnow().isoformat()],
        }
        await keycloak.update_user_attributes(user_id, attributes)
        
        # Update session
        if session_id:
            import redis.asyncio as redis
            import os
            
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
            redis_client = redis.from_url(redis_url, decode_responses=True)
            try:
                await redis_client.hset(
                    f"session:{session_id}",
                    mapping={
                        "organization_id": org_id,
                        "organization_name": org_name,
                        "onboarding_completed": "true",
                    }
                )
            finally:
                await redis_client.aclose()
        
        logger.info(f"User {user_email} joined organization {org_name} via invite code")
        
        return JoinWithCodeResponse(
            success=True,
            organization_id=org_id,
            organization_name=org_name,
            message=f"Successfully joined {org_name}!",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error joining with invite code: {e}")
        raise HTTPException(status_code=500, detail="Failed to join organization")


@router.post("/request-membership", response_model=RequestMembershipResponse)
async def request_membership(
    request_data: RequestMembershipRequest,
    session: dict = Depends(get_session_data),
    keycloak: KeycloakAdminClient = Depends(get_keycloak_admin),
    db: AsyncSession = Depends(get_db_session),
) -> RequestMembershipResponse:
    """
    Request to join an organization that requires approval.
    
    Creates a pending membership request that org admins can review.
    """
    user_id = session.get("user_id")
    user_email = session.get("email", "")
    
    org_id = request_data.organization_id
    settings = await get_org_settings(org_id, db)
    
    # Check if org allows membership requests
    if settings.get("membership_mode") == "invite_only":
        raise HTTPException(
            status_code=400,
            detail="This organization only accepts members via invitation. "
                   "Please contact the organization administrator."
        )
    
    # Check for existing pending request
    for req in _membership_requests.values():
        if (req.get("user_id") == user_id and 
            req.get("organization_id") == org_id and
            req.get("status") == "pending"):
            raise HTTPException(
                status_code=400,
                detail="You already have a pending request for this organization."
            )
    
    try:
        # Get organization info
        org = await keycloak.get_organization(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        
        org_name = org.get("name", "Unknown")
        
        # If org is open, join directly
        if settings.get("membership_mode") == "open":
            await keycloak.add_user_to_organization(org_id, user_id)
            
            attributes = {
                "organization_id": [org_id],
                "organization_name": [org_name],
                "joined_via": ["open_join"],
            }
            await keycloak.update_user_attributes(user_id, attributes)
            
            return RequestMembershipResponse(
                success=True,
                request_id=None,
                organization_name=org_name,
                message=f"You have joined {org_name}!",
            )
        
        # Create membership request for approval-required orgs
        request_id = str(uuid4())
        _membership_requests[request_id] = {
            "id": request_id,
            "organization_id": org_id,
            "organization_name": org_name,
            "user_id": user_id,
            "user_email": user_email,
            "message": request_data.message,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }
        
        logger.info(f"User {user_email} requested membership to {org_name}")
        
        return RequestMembershipResponse(
            success=True,
            request_id=request_id,
            organization_name=org_name,
            message=f"Your request to join {org_name} has been submitted. "
                    "You'll be notified when an administrator reviews your request.",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error requesting membership: {e}")
        raise HTTPException(status_code=500, detail="Failed to submit membership request")


@router.post("/complete", response_model=CompleteOnboardingResponse)
async def complete_onboarding(
    request_data: CompleteOnboardingRequest,
    session: dict = Depends(get_session_data),
    keycloak: KeycloakAdminClient = Depends(get_keycloak_admin),
    db: AsyncSession = Depends(get_db_session),
) -> CompleteOnboardingResponse:
    """
    Complete the onboarding process.
    
    For applicants:
    - Optionally associate with a vendor organization (if open/approval mode)
    - Keep the 'applicant' role
    
    For vendors:
    - Switch role from 'applicant' to 'vendor'
    - Create new organization with specified settings
    - Set as organization owner
    """
    user_id = session.get("user_id")
    user_email = session.get("email", "")
    session_id = session.get("_session_id")
    
    if request_data.user_type not in ("applicant", "vendor"):
        raise HTTPException(
            status_code=400, 
            detail="Invalid user type. Must be 'applicant' or 'vendor'"
        )
    
    try:
        org_id = None
        org_name = None
        membership_status = "none"
        invite_code = None
        
        if request_data.user_type == "vendor":
            # Vendor flow: create new organization
            if request_data.organization_id:
                # Vendors joining existing org - this should go through invite code
                raise HTTPException(
                    status_code=400,
                    detail="Vendors must create a new organization or use an invite code to join existing one."
                )
            
            if not request_data.organization_name:
                raise HTTPException(
                    status_code=400,
                    detail="Organization name is required"
                )
            
            # Create new organization in Keycloak
            new_org = await keycloak.create_organization(
                name=request_data.organization_name,
                description=request_data.organization_description,
            )
            org_id = new_org.get("id")
            org_name = request_data.organization_name
            
            # Store organization settings (also create Organization record in local DB)
            await set_org_settings(org_id, {
                "name": org_name,  # Needed for creating local DB record
                "is_discoverable": request_data.is_discoverable,
                "membership_mode": request_data.membership_mode,
                "created_by": user_id,
                "created_at": datetime.utcnow().isoformat(),
            }, db)
            
            # Generate invite code for the organization
            invite_code = await generate_invite_code(org_id, db, created_by=user_id)
            logger.info(f"Created org '{org_name}' with invite code: {invite_code}")
            
            # Add user to organization as owner
            await keycloak.add_user_to_organization(org_id, user_id)
            
            # Update role from applicant to vendor
            await keycloak.remove_user_role(user_id, "applicant")
            await keycloak.add_user_role(user_id, "vendor")
            
            membership_status = "owner"
            
        elif request_data.user_type == "applicant":
            # Applicant flow
            if request_data.organization_id:
                # Require explicit confirmation
                if not request_data.confirm_organization:
                    raise HTTPException(
                        status_code=400,
                        detail="Please confirm your organization selection"
                    )
                
                org_id = request_data.organization_id
                settings = await get_org_settings(org_id, db)
                
                # Get org info
                org = await keycloak.get_organization(org_id)
                if not org:
                    raise HTTPException(status_code=404, detail="Organization not found")
                org_name = org.get("name")
                
                membership_mode = settings.get("membership_mode", "invite_only")
                
                if membership_mode == "invite_only":
                    raise HTTPException(
                        status_code=400,
                        detail="This organization only accepts members via invitation. "
                               "Please use an invite code or contact the administrator."
                    )
                elif membership_mode == "open":
                    # Join directly
                    await keycloak.add_user_to_organization(org_id, user_id)
                    membership_status = "joined"
                elif membership_mode == "approval":
                    # Create membership request
                    request_id = str(uuid4())
                    _membership_requests[request_id] = {
                        "id": request_id,
                        "organization_id": org_id,
                        "organization_name": org_name,
                        "user_id": user_id,
                        "user_email": user_email,
                        "status": "pending",
                        "created_at": datetime.utcnow().isoformat(),
                    }
                    membership_status = "pending_approval"
        
        # Update user attributes
        attributes = {
            "user_type": [request_data.user_type],
            "onboarding_completed": [datetime.utcnow().isoformat()],
        }
        if org_id:
            attributes["organization_id"] = [org_id]
        if org_name:
            attributes["organization_name"] = [org_name]
        
        await keycloak.update_user_attributes(user_id, attributes)
        
        # Update session
        if session_id:
            import redis.asyncio as redis
            import os
            
            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
            redis_client = redis.from_url(redis_url, decode_responses=True)
            try:
                await redis_client.hset(
                    f"session:{session_id}",
                    mapping={
                        "user_type": request_data.user_type,
                        "organization_id": org_id or "",
                        "organization_name": org_name or "",
                        "onboarding_completed": "true",
                    }
                )
            finally:
                await redis_client.aclose()
        
        # Build response message
        if request_data.user_type == "vendor":
            message = f"Welcome! Your organization '{org_name}' has been created. Your invite code is: {invite_code}"
        elif membership_status == "joined":
            message = f"Welcome! You've joined {org_name}."
        elif membership_status == "pending_approval":
            message = f"Your request to join {org_name} is pending approval."
        else:
            message = "Welcome! Your account has been set up."
        
        logger.info(
            f"Completed onboarding for {user_email}: "
            f"type={request_data.user_type}, org={org_name}, status={membership_status}"
        )
        
        return CompleteOnboardingResponse(
            success=True,
            user_type=request_data.user_type,
            organization_id=org_id,
            organization_name=org_name,
            membership_status=membership_status,
            invite_code=invite_code,
            message=message,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing onboarding: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to complete onboarding: {str(e)}")


# =============================================================================
# Organization Management Endpoints (for vendors)
# =============================================================================


class OrgSettingsResponse(BaseModel):
    """Organization settings response."""
    
    organization_id: str
    organization_name: str
    is_discoverable: bool
    membership_mode: str
    invite_code: str | None = None


class UpdateOrgSettingsRequest(BaseModel):
    """Request to update organization settings."""
    
    is_discoverable: bool | None = None
    membership_mode: Literal["invite_only", "approval", "open"] | None = None
    regenerate_invite_code: bool = False


@router.get("/org-settings", response_model=OrgSettingsResponse)
async def get_organization_settings(
    session: dict = Depends(get_session_data),
    keycloak: KeycloakAdminClient = Depends(get_keycloak_admin),
    db: AsyncSession = Depends(get_db_session),
) -> OrgSettingsResponse:
    """Get current organization settings (for vendors)."""
    user_id = session.get("user_id")
    
    # Get user's organization
    orgs = await keycloak.get_user_organizations(user_id)
    if not orgs:
        raise HTTPException(status_code=404, detail="You are not a member of any organization")
    
    org = orgs[0]
    org_id = org["id"]
    settings = await get_org_settings(org_id, db)
    
    return OrgSettingsResponse(
        organization_id=org_id,
        organization_name=org.get("name", "Unknown"),
        is_discoverable=settings.get("is_discoverable", False),
        membership_mode=settings.get("membership_mode", "invite_only"),
        invite_code=settings.get("invite_code"),
    )


@router.put("/org-settings", response_model=OrgSettingsResponse)
async def update_organization_settings(
    request_data: UpdateOrgSettingsRequest,
    session: dict = Depends(get_session_data),
    keycloak: KeycloakAdminClient = Depends(get_keycloak_admin),
    db: AsyncSession = Depends(get_db_session),
) -> OrgSettingsResponse:
    """Update organization settings (for vendors)."""
    user_id = session.get("user_id")
    
    # Get user's organization
    orgs = await keycloak.get_user_organizations(user_id)
    if not orgs:
        raise HTTPException(status_code=404, detail="You are not a member of any organization")
    
    org = orgs[0]
    org_id = org["id"]
    
    # Update settings
    current_settings = await get_org_settings(org_id, db)
    
    if request_data.is_discoverable is not None:
        current_settings["is_discoverable"] = request_data.is_discoverable
    
    if request_data.membership_mode is not None:
        current_settings["membership_mode"] = request_data.membership_mode
    
    if request_data.regenerate_invite_code:
        await generate_invite_code(org_id, db, created_by=user_id)
        current_settings = await get_org_settings(org_id, db)  # Refresh to get new code
    
    await set_org_settings(org_id, current_settings, db)
    
    logger.info(f"Updated settings for organization {org.get('name')}")
    
    return OrgSettingsResponse(
        organization_id=org_id,
        organization_name=org.get("name", "Unknown"),
        is_discoverable=current_settings.get("is_discoverable", False),
        membership_mode=current_settings.get("membership_mode", "invite_only"),
        invite_code=current_settings.get("invite_code"),
    )


class MembershipRequestInfo(BaseModel):
    """Membership request info."""
    
    id: str
    user_email: str
    message: str | None = None
    status: str
    created_at: str


class PendingRequestsResponse(BaseModel):
    """List of pending membership requests."""
    
    requests: list[MembershipRequestInfo]


@router.get("/pending-requests", response_model=PendingRequestsResponse)
async def get_pending_requests(
    session: dict = Depends(get_session_data),
    keycloak: KeycloakAdminClient = Depends(get_keycloak_admin),
) -> PendingRequestsResponse:
    """Get pending membership requests for vendor's organization."""
    user_id = session.get("user_id")
    
    orgs = await keycloak.get_user_organizations(user_id)
    if not orgs:
        raise HTTPException(status_code=404, detail="You are not a member of any organization")
    
    org_id = orgs[0]["id"]
    
    # Get pending requests for this org
    pending = [
        MembershipRequestInfo(
            id=req["id"],
            user_email=req["user_email"],
            message=req.get("message"),
            status=req["status"],
            created_at=req["created_at"],
        )
        for req in _membership_requests.values()
        if req.get("organization_id") == org_id and req.get("status") == "pending"
    ]
    
    return PendingRequestsResponse(requests=pending)


class ReviewRequestRequest(BaseModel):
    """Request to approve or reject a membership request."""
    
    request_id: str
    action: Literal["approve", "reject"]
    rejection_reason: str | None = None


class ReviewRequestResponse(BaseModel):
    """Response after reviewing a membership request."""
    
    success: bool
    message: str


@router.post("/review-request", response_model=ReviewRequestResponse)
async def review_membership_request(
    request_data: ReviewRequestRequest,
    session: dict = Depends(get_session_data),
    keycloak: KeycloakAdminClient = Depends(get_keycloak_admin),
) -> ReviewRequestResponse:
    """Approve or reject a membership request."""
    reviewer_id = session.get("user_id")
    
    # Get the request
    membership_req = _membership_requests.get(request_data.request_id)
    if not membership_req:
        raise HTTPException(status_code=404, detail="Request not found")
    
    if membership_req.get("status") != "pending":
        raise HTTPException(status_code=400, detail="Request has already been processed")
    
    # Verify reviewer is in the organization
    orgs = await keycloak.get_user_organizations(reviewer_id)
    if not orgs or orgs[0]["id"] != membership_req["organization_id"]:
        raise HTTPException(status_code=403, detail="You cannot review requests for this organization")
    
    org_id = membership_req["organization_id"]
    org_name = membership_req["organization_name"]
    user_id = membership_req["user_id"]
    user_email = membership_req["user_email"]
    
    if request_data.action == "approve":
        # Add user to organization
        await keycloak.add_user_to_organization(org_id, user_id)
        
        # Update user attributes
        await keycloak.update_user_attributes(user_id, {
            "organization_id": [org_id],
            "organization_name": [org_name],
            "joined_via": ["approval"],
        })
        
        membership_req["status"] = "approved"
        membership_req["reviewed_by"] = reviewer_id
        membership_req["reviewed_at"] = datetime.utcnow().isoformat()
        
        logger.info(f"Approved membership request from {user_email} to {org_name}")
        
        return ReviewRequestResponse(
            success=True,
            message=f"{user_email} has been added to the organization.",
        )
    else:
        membership_req["status"] = "rejected"
        membership_req["reviewed_by"] = reviewer_id
        membership_req["reviewed_at"] = datetime.utcnow().isoformat()
        membership_req["rejection_reason"] = request_data.rejection_reason
        
        logger.info(f"Rejected membership request from {user_email} to {org_name}")
        
        return ReviewRequestResponse(
            success=True,
            message=f"Request from {user_email} has been rejected.",
        )
