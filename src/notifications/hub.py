"""
Notification Hub

Central orchestrator for multi-channel notification delivery.
Integrates with MMF messaging for reliable, event-driven processing.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from .device_registry import DeviceRegistry
from .router import NotificationRouter
from .types import ChannelType, DeliveryResult, NotificationPayload, NotificationTarget

logger = logging.getLogger(__name__)


class NotificationHub:
    """
    Central notification orchestrator.
    
    Features:
    - Multi-channel delivery (FCM, webhook, email, SSE)
    - Event-driven processing via MMF messaging
    - Automatic routing based on event type
    - Delivery result tracking
    - Retry support for transient failures
    """
    
    def __init__(
        self,
        router: Optional[NotificationRouter] = None,
        device_registry: Optional[DeviceRegistry] = None,
        consumer: Optional[Any] = None,  # MMF IMessageConsumer
        producer: Optional[Any] = None,  # MMF IMessageProducer
    ):
        """
        Initialize the notification hub.
        
        Args:
            router: Notification router for channel selection
            device_registry: Registry for FCM tokens
            consumer: MMF message consumer for event-driven processing
            producer: MMF message producer for publishing results
        """
        self._router = router or NotificationRouter()
        self._device_registry = device_registry
        self._consumer = consumer
        self._producer = producer
        
        # Channel adapters
        self._adapters: dict[ChannelType, Any] = {}
        
        # Delivery results buffer
        self._results: list[DeliveryResult] = []
        
        # Running state
        self._running = False
    
    def register_adapter(self, channel: ChannelType, adapter: Any) -> None:
        """
        Register a channel adapter.
        
        Args:
            channel: The channel type
            adapter: The adapter instance (FCMAdapter, WebhookAdapter, etc.)
        """
        self._adapters[channel] = adapter
        logger.info(f"Registered adapter for channel: {channel.value}")
    
    async def send(
        self,
        payload: NotificationPayload,
        channels: Optional[list[ChannelType]] = None,
    ) -> list[DeliveryResult]:
        """
        Send a notification.
        
        Args:
            payload: The notification payload
            channels: Optional explicit channels (overrides routing)
            
        Returns:
            List of delivery results for each channel
        """
        # Determine target channels
        if channels is None:
            channels = self._router.route(payload)
        
        if not channels:
            logger.warning(f"No channels determined for notification {payload.id}")
            return []
        
        # Resolve FCM tokens if needed
        if ChannelType.FCM in channels and payload.target:
            await self._resolve_fcm_tokens(payload)
        
        # Send to each channel in parallel
        tasks = []
        for channel in channels:
            if channel in self._adapters:
                tasks.append(self._deliver(channel, payload))
            else:
                logger.warning(f"No adapter registered for channel: {channel.value}")
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        delivery_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                delivery_results.append(DeliveryResult(
                    notification_id=payload.id,
                    channel=channels[i],
                    success=False,
                    error_code="EXCEPTION",
                    error_message=str(result),
                    should_retry=True,
                ))
            elif isinstance(result, DeliveryResult):
                delivery_results.append(result)
        
        # Store results
        self._results.extend(delivery_results)
        
        # Publish delivery results if producer available
        if self._producer:
            await self._publish_results(payload, delivery_results)
        
        return delivery_results
    
    async def _deliver(
        self,
        channel: ChannelType,
        payload: NotificationPayload,
    ) -> DeliveryResult:
        """Deliver to a single channel."""
        adapter = self._adapters[channel]
        
        try:
            result = await adapter.send(payload)
            return result
        except Exception as e:
            logger.error(f"Delivery failed for channel {channel.value}: {e}")
            return DeliveryResult(
                notification_id=payload.id,
                channel=channel,
                success=False,
                error_code="ADAPTER_ERROR",
                error_message=str(e),
                should_retry=True,
            )
    
    async def _resolve_fcm_tokens(self, payload: NotificationPayload) -> None:
        """Resolve FCM tokens from device registry."""
        if not self._device_registry or not payload.target:
            return
        
        if payload.target.device_tokens:
            return  # Already has tokens
        
        tokens = await self._device_registry.get_fcm_tokens(
            user_id=payload.target.user_id,
            organization_id=payload.target.organization_id,
        )
        
        payload.target.device_tokens = tokens
    
    async def _publish_results(
        self,
        payload: NotificationPayload,
        results: list[DeliveryResult],
    ) -> None:
        """Publish delivery results to message queue."""
        if not self._producer:
            return
        
        try:
            message = {
                "notification_id": str(payload.id),
                "event_type": payload.event_type,
                "results": [r.to_dict() for r in results],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
            if hasattr(self._producer, 'send'):
                await self._producer.send(
                    topic="marty.notifications.results",
                    message=message,
                )
            elif hasattr(self._producer, 'publish'):
                await self._producer.publish(
                    topic="marty.notifications.results",
                    message=message,
                )
        except Exception as e:
            logger.error(f"Failed to publish delivery results: {e}")
    
    async def start(self) -> None:
        """
        Start the notification hub in event-driven mode.
        
        Subscribes to domain events and processes them as notifications.
        """
        if not self._consumer:
            logger.warning("No consumer configured - running in direct mode only")
            return
        
        self._running = True
        
        try:
            if hasattr(self._consumer, 'connect'):
                await self._consumer.connect()
            
            # Subscribe to domain events
            topics = [
                "marty.events.credential.*",
                "marty.events.dsc.*",
                "marty.events.subscription.*",
                "marty.events.trust_registry.*",
            ]
            
            for topic in topics:
                if hasattr(self._consumer, 'subscribe'):
                    await self._consumer.subscribe(
                        topic=topic,
                        handler=self._handle_event,
                    )
            
            logger.info("Notification hub started in event-driven mode")
            
            # Keep running
            while self._running:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Notification hub error: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the notification hub."""
        self._running = False
        
        if self._consumer and hasattr(self._consumer, 'close'):
            await self._consumer.close()
        
        # Close all adapters
        for adapter in self._adapters.values():
            if hasattr(adapter, 'close'):
                await adapter.close()
        
        logger.info("Notification hub stopped")
    
    async def _handle_event(self, message: dict) -> None:
        """Handle an incoming domain event."""
        try:
            event_type = message.get("message_type", "")
            event_data = message.get("payload", {})
            
            # Convert event to notification payload
            payload = NotificationPayload(
                title=self._get_event_title(event_type),
                body=self._get_event_body(event_type, event_data),
                event_type=event_type,
                data=event_data,
                correlation_id=message.get("headers", {}).get("correlation_id"),
            )
            
            # Extract target from event
            if "organization_id" in event_data:
                payload.target = NotificationTarget(
                    organization_id=UUID(event_data["organization_id"]),
                )
            
            await self.send(payload)
            
        except Exception as e:
            logger.error(f"Failed to process event: {e}")
    
    def _get_event_title(self, event_type: str) -> str:
        """Get notification title for an event type."""
        titles = {
            "credential.issued": "Credential Issued",
            "credential.revoked": "Credential Revoked",
            "dsc.revoked": "Document Signer Revoked",
            "subscription.created": "Subscription Created",
            "subscription.payment_failed": "Payment Failed",
            "trust_registry.updated": "Trust Registry Updated",
        }
        return titles.get(event_type, "Notification")
    
    def _get_event_body(self, event_type: str, data: dict) -> str:
        """Get notification body for an event."""
        if event_type == "credential.revoked":
            return f"Credential {data.get('credential_id', 'unknown')} has been revoked."
        elif event_type == "dsc.revoked":
            return f"Document Signer from {data.get('country_code', 'unknown')} has been revoked."
        elif event_type == "subscription.payment_failed":
            return "Your payment could not be processed. Please update your payment method."
        elif event_type == "trust_registry.updated":
            return f"Trust registry updated: {data.get('change_type', 'change')}"
        return "You have a new notification."
    
    def get_results(
        self,
        notification_id: Optional[UUID] = None,
        limit: int = 100,
    ) -> list[DeliveryResult]:
        """Get delivery results, optionally filtered by notification ID."""
        results = self._results
        
        if notification_id:
            results = [r for r in results if r.notification_id == notification_id]
        
        return results[-limit:]
