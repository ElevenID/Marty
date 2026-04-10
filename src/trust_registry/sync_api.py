"""
Trust Registry Sync API

Provides delta sync endpoints for mobile wallet trust registry updates.
Supports efficient polling with ETags and incremental updates.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/trust-registry", tags=["trust-registry"])


class TrustAnchorType(str, Enum):
    """Types of trust anchors."""
    CSCA = "csca"  # Country Signing CA (eMRTD/ePassport)
    DSC = "dsc"    # Document Signer Certificate (eMRTD)
    IACA = "iaca"  # Issuing Authority CA (mDL ISO 18013-5)
    ISSUER = "issuer"  # Credential issuer
    VERIFIER = "verifier"  # Trusted verifier


class TrustAnchorStatus(str, Enum):
    """Trust anchor status."""
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    SUSPENDED = "suspended"


class DeltaOperation(str, Enum):
    """Delta sync operation types."""
    ADD = "add"
    UPDATE = "update"
    REVOKE = "revoke"
    DELETE = "delete"


# Request/Response Models
class TrustAnchorResponse(BaseModel):
    """Trust anchor in API response."""
    id: str
    type: TrustAnchorType
    status: TrustAnchorStatus
    name: str
    country_code: Optional[str] = None
    jurisdiction: Optional[str] = None  # For IACA: AAMVA jurisdiction (e.g., US-CA, CA-ON)
    certificate_pem: Optional[str] = None
    public_key_jwk: Optional[dict[str, Any]] = None
    issuer_did: Optional[str] = None
    valid_from: datetime
    valid_until: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    vical_version: Optional[str] = None  # For IACA: AAMVA VICAL version
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime


class DeltaEntry(BaseModel):
    """Single delta sync entry."""
    operation: DeltaOperation
    anchor: TrustAnchorResponse
    sequence: int


class DeltaSyncResponse(BaseModel):
    """Delta sync response."""
    anchors: list[DeltaEntry]
    next_cursor: Optional[str] = None
    has_more: bool = False
    total_count: int
    etag: str


class FullSyncResponse(BaseModel):
    """Full sync response."""
    anchors: list[TrustAnchorResponse]
    total_count: int
    etag: str
    generated_at: datetime


class RevocationListResponse(BaseModel):
    """Revocation list response."""
    format: str  # "tsl" or "bitstring"
    list_id: str
    credential_type: str
    encoded_list: str
    valid_until: datetime
    etag: str


# Dependency for database session — must be overridden at app startup
async def get_db() -> AsyncSession:
    """Get database session — override via app.dependency_overrides[get_db]."""
    raise NotImplementedError(
        "get_db() dependency not configured. "
        "Set app.dependency_overrides[get_db] in your application startup."
    )


@dataclass
class TrustRegistryService:
    """
    Trust Registry service for mobile wallet sync.
    
    Features:
    - Full sync for initial wallet setup
    - Delta sync for efficient updates
    - ETag-based caching
    - Pagination with cursors
    """
    
    db: AsyncSession
    
    # In-memory cache for ETags (should be Redis in production)
    _etag_cache: dict[str, str] = field(default_factory=dict)
    
    async def get_full_registry(
        self,
        anchor_types: Optional[list[TrustAnchorType]] = None,
        country_codes: Optional[list[str]] = None,
    ) -> FullSyncResponse:
        """
        Get full trust registry for initial sync.
        
        Args:
            anchor_types: Filter by anchor types
            country_codes: Filter by country codes
            
        Returns:
            Complete registry with ETag
        """
        # Build query
        # Note: Using a mock query structure - actual implementation depends on DB schema
        anchors = await self._query_anchors(
            anchor_types=anchor_types,
            country_codes=country_codes,
            active_only=True,
        )
        
        # Convert to response models
        anchor_responses = [self._to_anchor_response(a) for a in anchors]
        
        # Generate ETag from content hash
        etag = self._generate_etag(anchor_responses)
        
        return FullSyncResponse(
            anchors=anchor_responses,
            total_count=len(anchor_responses),
            etag=etag,
            generated_at=datetime.now(timezone.utc),
        )
    
    async def get_delta_sync(
        self,
        since_cursor: Optional[str] = None,
        since_etag: Optional[str] = None,
        limit: int = 100,
        anchor_types: Optional[list[TrustAnchorType]] = None,
    ) -> DeltaSyncResponse:
        """
        Get delta updates since last sync.
        
        Args:
            since_cursor: Cursor from previous delta response
            since_etag: ETag from previous sync (alternative to cursor)
            limit: Maximum entries to return
            anchor_types: Filter by anchor types
            
        Returns:
            Delta entries with next cursor
        """
        # Parse cursor to get last sequence number
        last_sequence = 0
        if since_cursor:
            try:
                last_sequence = int(since_cursor)
            except ValueError:
                pass
        
        # Query changes since last sync
        changes = await self._query_changes(
            since_sequence=last_sequence,
            anchor_types=anchor_types,
            limit=limit + 1,  # Fetch one extra to check if more
        )
        
        has_more = len(changes) > limit
        if has_more:
            changes = changes[:limit]
        
        # Build delta entries
        delta_entries = []
        for change in changes:
            delta_entries.append(DeltaEntry(
                operation=change["operation"],
                anchor=self._to_anchor_response(change["anchor"]),
                sequence=change["sequence"],
            ))
        
        # Calculate next cursor
        next_cursor = None
        if delta_entries:
            next_cursor = str(delta_entries[-1].sequence)
        
        # Generate ETag
        etag = self._generate_delta_etag(delta_entries)
        
        return DeltaSyncResponse(
            anchors=delta_entries,
            next_cursor=next_cursor,
            has_more=has_more,
            total_count=len(delta_entries),
            etag=etag,
        )
    
    async def get_revocation_list(
        self,
        credential_type: str,
        list_id: str,
    ) -> RevocationListResponse:
        """
        Get revocation status list for a credential type.
        
        Args:
            credential_type: "mdoc" or "sd_jwt_vc"
            list_id: The specific list ID (shard)
            
        Returns:
            Encoded revocation list
        """
        # Determine format based on credential type
        if credential_type == "mdoc":
            format_type = "tsl"  # Token Status List
        else:
            format_type = "bitstring"  # Bitstring Status List
        
        # Get the status list from revocation service
        # This would integrate with StatusListManager
        encoded_list = await self._get_encoded_status_list(
            credential_type=credential_type,
            list_id=list_id,
            format_type=format_type,
        )
        
        etag = hashlib.sha256(encoded_list.encode()).hexdigest()[:16]
        
        return RevocationListResponse(
            format=format_type,
            list_id=list_id,
            credential_type=credential_type,
            encoded_list=encoded_list,
            valid_until=datetime.now(timezone.utc),  # Add cache duration
            etag=etag,
        )
    
    async def _query_anchors(
        self,
        anchor_types: Optional[list[TrustAnchorType]] = None,
        country_codes: Optional[list[str]] = None,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Query trust anchors from database."""
        # Placeholder - actual implementation depends on DB schema
        # This would query TrustAnchor table
        return []
    
    async def _query_changes(
        self,
        since_sequence: int,
        anchor_types: Optional[list[TrustAnchorType]] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query change log for delta sync."""
        # Placeholder - would query TrustAnchorChangeLog table
        return []
    
    async def _get_encoded_status_list(
        self,
        credential_type: str,
        list_id: str,
        format_type: str,
    ) -> str:
        """Get encoded status list from revocation service."""
        # Placeholder - integrates with StatusListManager
        return ""
    
    def _to_anchor_response(self, anchor: dict[str, Any]) -> TrustAnchorResponse:
        """Convert database record to response model."""
        return TrustAnchorResponse(
            id=str(anchor.get("id", "")),
            type=TrustAnchorType(anchor.get("type", "issuer")),
            status=TrustAnchorStatus(anchor.get("status", "active")),
            name=anchor.get("name", ""),
            country_code=anchor.get("country_code"),
            certificate_pem=anchor.get("certificate_pem"),
            public_key_jwk=anchor.get("public_key_jwk"),
            issuer_did=anchor.get("issuer_did"),
            valid_from=anchor.get("valid_from", datetime.now(timezone.utc)),
            valid_until=anchor.get("valid_until"),
            revoked_at=anchor.get("revoked_at"),
            metadata=anchor.get("metadata", {}),
            updated_at=anchor.get("updated_at", datetime.now(timezone.utc)),
        )
    
    def _generate_etag(self, anchors: list[TrustAnchorResponse]) -> str:
        """Generate ETag from anchor list."""
        content = "|".join(
            f"{a.id}:{a.status}:{a.updated_at.isoformat()}"
            for a in anchors
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _generate_delta_etag(self, entries: list[DeltaEntry]) -> str:
        """Generate ETag from delta entries."""
        if not entries:
            return "empty"
        content = f"{entries[-1].sequence}:{len(entries)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# FastAPI Routes
@router.get(
    "/sync/full",
    response_model=FullSyncResponse,
    summary="Full Trust Registry Sync",
    description="Get complete trust registry for initial wallet setup.",
)
async def full_sync(
    anchor_types: Optional[list[TrustAnchorType]] = Query(
        None,
        description="Filter by anchor types",
    ),
    country_codes: Optional[list[str]] = Query(
        None,
        description="Filter by country codes (ISO 3166-1 alpha-2)",
    ),
    if_none_match: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> FullSyncResponse | JSONResponse:
    """
    Get full trust registry.
    
    Use this endpoint for:
    - Initial wallet setup
    - Full re-sync after long offline period
    - Recovery from corrupted local state
    """
    service = TrustRegistryService(db=db)
    response = await service.get_full_registry(
        anchor_types=anchor_types,
        country_codes=country_codes,
    )
    
    # Check ETag for 304 Not Modified
    if if_none_match and if_none_match == response.etag:
        return JSONResponse(
            status_code=status.HTTP_304_NOT_MODIFIED,
            content=None,
            headers={"ETag": response.etag},
        )
    
    return response


@router.get(
    "/sync/delta",
    response_model=DeltaSyncResponse,
    summary="Delta Trust Registry Sync",
    description="Get incremental updates since last sync.",
)
async def delta_sync(
    cursor: Optional[str] = Query(
        None,
        description="Cursor from previous delta response",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum entries to return",
    ),
    anchor_types: Optional[list[TrustAnchorType]] = Query(
        None,
        description="Filter by anchor types",
    ),
    if_none_match: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> DeltaSyncResponse | JSONResponse:
    """
    Get delta updates since last sync.
    
    Use this endpoint for:
    - Regular background sync (recommended: every 15-30 minutes)
    - Push notification triggered updates
    - App foreground refresh
    """
    service = TrustRegistryService(db=db)
    response = await service.get_delta_sync(
        since_cursor=cursor,
        limit=limit,
        anchor_types=anchor_types,
    )
    
    # Check ETag for 304 Not Modified
    if if_none_match and if_none_match == response.etag:
        return JSONResponse(
            status_code=status.HTTP_304_NOT_MODIFIED,
            content=None,
            headers={"ETag": response.etag},
        )
    
    return response


@router.get(
    "/revocation/{credential_type}/{list_id}",
    response_model=RevocationListResponse,
    summary="Get Revocation Status List",
    description="Get credential revocation status list. "
    "This endpoint is intentionally public per W3C Bitstring Status List v1.0 "
    "and IETF Token Status List (draft-14). Rate limiting should be applied "
    "at the infrastructure layer (reverse proxy / CDN).",
)
async def get_revocation_list(
    credential_type: str,
    list_id: str,
    if_none_match: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> RevocationListResponse | JSONResponse:
    """
    Get revocation status list.
    
    Credential types:
    - `mdoc`: Returns Token Status List (IETF draft-14)
    - `sd_jwt_vc`: Returns Bitstring Status List (W3C v1.0)
    """
    if credential_type not in ("mdoc", "sd_jwt_vc"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid credential type: {credential_type}",
        )
    
    service = TrustRegistryService(db=db)
    
    try:
        response = await service.get_revocation_list(
            credential_type=credential_type,
            list_id=list_id,
        )
    except Exception as e:
        logger.error(f"Failed to get revocation list: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revocation list not found: {list_id}",
        )
    
    # Check ETag for 304 Not Modified
    if if_none_match and if_none_match == response.etag:
        return JSONResponse(
            status_code=status.HTTP_304_NOT_MODIFIED,
            content=None,
            headers={"ETag": response.etag},
        )
    
    return response


@router.get(
    "/anchors/{anchor_id}",
    response_model=TrustAnchorResponse,
    summary="Get Trust Anchor",
    description="Get a specific trust anchor by ID.",
)
async def get_anchor(
    anchor_id: str,
    db: AsyncSession = Depends(get_db),
) -> TrustAnchorResponse:
    """
    Get a specific trust anchor.
    
    Use this for:
    - Verifying a specific issuer/verifier
    - Certificate chain validation
    """
    # Placeholder - would query specific anchor
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Trust anchor not found: {anchor_id}",
    )


@router.get(
    "/countries",
    summary="List Supported Countries",
    description="Get list of countries with trust anchors.",
)
async def list_countries(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Get list of countries with trust anchors.
    
    Useful for UI filters and regional sync.
    """
    # Placeholder - would aggregate country codes
    return {
        "countries": [
            {"code": "US", "name": "United States", "anchor_count": 0},
            {"code": "DE", "name": "Germany", "anchor_count": 0},
            {"code": "FR", "name": "France", "anchor_count": 0},
        ],
        "total_anchors": 0,
    }
