"""
Device Configuration API

Provides device-specific configuration including deployment profile,
lane assignment, and policies.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from digital_identity.infrastructure.adapters.rest.dependencies import (
    get_deployment_profile_service,
    get_presentation_policy_service,
)
from digital_identity.infrastructure.adapters.rest.schemas import ErrorResponse

logger = logging.getLogger(__name__)

# Router for device-specific endpoints
device_router = APIRouter(
    prefix="/v1/devices",
    tags=["Devices"],
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


class DeviceConfigResponse(BaseModel):
    """Device configuration response."""

    device_id: str
    deployment_profile: dict[str, Any] | None = None
    lane: dict[str, Any] | None = None
    policies: list[dict[str, Any]] = []


@device_router.get(
    "/{device_id}/config",
    response_model=DeviceConfigResponse,
    summary="Get Device Configuration",
    description="Fetch deployment profile, lane assignment, and policies for a device",
)
async def get_device_config(
    device_id: str,
    profile_service=Depends(get_deployment_profile_service),
    policy_service=Depends(get_presentation_policy_service),
) -> DeviceConfigResponse:
    """
    Get device configuration including deployment profile, lane, and policies.
    
    The device_id is used to look up:
    1. Which lane the device is assigned to (if any)
    2. The deployment profile for that lane
    3. Relevant presentation policies
    
    Returns profile-level defaults if device is not assigned to a lane.
    """
    try:
        # Find deployment profile and lane for this device
        deployment_profile = None
        lane = None
        
        # Search through all profiles and lanes to find device assignment
        profiles = await profile_service.list(skip=0, limit=1000)
        
        for profile in profiles:
            for l in profile.lanes:
                if device_id in l.device_ids:
                    deployment_profile = profile
                    lane = l
                    break
            if lane:
                break
        
        if not deployment_profile:
            # Device not assigned - return empty config
            return DeviceConfigResponse(
                device_id=device_id,
                deployment_profile=None,
                lane=None,
                policies=[],
            )
        
        # Get policies for this deployment profile
        policies = await policy_service.list(
            skip=0,
            limit=1000,
            deployment_profile_id=deployment_profile.id if deployment_profile else None,
        )
        
        # Serialize deployment profile
        profile_data = {
            "id": deployment_profile.id,
            "name": deployment_profile.name,
            "site_id": deployment_profile.site_id,
            "network_mode": deployment_profile.network_mode.value,
            "key_access_mode": deployment_profile.key_access_mode.value,
            "ux_config": {
                "language": deployment_profile.ux_config.language,
                "theme": deployment_profile.ux_config.theme,
                "show_operator_mode": deployment_profile.ux_config.show_operator_mode,
                "accessibility_enabled": deployment_profile.ux_config.accessibility_enabled,
                "custom_branding": deployment_profile.ux_config.custom_branding,
                "signage_text": deployment_profile.ux_config.signage_text,
            },
            "update_policy": {
                "auto_update": deployment_profile.update_policy.auto_update,
                "update_channel": deployment_profile.update_policy.update_channel,
                "rollout_percentage": deployment_profile.update_policy.rollout_percentage,
                "version_pinned": deployment_profile.update_policy.version_pinned,
                "rollout_ring": deployment_profile.update_policy.rollout_ring,
            },
            "offline_cache_ttl_hours": deployment_profile.offline_cache_ttl_hours,
            "biometric_required": deployment_profile.biometric_required,
            "audit_all_events": deployment_profile.audit_all_events,
        }
        
        # Serialize lane
        lane_data = None
        if lane:
            lane_data = {
                "id": lane.id,
                "name": lane.name,
                "deployment_profile_id": lane.deployment_profile_id,
                "default_policy_id": lane.default_policy_id,
                "device_ids": lane.device_ids,
                "metadata": lane.metadata,
            }
        
        # Serialize policies (minimal info for sync)
        policy_data = [
            {
                "id": p.id,
                "name": p.name,
                "credential_types": p.accepted_credential_types,
                "version": p.version,
            }
            for p in policies
        ]
        
        return DeviceConfigResponse(
            device_id=device_id,
            deployment_profile=profile_data,
            lane=lane_data,
            policies=policy_data,
        )
        
    except Exception as e:
        logger.exception(f"Failed to fetch device config for {device_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch device configuration: {str(e)}",
        )
