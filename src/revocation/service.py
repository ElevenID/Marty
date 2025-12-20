"""
Revocation Service

Handles credential and trust anchor revocation with configurable cascade policies.
Supports format-per-credential-type (TSL for mDoc, Bitstring for SD-JWT VC).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from .status_list_manager import StatusListFormat, StatusListManager

logger = logging.getLogger(__name__)


class RevocationReason(str, Enum):
    """Standard revocation reasons."""
    UNSPECIFIED = "unspecified"
    KEY_COMPROMISE = "key_compromise"
    CA_COMPROMISE = "ca_compromise"
    AFFILIATION_CHANGED = "affiliation_changed"
    SUPERSEDED = "superseded"
    CESSATION_OF_OPERATION = "cessation_of_operation"
    CERTIFICATE_HOLD = "certificate_hold"
    PRIVILEGE_WITHDRAWN = "privilege_withdrawn"


class CascadePolicy(str, Enum):
    """
    Policy for cascading trust anchor revocation to credentials.
    
    AUTO_CASCADE: Automatically revoke all credentials signed by the anchor
    MANUAL: Require manual review of each credential
    NOTIFY_ONLY: Only notify affected parties, don't auto-revoke
    """
    AUTO_CASCADE = "auto_cascade"
    MANUAL = "manual"
    NOTIFY_ONLY = "notify_only"


@dataclass
class RevocationResult:
    """Result of a revocation operation."""
    success: bool
    credential_id: Optional[str] = None
    status_list_index: Optional[int] = None
    revoked_at: Optional[datetime] = None
    error: Optional[str] = None
    affected_count: int = 0


@dataclass
class TrustAnchorRevocationResult:
    """Result of a trust anchor revocation."""
    success: bool
    anchor_id: str
    anchor_type: str  # "dsc" or "csca"
    reason: RevocationReason
    cascade_policy: CascadePolicy
    affected_credentials: int = 0
    auto_revoked: int = 0
    pending_review: int = 0
    revoked_at: Optional[datetime] = None
    error: Optional[str] = None


class RevocationService:
    """
    Credential and trust anchor revocation service.
    
    Features:
    - Format-per-credential-type (TSL for mDoc, Bitstring for SD-JWT VC)
    - Configurable cascade policies for trust anchor revocation
    - Event publishing for downstream notification
    """
    
    def __init__(
        self,
        status_list_manager: StatusListManager,
        event_publisher: Optional[Any] = None,  # DomainEventPublisher
        default_cascade_policy: CascadePolicy = CascadePolicy.NOTIFY_ONLY,
    ):
        """
        Initialize the revocation service.
        
        Args:
            status_list_manager: Manager for status lists
            event_publisher: Optional event publisher for notifications
            default_cascade_policy: Default policy for trust anchor revocation
        """
        self._status_manager = status_list_manager
        self._event_publisher = event_publisher
        self._default_cascade_policy = default_cascade_policy
    
    async def revoke_credential(
        self,
        credential_id: str,
        credential_type: str,
        reason: RevocationReason = RevocationReason.UNSPECIFIED,
        issuer_id: Optional[str] = None,
        organization_id: Optional[UUID] = None,
    ) -> RevocationResult:
        """
        Revoke a single credential.
        
        Args:
            credential_id: The credential identifier
            credential_type: "mdoc" or "sd_jwt_vc"
            reason: Revocation reason
            issuer_id: Optional issuer identifier for list selection
            organization_id: Optional organization for event context
            
        Returns:
            RevocationResult with status list index
        """
        try:
            # Determine format based on credential type
            if credential_type == "mdoc":
                format_type = StatusListFormat.TOKEN_STATUS_LIST
            elif credential_type == "sd_jwt_vc":
                format_type = StatusListFormat.BITSTRING_STATUS_LIST
            else:
                return RevocationResult(
                    success=False,
                    credential_id=credential_id,
                    error=f"Unknown credential type: {credential_type}",
                )
            
            # Set status in appropriate list
            status_index = await self._status_manager.set_status(
                credential_id=credential_id,
                status=0x01,  # Revoked
                format_type=format_type,
                issuer_id=issuer_id,
            )
            
            now = datetime.now(timezone.utc)
            
            # Publish event if publisher available
            if self._event_publisher:
                await self._publish_credential_revoked(
                    credential_id=credential_id,
                    credential_type=credential_type,
                    reason=reason,
                    status_list_index=status_index,
                    organization_id=organization_id,
                )
            
            logger.info(
                f"Revoked credential {credential_id} "
                f"(type={credential_type}, index={status_index})"
            )
            
            return RevocationResult(
                success=True,
                credential_id=credential_id,
                status_list_index=status_index,
                revoked_at=now,
            )
            
        except Exception as e:
            logger.error(f"Failed to revoke credential {credential_id}: {e}")
            return RevocationResult(
                success=False,
                credential_id=credential_id,
                error=str(e),
            )
    
    async def revoke_trust_anchor(
        self,
        anchor_id: str,
        anchor_type: str,  # "dsc" or "csca"
        reason: RevocationReason,
        cascade_policy: Optional[CascadePolicy] = None,
        affected_credential_ids: Optional[list[str]] = None,
    ) -> TrustAnchorRevocationResult:
        """
        Revoke a trust anchor (DSC or CSCA).
        
        Args:
            anchor_id: The trust anchor identifier
            anchor_type: "dsc" or "csca"
            reason: Revocation reason
            cascade_policy: Policy for handling affected credentials
            affected_credential_ids: List of credential IDs signed by this anchor
            
        Returns:
            TrustAnchorRevocationResult with cascade statistics
        """
        policy = cascade_policy or self._default_cascade_policy
        affected_ids = affected_credential_ids or []
        
        try:
            now = datetime.now(timezone.utc)
            auto_revoked = 0
            pending_review = 0
            
            # Process based on cascade policy
            if policy == CascadePolicy.AUTO_CASCADE:
                # Automatically revoke all affected credentials
                for cred_id in affected_ids:
                    result = await self.revoke_credential(
                        credential_id=cred_id,
                        credential_type="mdoc",  # DSCs typically sign mDocs
                        reason=RevocationReason.CA_COMPROMISE if anchor_type == "csca" else RevocationReason.KEY_COMPROMISE,
                    )
                    if result.success:
                        auto_revoked += 1
                        
            elif policy == CascadePolicy.MANUAL:
                # Mark credentials for manual review
                pending_review = len(affected_ids)
                # In a real implementation, this would create review tasks
                
            elif policy == CascadePolicy.NOTIFY_ONLY:
                # Just count affected credentials
                pass
            
            # Publish trust anchor revocation event
            if self._event_publisher:
                await self._publish_anchor_revoked(
                    anchor_id=anchor_id,
                    anchor_type=anchor_type,
                    reason=reason,
                    cascade_policy=policy,
                    affected_count=len(affected_ids),
                )
            
            logger.info(
                f"Revoked {anchor_type} {anchor_id} "
                f"(policy={policy.value}, affected={len(affected_ids)}, auto_revoked={auto_revoked})"
            )
            
            return TrustAnchorRevocationResult(
                success=True,
                anchor_id=anchor_id,
                anchor_type=anchor_type,
                reason=reason,
                cascade_policy=policy,
                affected_credentials=len(affected_ids),
                auto_revoked=auto_revoked,
                pending_review=pending_review,
                revoked_at=now,
            )
            
        except Exception as e:
            logger.error(f"Failed to revoke {anchor_type} {anchor_id}: {e}")
            return TrustAnchorRevocationResult(
                success=False,
                anchor_id=anchor_id,
                anchor_type=anchor_type,
                reason=reason,
                cascade_policy=policy,
                error=str(e),
            )
    
    async def check_revocation_status(
        self,
        credential_id: str,
        credential_type: str,
        issuer_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Check the revocation status of a credential.
        
        Args:
            credential_id: The credential identifier
            credential_type: "mdoc" or "sd_jwt_vc"
            issuer_id: Optional issuer identifier
            
        Returns:
            Status information including revoked flag
        """
        try:
            if credential_type == "mdoc":
                format_type = StatusListFormat.TOKEN_STATUS_LIST
            elif credential_type == "sd_jwt_vc":
                format_type = StatusListFormat.BITSTRING_STATUS_LIST
            else:
                return {
                    "credential_id": credential_id,
                    "error": f"Unknown credential type: {credential_type}",
                }
            
            status = await self._status_manager.get_status(
                credential_id=credential_id,
                format_type=format_type,
                issuer_id=issuer_id,
            )
            
            return {
                "credential_id": credential_id,
                "credential_type": credential_type,
                "revoked": status == 0x01,
                "status_code": status,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            
        except Exception as e:
            return {
                "credential_id": credential_id,
                "error": str(e),
            }
    
    async def bulk_revoke(
        self,
        credentials: list[dict[str, Any]],
        reason: RevocationReason = RevocationReason.UNSPECIFIED,
        organization_id: Optional[UUID] = None,
    ) -> list[RevocationResult]:
        """
        Revoke multiple credentials in bulk.
        
        Args:
            credentials: List of {"credential_id": str, "credential_type": str}
            reason: Revocation reason for all
            organization_id: Optional organization context
            
        Returns:
            List of RevocationResult for each credential
        """
        results = []
        
        for cred in credentials:
            result = await self.revoke_credential(
                credential_id=cred["credential_id"],
                credential_type=cred["credential_type"],
                reason=reason,
                organization_id=organization_id,
            )
            results.append(result)
        
        success_count = sum(1 for r in results if r.success)
        logger.info(
            f"Bulk revocation completed: {success_count}/{len(credentials)} successful"
        )
        
        return results
    
    async def _publish_credential_revoked(
        self,
        credential_id: str,
        credential_type: str,
        reason: RevocationReason,
        status_list_index: int,
        organization_id: Optional[UUID],
    ) -> None:
        """Publish credential revoked event."""
        if not self._event_publisher:
            return
        
        try:
            from ..events.domain_events import credential_revoked
            
            event = credential_revoked(
                credential_id=credential_id,
                reason=reason.value,
                organization_id=organization_id,
                status_list_index=status_list_index,
                credential_type=credential_type,
            )
            
            await self._event_publisher.publish(event)
            
        except Exception as e:
            logger.error(f"Failed to publish credential revoked event: {e}")
    
    async def _publish_anchor_revoked(
        self,
        anchor_id: str,
        anchor_type: str,
        reason: RevocationReason,
        cascade_policy: CascadePolicy,
        affected_count: int,
    ) -> None:
        """Publish trust anchor revoked event."""
        if not self._event_publisher:
            return
        
        try:
            from ..events.domain_events import dsc_revoked
            
            event = dsc_revoked(
                dsc_id=anchor_id,
                country_code="",  # Would be populated from anchor data
                reason=reason.value,
                cascade_policy=cascade_policy.value,
                affected_credentials=affected_count,
            )
            
            await self._event_publisher.publish(event)
            
        except Exception as e:
            logger.error(f"Failed to publish anchor revoked event: {e}")
