"""Credential Configuration API Router.

Provides endpoints for organizations to configure which credential types
they can issue and the required/optional fields for each type.

Endpoints:
- GET /api/organizations/{org_id}/credential-types - List configured types
- POST /api/organizations/{org_id}/credential-types - Add credential type
- GET /api/organizations/{org_id}/credential-types/{type_id} - Get single config
- PUT /api/organizations/{org_id}/credential-types/{type_id} - Update config
- DELETE /api/organizations/{org_id}/credential-types/{type_id} - Disable type
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from subscription.models import (
    CredentialType,
    CredentialTypeConfiguration,
    Organization,
)
from subscription.database import get_db_session
from auth.router import get_current_user, AuthStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/organizations", tags=["credentials"])


# =============================================================================
# Default Field Configurations
# =============================================================================

# Travel document field configurations
TRAVEL_VISA_FIELDS = {
    "required": ["given_name", "family_name", "birth_date", "nationality", "document_number"],
    "optional": ["portrait", "visa_type", "valid_from", "valid_until", "issuing_country", "issuing_authority"],
}

PASSPORT_FIELDS = {
    "required": ["given_name", "family_name", "birth_date", "nationality", "document_number", "expiry_date"],
    "optional": ["portrait", "sex", "birth_place", "issuing_authority", "mrz_line1", "mrz_line2"],
}

DRIVERS_LICENSE_FIELDS = {
    "required": ["given_name", "family_name", "birth_date", "document_number", "issue_date", "expiry_date"],
    "optional": ["portrait", "address", "vehicle_categories", "restrictions", "issuing_authority"],
}

ACCESS_BADGE_FIELDS = {
    "required": ["given_name", "family_name", "employee_id"],
    "optional": ["portrait", "department", "access_level", "valid_from", "valid_until"],
}

NATIONAL_ID_FIELDS = {
    "required": ["given_name", "family_name", "birth_date", "document_number", "nationality"],
    "optional": ["portrait", "sex", "birth_place", "address", "expiry_date"],
}

DTC_FIELDS = {
    "required": ["passport_number", "issuing_authority", "issue_date", "expiry_date", "dtc_type"],
    "optional": [
        "personal_details",
        "data_groups",
        "access_control",
        "access_key",
        "dtc_valid_from",
        "dtc_valid_until",
        "type1_profile",
        "type2_profile",
        "type3_profile",
    ],
}

OPEN_BADGE_FIELDS = {
    "required": ["version", "payload_json"],
    "optional": ["document_store_json", "recipient_identity", "signing_json"],
}

DEFAULT_FIELDS = {
    CredentialType.TRAVEL_VISA: TRAVEL_VISA_FIELDS,
    CredentialType.PASSPORT: PASSPORT_FIELDS,
    CredentialType.DRIVERS_LICENSE: DRIVERS_LICENSE_FIELDS,
    CredentialType.ACCESS_BADGE: ACCESS_BADGE_FIELDS,
    CredentialType.NATIONAL_ID: NATIONAL_ID_FIELDS,
    CredentialType.DTC: DTC_FIELDS,
    CredentialType.OPEN_BADGE: OPEN_BADGE_FIELDS,
}

# Document type identifiers
DOCTYPE_MAP = {
    CredentialType.TRAVEL_VISA: "org.marty.travel.visa.1",
    CredentialType.PASSPORT: "org.marty.passport.1",
    CredentialType.DRIVERS_LICENSE: "org.iso.18013.5.1.mDL",
    CredentialType.ACCESS_BADGE: "org.marty.access.badge.1",
    CredentialType.NATIONAL_ID: "org.marty.national_id.1",
    CredentialType.DTC: "org.icao.dtc.1",
    CredentialType.OPEN_BADGE: "openbadges",
}


# =============================================================================
# Issuer Key Generation
# =============================================================================

_MARTY_RS_AVAILABLE = False
try:
    import marty_rs  # type: ignore
    _MARTY_RS_AVAILABLE = True
except Exception:
    marty_rs = None

_CRYPTO_BRIDGE_AVAILABLE = False
try:
    from marty_plugin.common.crypto_bridge import jwk_generate
    _CRYPTO_BRIDGE_AVAILABLE = True
except Exception:
    jwk_generate = None


def _generate_issuer_key() -> dict[str, Any]:
    """Generate a signing key for credential issuance."""
    if _MARTY_RS_AVAILABLE and marty_rs is not None:
        import json

        result_json = marty_rs.generate_ed25519_key()
        return json.loads(result_json)

    if _CRYPTO_BRIDGE_AVAILABLE and jwk_generate is not None:
        import json
        key = jwk_generate("ed25519")
        jwk_json = json.loads(key.to_json())
        key_id = jwk_json.get("kid") or key.thumbprint()
        return {
            "did": f"did:key:{key_id}",
            "jwk": jwk_json,
            "keyId": key_id,
        }

    key_id = f"key_{uuid4().hex[:8]}"
    return {
        "did": f"did:key:{key_id}",
        "jwk": {"kty": "OKP", "crv": "Ed25519", "x": "mock_public_key"},
        "keyId": key_id,
    }


# =============================================================================
# Request/Response Models
# =============================================================================


class CredentialTypeInfo(BaseModel):
    """Info about a configured credential type."""
    
    id: str
    credential_type: str
    display_name: str
    doctype: str | None = None
    required_fields: list[str]
    optional_fields: list[str]
    validity_days: int
    is_active: bool
    created_at: str
    updated_at: str | None = None


class ListCredentialTypesResponse(BaseModel):
    """Response for listing credential types."""
    
    credential_types: list[CredentialTypeInfo]
    available_types: list[str]  # Types not yet configured


class CreateCredentialTypeRequest(BaseModel):
    """Request to configure a new credential type."""
    
    credential_type: str = Field(
        ...,
        description=(
            "Type: travel_visa, passport, drivers_license, access_badge, national_id, dtc, open_badge"
        ),
    )
    display_name: str = Field(..., min_length=1, max_length=255, description="Human-readable name")
    required_fields: list[str] | None = Field(None, description="Override default required fields")
    optional_fields: list[str] | None = Field(None, description="Override default optional fields")
    validity_days: int = Field(365, ge=1, le=3650, description="Credential validity in days")


class UpdateCredentialTypeRequest(BaseModel):
    """Request to update a credential type configuration."""
    
    display_name: str | None = Field(None, min_length=1, max_length=255)
    required_fields: list[str] | None = None
    optional_fields: list[str] | None = None
    validity_days: int | None = Field(None, ge=1, le=3650)
    is_active: bool | None = None


class CredentialTypeResponse(BaseModel):
    """Response with single credential type config."""
    
    credential_type: CredentialTypeInfo


class DefaultFieldsResponse(BaseModel):
    """Response with default field configurations."""
    
    credential_type: str
    doctype: str
    required_fields: list[str]
    optional_fields: list[str]


# =============================================================================
# Helper Functions
# =============================================================================


def _config_to_info(config: CredentialTypeConfiguration) -> CredentialTypeInfo:
    """Convert database model to response model."""
    return CredentialTypeInfo(
        id=config.id,
        credential_type=config.credential_type.value,
        display_name=config.display_name,
        doctype=config.doctype,
        required_fields=config.required_fields or [],
        optional_fields=config.optional_fields or [],
        validity_days=config.validity_days,
        is_active=config.is_active,
        created_at=config.created_at.isoformat() if config.created_at else "",
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )


async def _verify_org_access(
    org_id: str,
    current_user: AuthStatusResponse,
    db: AsyncSession,
) -> Organization:
    """Verify user has access to the organization.
    
    If the organization exists in Keycloak but not in the local database,
    auto-create it to enable credential configuration.
    """
    import re
    
    if not current_user.authenticated or not current_user.user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = current_user.user
    
    # Check organization exists
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()
    
    # Check user authorization first
    user_org_id = getattr(user, "organization_id", None)
    user_type = getattr(user, "user_type", None)
    is_admin = user_type == "administrator"
    is_org_member = user_org_id == org_id
    
    if not org:
        # Organization doesn't exist in local DB
        # If user is member of this org (from Keycloak), auto-create it
        if is_org_member or is_admin:
            # Get org name from user session if available
            org_name = getattr(user, "organization_name", None) or f"Organization {org_id[:8]}"
            slug = re.sub(r'[^a-z0-9]+', '-', org_name.lower()).strip('-')
            slug = f"{slug}-{org_id[:8]}"
            
            org = Organization(
                id=org_id,
                name=org_name,
                slug=slug,
                is_active=True,
                is_discoverable=False,
            )
            db.add(org)
            await db.commit()
            await db.refresh(org)
            logger.info(f"Auto-created organization from Keycloak: {org_id} ({org_name})")
        else:
            raise HTTPException(status_code=404, detail="Organization not found")
    
    # Verify access
    if not is_org_member and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized for this organization")
    
    return org


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/{org_id}/credential-types", response_model=ListCredentialTypesResponse)
async def list_credential_types(
    org_id: str,
    current_user: AuthStatusResponse = Depends(get_current_user),
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db_session),
):
    """List configured credential types for an organization."""
    await _verify_org_access(org_id, current_user, db)
    
    query = select(CredentialTypeConfiguration).where(
        CredentialTypeConfiguration.organization_id == org_id
    )
    if not include_inactive:
        query = query.where(CredentialTypeConfiguration.is_active == True)
    
    result = await db.execute(query)
    configs = result.scalars().all()
    
    # Determine which types are still available to configure
    configured_types = {c.credential_type for c in configs if c.is_active}
    all_types = set(CredentialType)
    available_types = [t.value for t in all_types - configured_types]
    
    return ListCredentialTypesResponse(
        credential_types=[_config_to_info(c) for c in configs],
        available_types=available_types,
    )


@router.get("/credential-types/defaults/{credential_type}", response_model=DefaultFieldsResponse)
async def get_default_fields(
    credential_type: str,
):
    """Get default field configuration for a credential type.
    
    This endpoint is public and returns the recommended fields for each type.
    """
    try:
        cred_type = CredentialType(credential_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid credential type. Valid types: {[t.value for t in CredentialType]}"
        )
    
    defaults = DEFAULT_FIELDS.get(cred_type, {"required": [], "optional": []})
    doctype = DOCTYPE_MAP.get(cred_type, "")
    
    return DefaultFieldsResponse(
        credential_type=credential_type,
        doctype=doctype,
        required_fields=defaults["required"],
        optional_fields=defaults["optional"],
    )


@router.post("/{org_id}/credential-types", response_model=CredentialTypeResponse, status_code=201)
async def create_credential_type(
    org_id: str,
    body: CreateCredentialTypeRequest,
    current_user: AuthStatusResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Configure a new credential type for the organization."""
    await _verify_org_access(org_id, current_user, db)
    
    # Validate credential type
    try:
        cred_type = CredentialType(body.credential_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid credential type. Valid types: {[t.value for t in CredentialType]}"
        )
    
    # Check if already configured
    existing = await db.execute(
        select(CredentialTypeConfiguration).where(
            CredentialTypeConfiguration.organization_id == org_id,
            CredentialTypeConfiguration.credential_type == cred_type,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Credential type already configured")
    
    # Get defaults
    defaults = DEFAULT_FIELDS.get(cred_type, {"required": [], "optional": []})
    doctype = DOCTYPE_MAP.get(cred_type, "")
    
    # Create configuration
    issuer_key = _generate_issuer_key()
    config = CredentialTypeConfiguration(
        id=str(uuid4()),
        organization_id=org_id,
        credential_type=cred_type,
        display_name=body.display_name,
        doctype=doctype,
        required_fields=body.required_fields or defaults["required"],
        optional_fields=body.optional_fields or defaults["optional"],
        validity_days=body.validity_days,
        issuer_key_id=issuer_key.get("keyId"),
        issuer_did=issuer_key.get("did"),
        issuer_jwk=issuer_key.get("jwk"),
        is_active=True,
    )
    
    db.add(config)
    await db.commit()
    await db.refresh(config)
    
    logger.info(f"Created credential type config: org={org_id}, type={cred_type.value}")
    
    return CredentialTypeResponse(credential_type=_config_to_info(config))


@router.get("/{org_id}/credential-types/{type_id}", response_model=CredentialTypeResponse)
async def get_credential_type(
    org_id: str,
    type_id: str,
    current_user: AuthStatusResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get a specific credential type configuration."""
    await _verify_org_access(org_id, current_user, db)
    
    result = await db.execute(
        select(CredentialTypeConfiguration).where(
            CredentialTypeConfiguration.id == type_id,
            CredentialTypeConfiguration.organization_id == org_id,
        )
    )
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="Credential type configuration not found")
    
    return CredentialTypeResponse(credential_type=_config_to_info(config))


@router.put("/{org_id}/credential-types/{type_id}", response_model=CredentialTypeResponse)
async def update_credential_type(
    org_id: str,
    type_id: str,
    body: UpdateCredentialTypeRequest,
    current_user: AuthStatusResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Update a credential type configuration."""
    await _verify_org_access(org_id, current_user, db)
    
    result = await db.execute(
        select(CredentialTypeConfiguration).where(
            CredentialTypeConfiguration.id == type_id,
            CredentialTypeConfiguration.organization_id == org_id,
        )
    )
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="Credential type configuration not found")
    
    # Update fields
    if body.display_name is not None:
        config.display_name = body.display_name
    if body.required_fields is not None:
        config.required_fields = body.required_fields
    if body.optional_fields is not None:
        config.optional_fields = body.optional_fields
    if body.validity_days is not None:
        config.validity_days = body.validity_days
    if body.is_active is not None:
        config.is_active = body.is_active
    
    config.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(config)
    
    logger.info(f"Updated credential type config: org={org_id}, type={config.credential_type.value}")
    
    return CredentialTypeResponse(credential_type=_config_to_info(config))


@router.delete("/{org_id}/credential-types/{type_id}", status_code=204)
async def delete_credential_type(
    org_id: str,
    type_id: str,
    current_user: AuthStatusResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Disable a credential type configuration (soft delete)."""
    await _verify_org_access(org_id, current_user, db)
    
    result = await db.execute(
        select(CredentialTypeConfiguration).where(
            CredentialTypeConfiguration.id == type_id,
            CredentialTypeConfiguration.organization_id == org_id,
        )
    )
    config = result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(status_code=404, detail="Credential type configuration not found")
    
    config.is_active = False
    config.updated_at = datetime.utcnow()
    
    await db.commit()
    
    logger.info(f"Disabled credential type config: org={org_id}, type={config.credential_type.value}")
