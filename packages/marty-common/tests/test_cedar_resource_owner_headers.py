"""Authentication headers for internal resource-owner lookups."""

from types import SimpleNamespace

from marty_common.cedar_middleware import CedarAuthMiddleware


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
