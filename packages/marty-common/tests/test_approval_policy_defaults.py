"""Automatic approval requires explicit platform-owned policy configuration."""

import pytest

from marty_common.cedar_engine import CedarEngine


def _decision(engine: CedarEngine, service_name: str):
    organization = {"type": "MIP::Organization", "id": "org-a"}
    return engine.is_authorized(
        principal='MIP::ServiceAccount::"worker"',
        action='MIP::Action::"applications:approve"',
        resource='MIP::Application::"application-a"',
        context={
            "risk_score": 0,
            "document_verification_passed": True,
            "biometric_match_score": 100,
            "evidence_count": 1,
            "applicant_country": "US",
            "evidence_provider": "external",
            "evidence_verification_status": "VERIFIED",
            "evidence_scope_matched": True,
            "required_evidence_count": 1,
            "satisfied_requirement_count": 1,
            "all_required_evidence_satisfied": True,
        },
        entities=[
            {"uid": organization, "attrs": {}, "parents": []},
            {
                "uid": {"type": "MIP::ServiceAccount", "id": "worker"},
                "attrs": {"service_name": service_name},
                "parents": [organization],
            },
            {
                "uid": {"type": "MIP::Application", "id": "application-a"},
                "attrs": {"risk_score": 0, "status": "PENDING"},
                "parents": [organization],
            },
        ],
    )


@pytest.mark.parametrize("service_name", [
    "external-evidence-worker", "unregistered-connector", "platform-approval",
])
def test_verified_evidence_does_not_grant_implicit_approval(service_name) -> None:
    decision = _decision(CedarEngine.with_approval_rules(), service_name)
    assert not decision.allowed
    assert not decision.errors


def test_explicit_approval_policy_still_controls_the_decision() -> None:
    engine = CedarEngine.with_approval_policy_text('''
        permit (
            principal is MIP::ServiceAccount,
            action == MIP::Action::"applications:approve",
            resource is MIP::Application
        ) when { principal.service_name == "reviewed-platform-policy" };
    ''')
    accepted = _decision(engine, "reviewed-platform-policy")
    assert accepted.allowed
    assert not accepted.errors
    rejected = _decision(engine, "unregistered-connector")
    assert not rejected.allowed
    assert not rejected.errors
