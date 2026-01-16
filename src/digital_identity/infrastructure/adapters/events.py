"""
Event Publisher Adapter for Digital Identity Module

Wraps the existing DomainEventPublisher to implement EventPublisherPort.
Converts Digital Identity domain events to the Marty messaging format.
"""

from __future__ import annotations

import logging
from typing import Any

from digital_identity.application.ports.outbound import EventPublisherPort
from digital_identity.domain.events import (
    DomainEvent,
    TrustProfileCreated,
    TrustProfileUpdated,
    TrustProfileDeleted,
    CredentialTemplateCreated,
    CredentialTemplateUpdated,
    CredentialTemplateDeleted,
    PresentationPolicyCreated,
    PresentationPolicyUpdated,
    PresentationPolicyDeleted,
    DeploymentProfileCreated,
    DeploymentProfileUpdated,
    DeploymentProfileDeleted,
    FlowCreated,
    FlowUpdated,
    FlowDeleted,
    FlowExecutionStarted,
    FlowExecutionStepCompleted,
    FlowExecutionCompleted,
    FlowExecutionFailed,
)

logger = logging.getLogger(__name__)


class DigitalIdentityEventPublisher:
    """
    Event publisher adapter for Digital Identity domain events.
    
    Implements the EventPublisherPort interface and delegates to the
    underlying Marty DomainEventPublisher.
    """
    
    # Map event types to topic suffixes
    EVENT_TOPICS = {
        "TrustProfileCreated": "digital_identity.trust_profile.created",
        "TrustProfileUpdated": "digital_identity.trust_profile.updated",
        "TrustProfileDeleted": "digital_identity.trust_profile.deleted",
        "CredentialTemplateCreated": "digital_identity.credential_template.created",
        "CredentialTemplateUpdated": "digital_identity.credential_template.updated",
        "CredentialTemplateDeleted": "digital_identity.credential_template.deleted",
        "PresentationPolicyCreated": "digital_identity.presentation_policy.created",
        "PresentationPolicyUpdated": "digital_identity.presentation_policy.updated",
        "PresentationPolicyDeleted": "digital_identity.presentation_policy.deleted",
        "DeploymentProfileCreated": "digital_identity.deployment_profile.created",
        "DeploymentProfileUpdated": "digital_identity.deployment_profile.updated",
        "DeploymentProfileDeleted": "digital_identity.deployment_profile.deleted",
        "FlowCreated": "digital_identity.flow.created",
        "FlowUpdated": "digital_identity.flow.updated",
        "FlowDeleted": "digital_identity.flow.deleted",
        "FlowExecutionStarted": "digital_identity.flow_execution.started",
        "FlowExecutionStepCompleted": "digital_identity.flow_execution.step_completed",
        "FlowExecutionCompleted": "digital_identity.flow_execution.completed",
        "FlowExecutionFailed": "digital_identity.flow_execution.failed",
    }
    
    def __init__(
        self,
        publisher: Any | None = None,
        topic_prefix: str = "marty.events",
    ):
        """
        Initialize the event publisher adapter.
        
        Args:
            publisher: Underlying DomainEventPublisher from events module
            topic_prefix: Prefix for event topics
        """
        self._publisher = publisher
        self._topic_prefix = topic_prefix
        self._buffered_events: list[DomainEvent] = []
    
    def _get_topic(self, event: DomainEvent) -> str:
        """Get the full topic name for an event."""
        event_type = type(event).__name__
        suffix = self.EVENT_TOPICS.get(event_type, f"digital_identity.{event_type.lower()}")
        return f"{self._topic_prefix}.{suffix}"
    
    def _convert_to_message(self, event: DomainEvent) -> dict[str, Any]:
        """Convert domain event to message format."""
        return {
            "event_id": str(event.event_id),
            "event_type": type(event).__name__,
            "timestamp": event.timestamp.isoformat(),
            "entity_id": str(event.entity_id),
            "entity_type": event.entity_type,
            "data": event.data,
        }
    
    async def publish(self, event: DomainEvent) -> bool:
        """
        Publish a domain event.
        
        Args:
            event: The domain event to publish
            
        Returns:
            True if published successfully
        """
        if self._publisher is None:
            # Buffer events when no publisher configured
            self._buffered_events.append(event)
            logger.warning(f"Event {event.event_id} buffered - no publisher configured")
            return False
        
        topic = self._get_topic(event)
        message = self._convert_to_message(event)
        
        try:
            if hasattr(self._publisher, 'send'):
                await self._publisher.send(topic=topic, message=message)
            elif hasattr(self._publisher, 'publish'):
                await self._publisher.publish(topic=topic, message=message)
            else:
                logger.error("Publisher has no send/publish method")
                return False
            
            logger.debug(f"Published event {event.event_id} to {topic}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish event {event.event_id}: {e}")
            self._buffered_events.append(event)
            return False
    
    async def publish_many(self, events: list[DomainEvent]) -> int:
        """
        Publish multiple events.
        
        Args:
            events: List of events to publish
            
        Returns:
            Number of successfully published events
        """
        success_count = 0
        for event in events:
            if await self.publish(event):
                success_count += 1
        return success_count
    
    async def flush_buffered(self) -> int:
        """
        Attempt to publish all buffered events.
        
        Returns:
            Number of successfully published events
        """
        if not self._buffered_events:
            return 0
        
        events = self._buffered_events.copy()
        self._buffered_events.clear()
        
        return await self.publish_many(events)
    
    @property
    def buffered_count(self) -> int:
        """Number of buffered (unpublished) events."""
        return len(self._buffered_events)


class InMemoryEventPublisher:
    """
    In-memory event publisher for testing and development.
    
    Stores all published events for inspection.
    """
    
    def __init__(self):
        """Initialize in-memory publisher."""
        self.events: list[tuple[str, DomainEvent]] = []
        self._subscribers: dict[str, list] = {}
    
    async def publish(self, event: DomainEvent) -> bool:
        """Store event in memory."""
        event_type = type(event).__name__
        self.events.append((event_type, event))
        
        # Notify subscribers
        for subscriber in self._subscribers.get(event_type, []):
            try:
                await subscriber(event)
            except Exception as e:
                logger.error(f"Subscriber error: {e}")
        
        logger.debug(f"Published event {event.event_id} (in-memory)")
        return True
    
    async def publish_many(self, events: list[DomainEvent]) -> int:
        """Publish multiple events."""
        for event in events:
            await self.publish(event)
        return len(events)
    
    def subscribe(self, event_type: str, handler) -> None:
        """Subscribe to events of a specific type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
    
    def get_events_by_type(self, event_type: str) -> list[DomainEvent]:
        """Get all events of a specific type."""
        return [event for etype, event in self.events if etype == event_type]
    
    def get_events_for_entity(self, entity_id: str) -> list[DomainEvent]:
        """Get all events for a specific entity."""
        return [event for _, event in self.events if str(event.entity_id) == entity_id]
    
    def clear(self) -> None:
        """Clear all stored events."""
        self.events.clear()
    
    @property
    def buffered_count(self) -> int:
        """Compatibility with EventPublisherPort."""
        return 0


def create_event_publisher(
    producer: Any | None = None,
    use_memory: bool = False,
) -> DigitalIdentityEventPublisher | InMemoryEventPublisher:
    """
    Factory function to create an event publisher.
    
    Args:
        producer: Optional message producer from MMF
        use_memory: If True, use in-memory publisher (for testing)
        
    Returns:
        Event publisher instance
    """
    if use_memory:
        return InMemoryEventPublisher()
    
    return DigitalIdentityEventPublisher(publisher=producer)
