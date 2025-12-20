"""
Notifications Module

Provides a centralized Notification Hub for multi-channel delivery.
Supports FCM, webhooks, email, and SSE channels.
"""
from .adapters import EmailAdapter, FCMAdapter, SSEAdapter, WebhookAdapter
from .device_registry import DeviceRegistration, DeviceRegistry
from .hub import NotificationHub
from .router import NotificationRouter
from .types import (
    ChannelType,
    DeliveryResult,
    NotificationPayload,
    NotificationPriority,
    NotificationTarget,
)

__all__ = [
    # Core
    "NotificationHub",
    "NotificationRouter",
    "DeviceRegistry",
    "DeviceRegistration",
    # Types
    "ChannelType",
    "NotificationPriority",
    "NotificationTarget",
    "NotificationPayload",
    "DeliveryResult",
    # Adapters
    "FCMAdapter",
    "WebhookAdapter",
    "EmailAdapter",
    "SSEAdapter",
]
