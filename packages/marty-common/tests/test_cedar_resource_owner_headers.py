"""Authentication headers for internal resource-owner lookups."""

from types import SimpleNamespace

import pytest

from marty_common.cedar_middleware import CedarAuthMiddleware


class _JsonRequest(SimpleNamespace):
    async def json(self):
        return self.payload


def test_resource_owner_lookup_uses_service_specific_credentials(monkeypatch) -> None:
    monkeypatch.setenv("ISSUANCE_API_KEY", "issuance-service-key")
    monkeypatch.setenv("SIGNING_KEYS_INTERNAL_API_KEY", "trust-service-key")
    request = SimpleNamespace(state=SimpleNamespace(), headers={})

    assert CedarAuthMiddleware._forward_headers(request, "issuance") == {
        "X-API-Key": "issuance-service-key"
    }
    assert CedarAuthMiddleware._forward_headers(request, "trust-profiles") == {
        "X-API-Key": "trust-service-key"
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
async def test_mutation_body_selects_organization_for_authorization(method: str) -> None:
    request = _JsonRequest(
        method=method,
        headers={"content-type": "application/json"},
        payload={"organization_id": "org-from-public-request"},
    )

    assert (
        await CedarAuthMiddleware._extract_body_org_id(SimpleNamespace(), request)
        == "org-from-public-request"
    )


@pytest.mark.asyncio
async def test_read_body_does_not_override_selected_organization() -> None:
    request = _JsonRequest(
        method="GET",
        headers={"content-type": "application/json"},
        payload={"organization_id": "untrusted-read-body"},
    )

    assert (
        await CedarAuthMiddleware._extract_body_org_id(SimpleNamespace(), request) is None
    )
