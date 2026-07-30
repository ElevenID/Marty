from __future__ import annotations

import pytest

from marty_common.cedar_actions import (
    extract_org_id,
    resolve_action_and_resource,
)


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
