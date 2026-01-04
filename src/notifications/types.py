"""
Notification Types

Core types for the notification system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4


class ChannelType(str, Enum):
    """Notification delivery channels."""
    FCM = "fcm"           # Firebase Cloud Messaging (push)
    WEBHOOK = "webhook"   # HTTP callbacks
    EMAIL = "email"       # Email notifications
    SSE = "sse"           # Server-Sent Events (real-time dashboard)
    SMS = "sms"           # SMS (future)


class NotificationPriority(str, Enum):
    """Notification priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class NotificationTarget:
    """
    Target for a notification.
    
    Identifies who/what should receive the notification
    and through which channels.
    """
    # Organization-level targeting
    organization_id: Optional[UUID] = None
    
    # User-level targeting
    user_id: Optional[str] = None
    
    # Device-level targeting (for push)
    device_tokens: list[str] = field(default_factory=list)
    
    # Channel-specific targeting
    webhook_endpoints: list[str] = field(default_factory=list)
    email_addresses: list[str] = field(default_factory=list)
    
    # Channel preferences
    channels: list[ChannelType] = field(default_factory=lambda: [ChannelType.FCM])
    
    def __post_init__(self):
        """Validate target has at least one destination."""
        has_destination = (
            self.organization_id is not None or
            self.user_id is not None or
            self.device_tokens or
            self.webhook_endpoints or
            self.email_addresses
        )
        if not has_destination:
            raise ValueError("NotificationTarget must have at least one destination")


@dataclass
class NotificationPayload:
    """
    Notification content payload.
    
    Contains the actual content to be delivered across channels.
    Each channel adapter may transform this for its specific format.
    """
    # Identity
    id: UUID = field(default_factory=uuid4)
    
    # Content
    title: str = ""
    body: str = ""
    
    # Structured data
    data: dict[str, Any] = field(default_factory=dict)
    
    # Event context
    event_type: str = ""
    
    # Priority
    priority: NotificationPriority = NotificationPriority.NORMAL
    
    # Targeting
    target: Optional[NotificationTarget] = None
    
    # Options
    ttl_seconds: int = 86400  # 24 hours default
    collapse_key: Optional[str] = None  # For collapsing similar notifications
    
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Correlation
    correlation_id: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "title": self.title,
            "body": self.body,
            "data": self.data,
            "event_type": self.event_type,
            "priority": self.priority.value,
            "ttl_seconds": self.ttl_seconds,
            "collapse_key": self.collapse_key,
            "created_at": self.created_at.isoformat(),
            "correlation_id": self.correlation_id,
        }


@dataclass
class DeliveryResult:
    """
    Result of a notification delivery attempt.
    
    Tracks success/failure for each channel.
    """
    # Identity
    notification_id: UUID
    channel: ChannelType
    
    # Status
    success: bool
    
    # Timing
    attempted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    delivered_at: Optional[datetime] = None
    
    # Error info (if failed)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    
    # Retry info
    attempt_number: int = 1
    should_retry: bool = False
    retry_after: Optional[int] = None  # Seconds
    
    # Channel-specific metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "notification_id": str(self.notification_id),
            "channel": self.channel.value,
            "success": self.success,
            "attempted_at": self.attempted_at.isoformat(),
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "attempt_number": self.attempt_number,
            "should_retry": self.should_retry,
            "retry_after": self.retry_after,
            "metadata": self.metadata,
        }


# =============================================================================
# Marty Push Challenge Types
# =============================================================================

MARTY_CHALLENGE_FORMAT = "marty/v1"


@dataclass
class ChallengeOption:
    """
    An option for multi-choice challenges.
    
    Displayed as buttons in the mobile app.
    """
    id: str  # Unique identifier sent in response
    label: str  # Display text for the button
    
    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for serialization."""
        return {"id": self.id, "label": self.label}


@dataclass
class MartyChallengePayload:
    """
    Marty-native push challenge payload (marty/v1 format).
    
    Used for both FCM and SSE delivery. All fields are serialized
    as strings for FCM compatibility.
    """
    # Identity
    challenge_id: str
    device_id: str
    
    # Content
    title: str
    question: str
    
    # Cryptographic
    nonce: str
    signature: str = ""  # Server signature, populated after signing
    
    # Options for multi-choice challenges (displayed as buttons)
    options: list[ChallengeOption] = field(default_factory=list)
    
    # Timing
    ttl_seconds: int = 120
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Optional targeting
    credential_id: Optional[str] = None
    relying_party_id: Optional[str] = None
    
    # Configuration
    require_signature: bool = True
    
    # Additional metadata
    data: dict[str, Any] = field(default_factory=dict)
    
    @property
    def format(self) -> str:
        """Return the format identifier."""
        return MARTY_CHALLENGE_FORMAT
    
    def canonical_string(self) -> str:
        """
        Build canonical string for signature verification.
        
        Format: challenge_id|nonce|device_id|ttl_seconds|created_at|options_json
        """
        import json
        options_json = json.dumps([opt.to_dict() for opt in self.options], separators=(",", ":"))
        return "|".join([
            self.challenge_id,
            self.nonce,
            self.device_id,
            str(self.ttl_seconds),
            self.created_at.isoformat(),
            options_json,
        ])
    
    def to_fcm_data(self) -> dict[str, str]:
        """
        Convert to FCM data payload.
        
        All values are strings per FCM requirements.
        """
        import json
        
        data = {
            "format": self.format,
            "challenge_id": self.challenge_id,
            "device_id": self.device_id,
            "title": self.title,
            "question": self.question,
            "nonce": self.nonce,
            "ttl_seconds": str(self.ttl_seconds),
            "created_at": self.created_at.isoformat(),
            "require_signature": "true" if self.require_signature else "false",
            "signature": self.signature,
        }
        
        # Add options as JSON string
        if self.options:
            data["options"] = json.dumps([opt.to_dict() for opt in self.options], separators=(",", ":"))
        
        # Add optional fields
        if self.credential_id:
            data["credential_id"] = self.credential_id
        if self.relying_party_id:
            data["relying_party_id"] = self.relying_party_id
        
        # Add custom data as JSON string if present
        if self.data:
            data["data"] = json.dumps(self.data, separators=(",", ":"))
        
        return data
    
    def to_notification_payload(self) -> NotificationPayload:
        """Convert to NotificationPayload for delivery via adapters."""
        return NotificationPayload(
            id=UUID(self.challenge_id) if self.challenge_id else uuid4(),
            title=self.title,
            body=self.question,
            event_type="push_challenge",
            data=self.to_fcm_data(),
            ttl_seconds=self.ttl_seconds,
            created_at=self.created_at,
            priority=NotificationPriority.HIGH,
        )
