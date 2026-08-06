from __future__ import annotations

import pytest

from marty_common.cedar_actions import (
    extract_org_id,
    resolve_action_and_resource,
)
from marty_common.cedar_middleware import CedarAuthMiddleware

ORG_ID = "11111111-1111-1111-1111-111111111111"
ORG_PREFIX = f"/v1/organizations/{ORG_ID}/"


@pytest.mark.parametrize(
    ("path", "expected_permission"),
    [
        (ORG_PREFIX + "audit-events", "audit:view"),
        (ORG_PREFIX + "audit-events/event-123", "audit:view"),
        (ORG_PREFIX + "audit-events/export", "audit:export"),
    ],
)
def test_audit_routes_require_tenant_scoped_permissions(
    path: str,
    expected_permission: str,
) -> None:
    assert extract_org_id(path) == ORG_ID
    assert resolve_action_and_resource("GET", path) == (
        expected_permission,
        "audit",
    )


@pytest.mark.parametrize(
    "method",
    ["POST", "PUT", "PATCH", "DELETE"],
)
def test_audit_routes_do_not_infer_unsupported_mutations(method: str) -> None:
    assert resolve_action_and_resource(method, ORG_PREFIX + "audit-events") is None


@pytest.mark.parametrize(
    ("method", "expected_permission"),
    [
        ("GET", "trusted-issuer:view"),
        ("HEAD", "trusted-issuer:view"),
        ("OPTIONS", "trusted-issuer:view"),
        ("POST", "trusted-issuer:create"),
        ("PUT", "trusted-issuer:edit"),
        ("PATCH", "trusted-issuer:edit"),
        ("DELETE", "trusted-issuer:delete"),
    ],
)
def test_issuer_entity_routes_require_trust_permissions(
    method: str,
    expected_permission: str,
) -> None:
    assert resolve_action_and_resource(method, "/v1/issuer-entities/entity-123") == (
        expected_permission,
        "issuer-entity",
    )


def test_issuer_entity_permissions_map_to_public_api_key_trust_scopes() -> None:
    assert CedarAuthMiddleware._api_key_allowed("trusted-issuer:view", ["trust:read"])
    assert CedarAuthMiddleware._api_key_allowed("trusted-issuer:create", ["trust:write"])
    assert not CedarAuthMiddleware._api_key_allowed(
        "trusted-issuer:create", ["trust:read"]
    )


def test_didcomm_delivery_requires_issuance_permission() -> None:
    assert resolve_action_and_resource("POST", "/v1/issuance/didcomm/deliver") == (
        "issuance:initiate",
        "issuance",
    )


def test_didcomm_delivery_maps_to_public_api_key_issuance_scope() -> None:
    assert CedarAuthMiddleware._api_key_allowed(
        "issuance:initiate", ["credentials:issue"]
    )
    assert not CedarAuthMiddleware._api_key_allowed(
        "issuance:initiate", ["credentials:read"]
    )
