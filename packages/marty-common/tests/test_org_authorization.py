from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from marty_common.org_authorization import (
    OrganizationMembership,
    require_org_membership,
)


def _request(org_client: object | None = None) -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "app": SimpleNamespace(state=SimpleNamespace()),
        }
    )
    if org_client is not None:
        request.app.state.org_client = org_client
    return request


@pytest.mark.asyncio
async def test_api_key_uses_gateway_bound_organization_and_permission() -> None:
    context = await require_org_membership(
        "org-b",
        _request(),
        x_user_id="api_key:key-b",
        x_organization_id="org-b",
        x_api_key_id="key-b",
        x_required_permission="credential-template:view",
    )

    assert context.source == "api_key"
    assert context.organization_id == "org-b"
    assert context.membership is None
    assert context.permissions == {"credential-template:view"}
    assert context.has_permission("credential-template", "view")


@pytest.mark.asyncio
async def test_api_key_cannot_select_another_organization() -> None:
    with pytest.raises(
        HTTPException,
        match="API key does not have access to this organization",
    ) as exc:
        await require_org_membership(
            "org-a",
            _request(),
            x_user_id="api_key:key-b",
            x_organization_id="org-b",
            x_api_key_id="key-b",
            x_required_permission="credential-template:view",
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_api_key_requires_complete_gateway_authorization_context() -> None:
    with pytest.raises(
        HTTPException,
        match="missing an authorized permission",
    ) as exc:
        await require_org_membership(
            "org-b",
            _request(),
            x_user_id="api_key:key-b",
            x_organization_id="org-b",
            x_api_key_id="key-b",
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_api_key_identity_must_match_gateway_principal() -> None:
    with pytest.raises(
        HTTPException,
        match="identity context is inconsistent",
    ) as exc:
        await require_org_membership(
            "org-b",
            _request(),
            x_user_id="api_key:different-key",
            x_organization_id="org-b",
            x_api_key_id="key-b",
            x_required_permission="credential-template:view",
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_session_principal_still_requires_active_membership() -> None:
    membership = OrganizationMembership(
        user_id="user-1",
        organization_id="org-a",
        status="active",
        permissions={"credential-template:view"},
    )
    get_membership = AsyncMock(return_value=membership)
    request = _request(SimpleNamespace(get_membership=get_membership))

    context = await require_org_membership(
        "org-a",
        request,
        x_user_id="user-1",
    )

    assert context.source == "session"
    assert context.membership == membership
    get_membership.assert_awaited_once_with("user-1", "org-a")
