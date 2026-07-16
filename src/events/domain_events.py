"""
Domain Events

Typed domain events for the Marty platform.
These events are published via MMF messaging infrastructure.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4


class DomainEventType(str, Enum):
    """All domain event types in the system."""
    
    # Credential events
    CREDENTIAL_ISSUED = "credential.issued"
    CREDENTIAL_REVOKED = "credential.revoked"
    CREDENTIAL_VERIFIED = "credential.verified"
    CREDENTIAL_EXPIRED = "credential.expired"
    
    # Trust anchor events
    DSC_ADDED = "dsc.added"
    DSC_REVOKED = "dsc.revoked"
    DSC_EXPIRED = "dsc.expired"
    CSCA_ADDED = "csca.added"
    CSCA_REVOKED = "csca.revoked"
    
    # API key events
    API_KEY_CREATED = "api_key.created"
    API_KEY_REVOKED = "api_key.revoked"
    API_KEY_RATE_LIMITED = "api_key.rate_limited"
    
    # Organization events
    ORGANIZATION_CREATED = "organization.created"
    
    # Trust registry events
    TRUST_REGISTRY_UPDATED = "trust_registry.updated"


@dataclass
class DomainEvent:
    """
    A domain event in the system.
    
    Events are immutable and contain all context needed
    for downstream consumers to process them.
    """
    
    # Event identity
    id: UUID = field(default_factory=uuid4)
    type: DomainEventType = field(default=DomainEventType.CREDENTIAL_ISSUED)
    
    # Event timing
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Actor context
    organization_id: Optional[UUID] = None
    user_id: Optional[str] = None
    
    # Event payload
    payload: dict[str, Any] = field(default_factory=dict)
    
    # Correlation for distributed tracing
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    
    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "id": str(self.id),
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "organization_id": str(self.organization_id) if self.organization_id else None,
            "user_id": self.user_id,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "metadata": self.metadata,
        }
    
    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DomainEvent":
        """Create event from dictionary."""
        return cls(
            id=UUID(data["id"]),
            type=DomainEventType(data["type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            organization_id=UUID(data["organization_id"]) if data.get("organization_id") else None,
            user_id=data.get("user_id"),
            payload=data.get("payload", {}),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            metadata=data.get("metadata", {}),
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "DomainEvent":
        """Create event from JSON string."""
        return cls.from_dict(json.loads(json_str))
    
    def to_message(self) -> dict[str, Any]:
        """
        Convert to MMF Message format.
        
        This allows seamless integration with the MMF messaging infrastructure.
        """
        return {
            "message_id": str(self.id),
            "message_type": self.type.value,
            "payload": self.to_dict(),
            "headers": {
                "correlation_id": self.correlation_id or str(self.id),
                "content_type": "application/json",
                "source": "marty-events",
            },
            "timestamp": self.timestamp,
            "priority": self._get_priority(),
        }
    
    def _get_priority(self) -> int:
        """Determine message priority based on event type."""
        high_priority = {
            DomainEventType.CREDENTIAL_REVOKED,
            DomainEventType.DSC_REVOKED,
            DomainEventType.CSCA_REVOKED,
            DomainEventType.API_KEY_RATE_LIMITED,
        }
        
        if self.type in high_priority:
            return 10  # High priority
        return 5  # Normal priority


# Factory functions for common events
def credential_issued(
    credential_id: str,
    credential_type: str,
    subject_id: str,
    organization_id: UUID,
    issuer_did: str,
    **kwargs: Any,
) -> DomainEvent:
    """Create a credential issued event."""
    return DomainEvent(
        type=DomainEventType.CREDENTIAL_ISSUED,
        organization_id=organization_id,
        payload={
            "credential_id": credential_id,
            "credential_type": credential_type,
            "subject_id": subject_id,
            "issuer_did": issuer_did,
            **kwargs,
        },
    )


def credential_revoked(
    credential_id: str,
    reason: str,
    organization_id: UUID,
    status_list_index: Optional[int] = None,
    **kwargs: Any,
) -> DomainEvent:
    """Create a credential revoked event."""
    return DomainEvent(
        type=DomainEventType.CREDENTIAL_REVOKED,
        organization_id=organization_id,
        payload={
            "credential_id": credential_id,
            "reason": reason,
            "status_list_index": status_list_index,
            **kwargs,
        },
    )


def dsc_revoked(
    dsc_id: str,
    country_code: str,
    reason: str,
    cascade_policy: str,
    affected_credentials: int = 0,
    **kwargs: Any,
) -> DomainEvent:
    """Create a DSC revoked event."""
    return DomainEvent(
        type=DomainEventType.DSC_REVOKED,
        payload={
            "dsc_id": dsc_id,
            "country_code": country_code,
            "reason": reason,
            "cascade_policy": cascade_policy,
            "affected_credentials": affected_credentials,
            **kwargs,
        },
    )


def trust_registry_updated(
    change_type: str,
    anchor_id: str,
    anchor_type: str,
    **kwargs: Any,
) -> DomainEvent:
    """Create a trust registry updated event."""
    return DomainEvent(
        type=DomainEventType.TRUST_REGISTRY_UPDATED,
        payload={
            "change_type": change_type,
            "anchor_id": anchor_id,
            "anchor_type": anchor_type,
            **kwargs,
        },
    )
