"""
Domain Event Publisher

Publishes domain events via MMF messaging infrastructure.
Supports multiple backends (RabbitMQ, Redis, Kafka, NATS, Memory).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from .domain_events import DomainEvent, DomainEventType

logger = logging.getLogger(__name__)


class DomainEventPublisher:
    """
    Publishes domain events to the messaging infrastructure.
    
    Uses MMF IMessageProducer for reliable delivery with:
    - Automatic retries
    - Dead letter queue support
    - Multiple backend options
    """
    
    def __init__(
        self,
        producer: Optional[Any] = None,  # IMessageProducer from MMF
        topic_prefix: str = "marty.events",
    ):
        """
        Initialize the publisher.
        
        Args:
            producer: MMF IMessageProducer instance
            topic_prefix: Prefix for event topics
        """
        self._producer = producer
        self._topic_prefix = topic_prefix
        self._connected = False
        self._pending_events: list[DomainEvent] = []
    
    async def _ensure_connection(self) -> bool:
        """Ensure producer is connected."""
        if self._producer is None:
            logger.warning("No producer configured - events will be buffered")
            return False
        
        if not self._connected:
            try:
                if hasattr(self._producer, 'connect'):
                    await self._producer.connect()
                self._connected = True
                
                # Flush pending events
                if self._pending_events:
                    for event in self._pending_events:
                        await self._do_publish(event)
                    self._pending_events.clear()
                    
            except Exception as e:
                logger.error(f"Failed to connect producer: {e}")
                return False
        
        return True
    
    def _get_topic(self, event: DomainEvent) -> str:
        """
        Get the topic name for an event.
        
        Topics are structured as: {prefix}.{category}.{action}
        e.g., marty.events.credential.revoked
        """
        return f"{self._topic_prefix}.{event.type.value}"
    
    async def publish(self, event: DomainEvent) -> bool:
        """
        Publish a domain event.
        
        Args:
            event: The event to publish
            
        Returns:
            True if published successfully, False otherwise
        """
        if not await self._ensure_connection():
            # Buffer event for later delivery
            self._pending_events.append(event)
            logger.warning(f"Event {event.id} buffered - producer not connected")
            return False
        
        return await self._do_publish(event)
    
    async def _do_publish(self, event: DomainEvent) -> bool:
        """Actually publish the event."""
        topic = self._get_topic(event)
        message = event.to_message()
        
        try:
            if hasattr(self._producer, 'send'):
                await self._producer.send(
                    topic=topic,
                    message=message,
                    key=str(event.organization_id) if event.organization_id else None,
                )
            elif hasattr(self._producer, 'publish'):
                await self._producer.publish(
                    topic=topic,
                    message=message,
                )
            
            logger.debug(f"Published event {event.id} to {topic}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish event {event.id}: {e}")
            # Buffer for retry
            self._pending_events.append(event)
            return False
    
    async def publish_many(self, events: list[DomainEvent]) -> int:
        """
        Publish multiple events.
        
        Args:
            events: List of events to publish
            
        Returns:
            Number of successfully published events
        """
        if not await self._ensure_connection():
            self._pending_events.extend(events)
            return 0
        
        success_count = 0
        for event in events:
            if await self._do_publish(event):
                success_count += 1
        
        return success_count
    
    async def close(self) -> None:
        """Close the producer connection."""
        if self._producer is not None and self._connected:
            try:
                if hasattr(self._producer, 'close'):
                    await self._producer.close()
                elif hasattr(self._producer, 'disconnect'):
                    await self._producer.disconnect()
            except Exception as e:
                logger.error(f"Error closing producer: {e}")
            finally:
                self._connected = False
    
    @property
    def pending_count(self) -> int:
        """Number of pending (unbuffered) events."""
        return len(self._pending_events)


class InMemoryEventPublisher(DomainEventPublisher):
    """
    In-memory event publisher for testing and development.
    
    Stores events in memory and allows inspection.
    """
    
    def __init__(self):
        super().__init__(producer=None, topic_prefix="test.events")
        self._published_events: list[tuple[str, DomainEvent]] = []
        self._subscribers: dict[str, list[Any]] = {}
    
    async def _ensure_connection(self) -> bool:
        return True
    
    async def _do_publish(self, event: DomainEvent) -> bool:
        topic = self._get_topic(event)
        self._published_events.append((topic, event))
        
        # Notify subscribers
        for pattern, callbacks in self._subscribers.items():
            if pattern == "*" or topic.startswith(pattern.rstrip("*")):
                for callback in callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(event)
                        else:
                            callback(event)
                    except Exception as e:
                        logger.error(f"Subscriber error: {e}")
        
        return True
    
    def subscribe(self, pattern: str, callback: Any) -> None:
        """Subscribe to events matching a pattern."""
        if pattern not in self._subscribers:
            self._subscribers[pattern] = []
        self._subscribers[pattern].append(callback)
    
    def get_events(
        self,
        event_type: Optional[DomainEventType] = None,
    ) -> list[DomainEvent]:
        """Get published events, optionally filtered by type."""
        events = [e for _, e in self._published_events]
        if event_type:
            events = [e for e in events if e.type == event_type]
        return events
    
    def clear(self) -> None:
        """Clear all published events."""
        self._published_events.clear()
