"""
Device Registry MMF Adapter

Adapts Marty's DeviceRegistry to implement MMF's push notification
interfaces: IDeviceTokenStore and ITokenLifecycleHandler.

This adapter bridges the Marty-specific persistence layer with
the generic MMF push framework.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

# Import from MMF push framework
try:
    from mmf.core.push import (
        IDeviceTokenStore,
        PushChannel,
    )
    from mmf.framework.push.lifecycle import (
        ITokenLifecycleHandler,
        TokenInvalidationEvent,
        TokenRegistrationEvent,
    )
except ImportError:
    # Fallback for when running outside the monorepo
    from marty_microservices_framework.mmf.core.push import (
        IDeviceTokenStore,
        PushChannel,
    )
    from marty_microservices_framework.mmf.framework.push.lifecycle import (
        ITokenLifecycleHandler,
        TokenInvalidationEvent,
        TokenRegistrationEvent,
    )

from .device_registry import DeviceRegistry, DeviceInfo

logger = logging.getLogger(__name__)


class DeviceRegistryTokenStore:
    """
    Adapter that implements MMF's IDeviceTokenStore using Marty's DeviceRegistry.
    
    This allows the MMF PushManager to look up device tokens by user
    when sending push notifications.
    
    Usage:
        registry = DeviceRegistry(db_session)
        token_store = DeviceRegistryTokenStore(registry)
        
        push_manager = PushManager(token_store=token_store)
    """
    
    def __init__(self, registry: DeviceRegistry):
        """
        Initialize the token store adapter.
        
        Args:
            registry: Marty DeviceRegistry instance
        """
        self._registry = registry
    
    async def get_tokens_for_user(self, user_id: str) -> list[str]:
        """
        Get all FCM tokens for a user.
        
        Implements IDeviceTokenStore.get_tokens_for_user
        
        Args:
            user_id: User identifier
            
        Returns:
            List of FCM tokens
        """
        return await self._registry.get_fcm_tokens(user_id=user_id)
    
    async def get_tokens_for_device(self, device_id: str) -> list[str]:
        """
        Get tokens for a specific device.
        
        Implements IDeviceTokenStore.get_tokens_for_device
        
        Args:
            device_id: Device identifier
            
        Returns:
            List of FCM tokens (typically one)
        """
        registration = await self._registry.get_device_by_id(device_id)
        if registration and registration.is_active:
            return [registration.fcm_token]
        return []
    
    async def store_token(
        self,
        token: str,
        device_id: str,
        user_id: str | None = None,
        channel: PushChannel = PushChannel.FCM,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Store a device token.
        
        Implements IDeviceTokenStore.store_token
        
        Note: This creates a minimal registration. For full device
        registration with metadata, use DeviceRegistry.register_device directly.
        
        Args:
            token: FCM token
            device_id: Device identifier
            user_id: User identifier (required for Marty)
            channel: Push channel (only FCM supported)
            metadata: Optional metadata
        """
        if not user_id:
            logger.warning("store_token called without user_id, token not stored")
            return
        
        if channel != PushChannel.FCM:
            logger.warning(f"store_token called with unsupported channel {channel}")
            return
        
        device_info = DeviceInfo(
            device_id=device_id,
            platform=metadata.get("platform", "unknown") if metadata else "unknown",
            fcm_token=token,
            app_version=metadata.get("app_version") if metadata else None,
            os_version=metadata.get("os_version") if metadata else None,
            device_model=metadata.get("device_model") if metadata else None,
        )
        
        await self._registry.register_device(
            user_id=user_id,
            device_info=device_info,
        )
    
    async def remove_token(self, token: str) -> None:
        """
        Remove a device token.
        
        Implements IDeviceTokenStore.remove_token
        
        Note: This marks the device as inactive rather than deleting.
        
        Args:
            token: FCM token to remove
        """
        await self._registry.mark_token_invalid(token)
    
    async def mark_token_invalid(
        self,
        token: str,
        reason: str | None = None,
    ) -> None:
        """
        Mark a token as invalid.
        
        Implements IDeviceTokenStore.mark_token_invalid
        
        Args:
            token: FCM token to invalidate
            reason: Optional reason for invalidation
        """
        logger.info(f"Marking token invalid: reason={reason}")
        await self._registry.mark_token_invalid(token)


class DeviceRegistryLifecycleHandler:
    """
    Adapter that implements MMF's ITokenLifecycleHandler using Marty's DeviceRegistry.
    
    Handles token lifecycle events from the push framework:
    - Token registration
    - Token invalidation
    - Token refresh
    
    Usage:
        registry = DeviceRegistry(db_session)
        lifecycle_handler = DeviceRegistryLifecycleHandler(registry)
        
        fcm_adapter = FCMAdapter(config, lifecycle_handler=lifecycle_handler)
    """
    
    def __init__(
        self,
        registry: DeviceRegistry,
        audit_logger: Any | None = None,
    ):
        """
        Initialize the lifecycle handler.
        
        Args:
            registry: Marty DeviceRegistry instance
            audit_logger: Optional audit logger for lifecycle events
        """
        self._registry = registry
        self._audit_logger = audit_logger
    
    async def on_token_registered(
        self,
        event: TokenRegistrationEvent,
    ) -> None:
        """
        Handle a new token registration.
        
        Implements ITokenLifecycleHandler.on_token_registered
        
        Args:
            event: Token registration event
        """
        logger.info(
            f"Token registered: device_id={event.device_id}, "
            f"channel={event.channel.value}"
        )
        
        if self._audit_logger:
            await self._audit_logger.log(
                event_type="push.token.registered",
                device_id=event.device_id,
                user_id=event.user_id,
                channel=event.channel.value,
            )
        
        # Note: Registration is typically done through the full DeviceRegistry
        # flow which includes user authentication and device info.
        # This handler is mainly for audit/observability.
    
    async def on_token_invalidated(
        self,
        event: TokenInvalidationEvent,
    ) -> None:
        """
        Handle a token invalidation.
        
        Implements ITokenLifecycleHandler.on_token_invalidated
        
        Called when FCM reports a token is no longer valid.
        
        Args:
            event: Token invalidation event
        """
        logger.info(
            f"Token invalidated: reason={event.reason.value}, "
            f"device_id={event.device_id}, channel={event.channel.value}"
        )
        
        # Mark the token as invalid in the registry
        await self._registry.mark_token_invalid(event.token)
        
        # Audit log
        if self._audit_logger:
            await self._audit_logger.log(
                event_type="push.token.invalidated",
                device_id=event.device_id,
                user_id=event.user_id,
                reason=event.reason.value,
                error_code=event.error_code,
            )
    
    async def on_token_refreshed(
        self,
        old_token: str,
        new_token: str,
        device_id: str,
        channel: PushChannel,
    ) -> None:
        """
        Handle a token refresh.
        
        Implements ITokenLifecycleHandler.on_token_refreshed
        
        Called when a device reports a new push token.
        
        Args:
            old_token: The previous token
            new_token: The new token
            device_id: Device identifier
            channel: Push channel
        """
        logger.info(f"Token refreshed for device {device_id}")
        
        # Get the existing registration
        registration = await self._registry.get_device_by_id(device_id)
        
        if registration:
            # Update the token via full registration flow
            device_info = DeviceInfo(
                device_id=device_id,
                platform=registration.platform,
                fcm_token=new_token,
                app_version=registration.app_version,
                os_version=registration.os_version,
                device_model=registration.device_model,
            )
            
            await self._registry.register_device(
                user_id=registration.user_id,
                device_info=device_info,
                organization_id=registration.organization_id,
            )
        else:
            logger.warning(
                f"Token refresh for unknown device {device_id}, "
                "cannot update without user context"
            )
        
        # Audit log
        if self._audit_logger:
            await self._audit_logger.log(
                event_type="push.token.refreshed",
                device_id=device_id,
                channel=channel.value,
            )


def create_push_infrastructure(
    registry: DeviceRegistry,
    fcm_config: dict[str, Any] | None = None,
    sse_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Factory function to create the complete push notification infrastructure.
    
    Creates and wires together:
    - Token store (from DeviceRegistry)
    - Lifecycle handler (from DeviceRegistry)
    - FCM adapter (if configured)
    - SSE adapter (if configured)
    - Push manager
    
    Args:
        registry: Marty DeviceRegistry
        fcm_config: Optional FCM configuration dict
        sse_config: Optional SSE configuration dict
        
    Returns:
        Dict with 'push_manager' and other components
    """
    try:
        from mmf.core.push import PushManager
        from mmf.framework.push.fcm import FCMAdapter, FCMConfig
        from mmf.framework.push.sse import SSEAdapter, SSEConfig
    except ImportError:
        from marty_microservices_framework.mmf.core.push import PushManager
        from marty_microservices_framework.mmf.framework.push.fcm import FCMAdapter, FCMConfig
        from marty_microservices_framework.mmf.framework.push.sse import SSEAdapter, SSEConfig
    
    # Create adapters
    token_store = DeviceRegistryTokenStore(registry)
    lifecycle_handler = DeviceRegistryLifecycleHandler(registry)
    
    # Create adapters
    adapters = {}
    
    if fcm_config:
        config = FCMConfig(**fcm_config)
        adapters["fcm"] = FCMAdapter(config, lifecycle_handler=lifecycle_handler)
    
    if sse_config:
        config = SSEConfig(**sse_config)
        adapters["sse"] = SSEAdapter(config)
    
    # Create push manager
    push_manager = PushManager(token_store=token_store)
    
    for adapter in adapters.values():
        push_manager.register_adapter(adapter)
    
    return {
        "push_manager": push_manager,
        "token_store": token_store,
        "lifecycle_handler": lifecycle_handler,
        "adapters": adapters,
    }
