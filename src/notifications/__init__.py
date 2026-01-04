"""
Notifications Module

Provides a centralized Notification Hub for multi-channel delivery.
Supports FCM, webhooks, email, and SSE channels.

The module includes two notification systems:
1. Legacy NotificationHub - the original multi-channel notification system
2. New MMF-based push framework - generic push infrastructure with Marty integration

For new code, prefer using MartyChallengeNotifier with the MMF push framework.
"""
from .adapters import EmailAdapter, FCMAdapter, SSEAdapter, WebhookAdapter
from .device_registry import DeviceRegistration, DeviceRegistry
from .hub import NotificationHub
from .router import NotificationRouter
from .types import (
    ChannelType,
    ChallengeOption,
    DeliveryResult,
    MartyChallengePayload,
    NotificationPayload,
    NotificationPriority,
    NotificationTarget,
)

# New MMF-integrated components
from .challenge_notifier import (
    ChallengeDeliveryResult,
    MartyChallengeNotifier,
    MockMartyChallengeNotifier,
)
from .registry_adapter import (
    DeviceRegistryLifecycleHandler,
    DeviceRegistryTokenStore,
    create_push_infrastructure,
)
from .signing import ChallengeSigner

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
    "ChallengeOption",
    "MartyChallengePayload",
    # Adapters (legacy)
    "FCMAdapter",
    "WebhookAdapter",
    "EmailAdapter",
    "SSEAdapter",
    # Challenge Notifier (new MMF-based)
    "MartyChallengeNotifier",
    "MockMartyChallengeNotifier",
    "ChallengeDeliveryResult",
    "ChallengeSigner",
    # MMF Integration
    "DeviceRegistryTokenStore",
    "DeviceRegistryLifecycleHandler",
    "create_push_infrastructure",
]
