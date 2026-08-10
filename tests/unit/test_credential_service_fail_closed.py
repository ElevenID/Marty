"""Fail-closed contracts for legacy credential service orchestration."""

from types import SimpleNamespace

import pytest

from digital_identity.application.services.credential_issuance_service import (
    CredentialIssuanceService,
)


@pytest.mark.asyncio
async def test_credential_verification_never_trusts_unverified_jwt_claims() -> None:
    service = CredentialIssuanceService(credential_repository=SimpleNamespace())

    result = await service.verify_credential(
        organization_id="org-1",
        credential="header.payload.signature",
        presentation_policy_id=None,
        trust_profile_id=None,
    )

    assert result["valid"] is False
    assert result["checks"]["signature"] is False
    assert result["checks"]["trust_profile"] is False
    assert "issuer key resolution" in result["error"]


@pytest.mark.asyncio
async def test_production_issuance_rejects_ephemeral_issuer_keys(monkeypatch) -> None:
    from marty_plugin import native_backends

    monkeypatch.setattr(native_backends, "require_backend", lambda _name: SimpleNamespace())
    monkeypatch.setenv("ENVIRONMENT", "production")
    service = CredentialIssuanceService(credential_repository=SimpleNamespace())

    with pytest.raises(RuntimeError, match="organization-scoped issuer profile"):
        await service.issue_credential_from_request(
            organization_id="org-1",
            credential_template_id="template-1",
            flow_execution_id=None,
            subject_claims={"employee_id": "E-123"},
            holder_identifier="did:example:holder",
            application_data=None,
        )
