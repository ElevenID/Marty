"""Integration Tests for Presentation Policy Abstraction"""

from __future__ import annotations

import pytest

from digital_identity.domain.value_objects import (
    TrustProfileType,
    RequiredClaim,
    HolderBindingMethod,
    HolderBindingConfig,
    FreshnessRequirements,
)
from digital_identity.application.services.trust_profile_service import TrustProfileService
from digital_identity.application.services.credential_template_service import CredentialTemplateService
from digital_identity.application.services.presentation_policy_service import PresentationPolicyService


class TestPresentationPolicyIntegration:
    """Integration tests for Presentation Policy abstraction."""

    @pytest.mark.asyncio
    async def test_presentation_policy_lifecycle(
        self,
        presentation_policy_service: PresentationPolicyService,
        trust_profile_service: TrustProfileService,
        credential_template_service: CredentialTemplateService,
    ):
        """Test complete Presentation Policy lifecycle."""
        # Create dependencies
        tp = await trust_profile_service.create(
            name="Test Trust",
            profile_type=TrustProfileType.ICAO,
        )
        
        ct = await credential_template_service.create(
            name="Test Credential",
            credential_type="test.credential",
            claims=[
                {"name": "age_over_21", "display_name": "Age Over 21", "data_type": "boolean", "required": True},
            ],
        )
        
        # Create Presentation Policy
        pp = await presentation_policy_service.create(
            name="Age 21+ Verification",
            description="Verify age over 21",
            purpose="Age verification for access control",
            accepted_credential_types=["test.credential"],
            required_claims=[
                {
                    "claim_name": "age_over_21",
                    "credential_type": "test.credential",
                    "accept_predicate": True,
                },
            ],
            trust_profile_id=tp.id,
            holder_binding=HolderBindingConfig(
                required=True,
                binding_methods=[HolderBindingMethod.BIOMETRIC],
                nonce_required=False,
            ),
            freshness_requirements={
                "max_age_seconds": 86400,
                "require_not_revoked": True,
            },
        )
        
        assert pp.id is not None
        assert pp.name == "Age 21+ Verification"
        assert len(pp.required_claims) == 1
        
        # Read
        retrieved = await presentation_policy_service.get(pp.id)
        assert retrieved is not None
        assert retrieved.trust_profile_id == tp.id
        
        # Update
        updated = await presentation_policy_service.update(
            policy_id=pp.id,
            description="Updated age verification policy",
        )
        assert updated.description == "Updated age verification policy"
        
        # Delete
        await presentation_policy_service.delete(pp.id)
        deleted = await presentation_policy_service.get(pp.id)
        assert deleted is None

    @pytest.mark.asyncio
    async def test_presentation_policy_data_minimization(
        self,
        presentation_policy_service: PresentationPolicyService,
        trust_profile_service: TrustProfileService,
    ):
        """Test Presentation Policy with data minimization rules."""
        tp = await trust_profile_service.create(
            name="Minimal Trust",
            profile_type=TrustProfileType.AAMVA,
        )
        
        # Policy that prefers boolean over full DOB
        pp = await presentation_policy_service.create(
            name="Minimal Age Check",
            description="Request only age_over_21, not full DOB",
            purpose="Minimal age verification",
            accepted_credential_types=["mdl"],
            required_claims=[
                {
                    "claim_name": "age_over_21",
                    "credential_type": "mdl",
                    "accept_predicate": True,
                },
            ],
            trust_profile_id=tp.id,
        )
        
        # Verify only minimal claim is requested
        req = pp.required_claims[0]
        assert req.claim_name == "age_over_21"
        # Verify date_of_birth is NOT requested
        dob_claims = [c for c in pp.required_claims if c.claim_name == "date_of_birth"]
        assert len(dob_claims) == 0
