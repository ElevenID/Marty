"""
Device Ownership Verification Dependencies

Provides reusable FastAPI dependency for verifying device ownership
and organization context in multi-tenant scenarios.
"""
from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status

from .device_registry import DeviceInfo, DeviceRegistry

logger = logging.getLogger(__name__)


async def verify_device_ownership(
    device_id: str,
    registry: DeviceRegistry,
    x_user_id: Annotated[str | None, Header()] = None,
    x_organization_id: Annotated[str | None, Header()] = None,
) -> DeviceInfo:
    """
    Verify that the authenticated user owns the specified device.
    
    This dependency performs multi-tenant authorization checks:
      1. Verifies device exists in registry
      2. Checks user_id matches device owner (if x_user_id provided)
      3. Checks organization_id matches device org (if x_organization_id provided)
    
    Args:
        device_id: Device identifier to verify
        registry: Device registry dependency
        x_user_id: Optional authenticated user ID from header
        x_organization_id: Optional organization context from header
    
    Returns:
        DeviceInfo: The verified device information
    
    Raises:
        HTTPException: 404 if device not found, 403 if ownership check fails
    
    Usage:
        @router.post("/challenges/{challenge_id}/respond")
        async def respond_to_challenge(
            challenge_id: str,
            device: DeviceInfo = Depends(verify_device_ownership),
        ):
            # device is guaranteed to exist and belong to authenticated user
            ...
    """
    # Check if device exists
    device = await registry.get_device_by_id(device_id)
    
    if not device:
        logger.warning(f"Device not found: {device_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not registered"
        )
    
    # Verify user ownership (if user context provided)
    if x_user_id and device.user_id != x_user_id:
        logger.warning(
            f"User {x_user_id} attempted to access device {device_id} "
            f"owned by {device.user_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this device"
        )
    
    # Verify organization context (if org context provided)
    if x_organization_id and device.organization_id:
        device_org_str = str(device.organization_id)
        if device_org_str != x_organization_id:
            logger.warning(
                f"Organization {x_organization_id} attempted to access device {device_id} "
                f"belonging to organization {device_org_str}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access device in this organization"
            )
    
    logger.debug(f"Device ownership verified: {device_id} for user {device.user_id}")
    return device


# Factory for creating device ownership dependency with explicit device_id parameter
def verify_device_ownership_factory(device_id_param: str) -> DeviceInfo:
    """
    Create a device ownership verification dependency for a specific parameter name.
    
    Useful when device_id comes from path, query, or body instead of standard location.
    
    Args:
        device_id_param: Name of the parameter containing device_id
    
    Returns:
        Dependency function that can be used with Depends()
    
    Example:
        verify_device = verify_device_ownership_factory("target_device")
        
        @router.post("/devices/{target_device}/action")
        async def perform_action(
            device: DeviceInfo = Depends(verify_device)
        ):
            ...
    """
    async def _verify(
        device_id: str,
        registry: DeviceRegistry = Depends(),
        x_user_id: Annotated[str | None, Header()] = None,
        x_organization_id: Annotated[str | None, Header()] = None,
    ) -> DeviceInfo:
        return await verify_device_ownership(
            device_id=device_id,
            registry=registry,
            x_user_id=x_user_id,
            x_organization_id=x_organization_id,
        )
    
    return _verify
