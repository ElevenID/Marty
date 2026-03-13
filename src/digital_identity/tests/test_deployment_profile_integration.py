"""Integration Tests for Deployment Profile Abstraction"""

from __future__ import annotations

import pytest

from digital_identity.domain.value_objects import (
    TrustProfileType,
    RequiredClaim,
    NetworkMode,
)
from digital_identity.application.services.trust_profile_service import TrustProfileService
from digital_identity.application.services.presentation_policy_service import PresentationPolicyService
from digital_identity.application.services.deployment_profile_service import DeploymentProfileService


class TestDeploymentProfileIntegration:
    """Integration tests for Deployment Profile abstraction."""

    @pytest.mark.asyncio
    async def test_deployment_profile_lifecycle(
        self,
        deployment_profile_service: DeploymentProfileService,
        presentation_policy_service: PresentationPolicyService,
        trust_profile_service: TrustProfileService,
    ):
        """Test complete Deployment Profile lifecycle."""
        # Create dependencies
        tp = await trust_profile_service.create(
            name="Gate Trust",
            profile_type=TrustProfileType.ICAO,
        )
        
        pp = await presentation_policy_service.create(
            name="Gate Policy",
            description="Gate verification policy",
            purpose="Boarding verification",
            accepted_credential_types=["boarding.pass"],
            required_claims=[
                {"claim_name": "flight_number", "credential_type": "boarding.pass"},
                {"claim_name": "gate", "credential_type": "boarding.pass"},
            ],
            trust_profile_id=tp.id,
        )
        
        # Create Deployment Profile
        dp = await deployment_profile_service.create(
            name="Airport Gate 12",
            description="Deployment profile for Gate 12",
            enabled_flow_ids=[pp.id],
            network_mode=NetworkMode.ONLINE,
            ux_config={
                "language": "en",
                "operator_mode": True,
                "accessibility_mode": True,
            },
        )
        
        assert dp.id is not None
        assert dp.name == "Airport Gate 12"
        assert pp.id in dp.enabled_flow_ids
        
        # Read
        retrieved = await deployment_profile_service.get(dp.id)
        assert retrieved is not None
        
        # Update
        updated = await deployment_profile_service.update(
            profile_id=dp.id,
            network_mode=NetworkMode.OFFLINE,
        )
        assert updated.network_mode == NetworkMode.OFFLINE
        
        # Delete
        await deployment_profile_service.delete(dp.id)
        deleted = await deployment_profile_service.get(dp.id)
        assert deleted is None

    @pytest.mark.asyncio
    async def test_deployment_profile_offline_mode(
        self,
        deployment_profile_service: DeploymentProfileService,
        presentation_policy_service: PresentationPolicyService,
        trust_profile_service: TrustProfileService,
    ):
        """Test Deployment Profile with offline mode configuration."""
        tp = await trust_profile_service.create(
            name="Offline Trust",
            profile_type=TrustProfileType.ICAO,
        )
        
        pp = await presentation_policy_service.create(
            name="Offline Policy",
            description="Policy for offline verification",
            purpose="Offline boarding verification",
            accepted_credential_types=["boarding.pass"],
            required_claims=[
                {"claim_name": "flight_number", "credential_type": "boarding.pass"},
            ],
            trust_profile_id=tp.id,
        )
        
        # Create offline deployment profile
        dp = await deployment_profile_service.create(
            name="Offline Kiosk",
            enabled_flow_ids=[pp.id],
            network_mode=NetworkMode.OFFLINE,
            ux_config={
                "language": "en",
                "accessibility_mode": True,
            },
        )
        
        assert dp.network_mode == NetworkMode.OFFLINE
        assert dp.ux_config.language == "en"
