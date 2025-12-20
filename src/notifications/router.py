"""
Notification Router

Routes notifications to appropriate channels based on event type and preferences.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .types import ChannelType, NotificationPayload, NotificationPriority

logger = logging.getLogger(__name__)


@dataclass
class RoutingRule:
    """A rule for routing notifications to channels."""
    
    # Match criteria
    event_types: list[str] = field(default_factory=list)  # Empty = match all
    priorities: list[NotificationPriority] = field(default_factory=list)  # Empty = match all
    
    # Target channels
    channels: list[ChannelType] = field(default_factory=list)
    
    # Options
    enabled: bool = True
    
    def matches(self, payload: NotificationPayload) -> bool:
        """Check if this rule matches the payload."""
        if not self.enabled:
            return False
        
        # Check event type
        if self.event_types and payload.event_type not in self.event_types:
            return False
        
        # Check priority
        if self.priorities and payload.priority not in self.priorities:
            return False
        
        return True


class NotificationRouter:
    """
    Routes notifications to appropriate channels.
    
    Features:
    - Event-type based routing
    - Priority-based channel selection
    - User preference override
    - Fallback routing
    """
    
    # Default routing rules
    DEFAULT_RULES: list[RoutingRule] = [
        # Critical events go to all channels
        RoutingRule(
            priorities=[NotificationPriority.CRITICAL],
            channels=[ChannelType.FCM, ChannelType.WEBHOOK, ChannelType.EMAIL],
        ),
        # High priority events go to push and webhook
        RoutingRule(
            priorities=[NotificationPriority.HIGH],
            channels=[ChannelType.FCM, ChannelType.WEBHOOK],
        ),
        # Credential revocation events
        RoutingRule(
            event_types=["credential.revoked", "dsc.revoked", "csca.revoked"],
            channels=[ChannelType.FCM, ChannelType.WEBHOOK, ChannelType.SSE],
        ),
        # Trust registry updates go to SSE for real-time dashboard
        RoutingRule(
            event_types=["trust_registry.updated"],
            channels=[ChannelType.SSE, ChannelType.WEBHOOK],
        ),
        # Subscription events go to email and webhook
        RoutingRule(
            event_types=[
                "subscription.created",
                "subscription.canceled",
                "subscription.upgraded",
                "subscription.payment_failed",
            ],
            channels=[ChannelType.EMAIL, ChannelType.WEBHOOK],
        ),
        # API key events go to webhook and SSE
        RoutingRule(
            event_types=["api_key.created", "api_key.revoked"],
            channels=[ChannelType.WEBHOOK, ChannelType.SSE],
        ),
        # Default: push notifications
        RoutingRule(
            event_types=[],  # Match all
            channels=[ChannelType.FCM],
        ),
    ]
    
    def __init__(
        self,
        rules: Optional[list[RoutingRule]] = None,
        default_channels: Optional[list[ChannelType]] = None,
    ):
        """
        Initialize the router.
        
        Args:
            rules: Custom routing rules (appended to defaults)
            default_channels: Fallback channels if no rules match
        """
        self._rules = list(self.DEFAULT_RULES)
        if rules:
            self._rules.extend(rules)
        
        self._default_channels = default_channels or [ChannelType.FCM]
    
    def route(self, payload: NotificationPayload) -> list[ChannelType]:
        """
        Determine which channels to use for a notification.
        
        Args:
            payload: The notification payload
            
        Returns:
            List of channels to deliver to
        """
        channels: set[ChannelType] = set()
        
        # Check explicit target channels first
        if payload.target and payload.target.channels:
            channels.update(payload.target.channels)
        else:
            # Apply routing rules
            for rule in self._rules:
                if rule.matches(payload):
                    channels.update(rule.channels)
                    break  # Use first matching rule
        
        # Fallback to defaults
        if not channels:
            channels.update(self._default_channels)
        
        # Apply target-specific filtering
        if payload.target:
            # If no FCM tokens, remove FCM channel
            if ChannelType.FCM in channels and not payload.target.device_tokens:
                # Don't remove if we can look up tokens by user/org
                if not payload.target.user_id and not payload.target.organization_id:
                    channels.discard(ChannelType.FCM)
            
            # If no webhook endpoints, remove webhook channel
            if ChannelType.WEBHOOK in channels and not payload.target.webhook_endpoints:
                if not payload.target.organization_id:
                    channels.discard(ChannelType.WEBHOOK)
            
            # If no email addresses, remove email channel
            if ChannelType.EMAIL in channels and not payload.target.email_addresses:
                if not payload.target.user_id:
                    channels.discard(ChannelType.EMAIL)
        
        logger.debug(
            f"Routed notification {payload.id} ({payload.event_type}) "
            f"to channels: {[c.value for c in channels]}"
        )
        
        return list(channels)
    
    def add_rule(self, rule: RoutingRule) -> None:
        """Add a routing rule (takes precedence over existing rules)."""
        self._rules.insert(0, rule)
    
    def remove_rule(self, event_type: str) -> bool:
        """Remove rules matching an event type."""
        original_count = len(self._rules)
        self._rules = [
            r for r in self._rules
            if event_type not in r.event_types
        ]
        return len(self._rules) < original_count
    
    def get_rules(self) -> list[RoutingRule]:
        """Get all routing rules."""
        return list(self._rules)
