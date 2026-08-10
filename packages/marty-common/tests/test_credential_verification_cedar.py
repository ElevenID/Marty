"""Credential-verification Cedar decisions preserve unknown revocation state."""

from __future__ import annotations

import pytest

from marty_common.cedar_engine import CedarEngine


def _context(
    *,
    revocation_checked: bool,
    revocation_required: bool,
    is_revoked: bool,
) -> dict[str, object]:
    return {
        "credential_format": "SD_JWT_VC",
        "compliance_code": "UNSPECIFIED",
        "issuer_id": "https://issuer.example",
        "issuer_trust_level": 100,
        "credential_age_seconds": 30,
        "revocation_checked": revocation_checked,
        "revocation_required": revocation_required,
        "is_revoked": is_revoked,
        "is_expired": False,
        "holder_binding_present": True,
        "algorithm": "ES256",
    }


def _entities() -> list[dict[str, object]]:
    organization = {"type": "MIP::Organization", "id": "org-1"}
    return [
        {
            "uid": {"type": "MIP::User", "id": "verifier"},
            "attrs": {"email": "", "status": "ACTIVE"},
            "parents": [organization],
        },
        {
            "uid": organization,
            "attrs": {},
            "parents": [],
        },
        {
            "uid": {"type": "MIP::Credential", "id": "presented-credential"},
            "attrs": {
                "format": "SD_JWT_VC",
                "status": "ACTIVE",
                "compliance_code": "UNSPECIFIED",
                "issuer_id": "https://issuer.example",
                "trust_level": 100,
            },
            "parents": [organization],
        },
    ]


def _authorize(context: dict[str, object]) -> bool:
    return CedarEngine.with_credential_verification().is_authorized(
        principal='MIP::User::"verifier"',
        action='MIP::Action::"credentials:verify"',
        resource='MIP::Credential::"presented-credential"',
        context=context,
        entities=_entities(),
    ).allowed


def test_unchecked_revocation_can_only_pass_when_policy_does_not_require_it() -> None:
    assert _authorize(
        _context(
            revocation_checked=False,
            revocation_required=False,
            is_revoked=False,
        )
    )
    assert not _authorize(
        _context(
            revocation_checked=False,
            revocation_required=True,
            is_revoked=False,
        )
    )


def test_checked_non_revoked_credential_satisfies_required_revocation_policy() -> None:
    assert _authorize(
        _context(
            revocation_checked=True,
            revocation_required=True,
            is_revoked=False,
        )
    )


@pytest.mark.parametrize("revocation_required", [False, True])
def test_known_revocation_always_denies(revocation_required: bool) -> None:
    assert not _authorize(
        _context(
            revocation_checked=True,
            revocation_required=revocation_required,
            is_revoked=True,
        )
    )


def test_unchecked_input_cannot_claim_a_known_revocation_result() -> None:
    assert not _authorize(
        _context(
            revocation_checked=False,
            revocation_required=False,
            is_revoked=True,
        )
    )


@pytest.mark.parametrize("missing_field", ["revocation_checked", "revocation_required"])
def test_legacy_context_without_explicit_revocation_policy_fails_closed(
    missing_field: str,
) -> None:
    context = _context(
        revocation_checked=False,
        revocation_required=False,
        is_revoked=False,
    )
    del context[missing_field]

    assert not _authorize(context)
