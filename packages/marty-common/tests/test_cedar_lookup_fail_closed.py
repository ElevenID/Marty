"""Fail-closed resource-owner lookup contracts for Cedar authorization."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import JSONResponse
from starlette.requests import Request

from marty_common.cedar_middleware import CedarAuthMiddleware

ORG_A = "00000000-0000-0000-0000-000000000001"
ORG_B = "00000000-0000-0000-0000-000000000002"


def _api_key_request(
    app: SimpleNamespace,
    path: str = "/v1/presentation-policies/policy-b",
) -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": b"",
            "headers": [],
            "app": app,
        }
    )
    request.state.auth_source = "api_key"
    request.state.user_id = "api_key:key-a"
    request.state.api_key_id = "key-a"
    request.state.api_key_organization_id = ORG_A
    request.state.organization_id = ORG_A
    request.state.api_key_scopes = ["trust:read"]
    return request


def _app_with_lookup(response_or_error) -> SimpleNamespace:
    service_registry = MagicMock()
    service_registry.get_service_url.return_value = "http://presentation-policy:8009"
    http_client = MagicMock()
    if isinstance(response_or_error, Exception):
        http_client.get = AsyncMock(side_effect=response_or_error)
    else:
        http_client.get = AsyncMock(return_value=response_or_error)
    return SimpleNamespace(
        state=SimpleNamespace(
            service_registry=service_registry,
            http_client=http_client,
        )
    )


@pytest.mark.asyncio
async def test_lookup_timeout_cannot_fall_back_then_return_foreign_resource() -> None:
    app = _app_with_lookup(TimeoutError("owner lookup timed out"))
    request = _api_key_request(app)
    foreign_backend_read = AsyncMock(return_value=JSONResponse({"organization_id": ORG_B, "name": "foreign policy"}))

    response = await CedarAuthMiddleware(app=MagicMock()).dispatch(
        request,
        foreign_backend_read,
    )

    assert response.status_code == 503
    assert json.loads(response.body) == {"detail": "Resource owner lookup unavailable"}
    foreign_backend_read.assert_not_awaited()


@pytest.mark.asyncio
async def test_lookup_failure_does_not_log_resource_or_exception_secrets() -> None:
    secret = "super-secret-password"
    app = _app_with_lookup(TimeoutError(f"upstream URL contained {secret}"))
    request = _api_key_request(
        app,
        path=f"/v1/presentation-policies/{secret}",
    )
    call_next = AsyncMock(return_value=JSONResponse({"ok": True}))

    with patch("marty_common.cedar_middleware.logger.warning") as warning:
        response = await CedarAuthMiddleware(app=MagicMock()).dispatch(
            request,
            call_next,
        )

    assert response.status_code == 503
    assert secret not in repr(warning.call_args_list)
    warning.assert_called_once_with(
        "Resource-owner lookup failed for service=%s",
        "presentation-policies",
    )
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_membership_denial_does_not_log_principal_or_tenant_secrets() -> None:
    upstream = MagicMock(status_code=200)
    upstream.json.return_value = {"organization_id": ORG_A}
    app = _app_with_lookup(upstream)
    membership = MagicMock()
    membership.is_active.return_value = True
    membership.has_permission.return_value = False
    membership.role_names = {"super-secret-role"}
    app.state.org_client = MagicMock()
    app.state.org_client.get_membership = AsyncMock(return_value=membership)
    request = _api_key_request(app)
    request.state.auth_source = "session"
    request.state.user_id = "super-secret-user"
    call_next = AsyncMock(return_value=JSONResponse({"ok": True}))

    with patch("marty_common.cedar_middleware.logger.warning") as warning:
        response = await CedarAuthMiddleware(app=MagicMock()).dispatch(
            request,
            call_next,
        )

    assert response.status_code == 403
    warning.assert_called_once_with(
        "Gateway deny for permission=%s",
        "presentation-policy:view",
    )
    logged = repr(warning.call_args_list)
    assert "super-secret-user" not in logged
    assert "super-secret-role" not in logged
    assert ORG_A not in logged
    call_next.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_dependency", ["service_registry", "http_client"])
async def test_known_detail_lookup_requires_owner_lookup_dependencies(
    missing_dependency: str,
) -> None:
    upstream = MagicMock(status_code=200)
    upstream.json.return_value = {"organization_id": ORG_A}
    app = _app_with_lookup(upstream)
    delattr(app.state, missing_dependency)
    request = _api_key_request(app)
    call_next = AsyncMock(return_value=JSONResponse({"ok": True}))

    response = await CedarAuthMiddleware(app=MagicMock()).dispatch(request, call_next)

    assert response.status_code == 503
    assert json.loads(response.body) == {"detail": "Resource owner lookup unavailable"}
    call_next.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service_url", "resolver_error"),
    [
        (None, None),
        (None, RuntimeError("registry unavailable")),
    ],
)
async def test_known_detail_lookup_requires_resolvable_owner_service(
    service_url: str | None,
    resolver_error: Exception | None,
) -> None:
    upstream = MagicMock(status_code=200)
    upstream.json.return_value = {"organization_id": ORG_A}
    app = _app_with_lookup(upstream)
    if resolver_error is not None:
        app.state.service_registry.get_service_url.side_effect = resolver_error
    else:
        app.state.service_registry.get_service_url.return_value = service_url
    request = _api_key_request(app)
    call_next = AsyncMock(return_value=JSONResponse({"ok": True}))

    response = await CedarAuthMiddleware(app=MagicMock()).dispatch(request, call_next)

    assert response.status_code == 503
    assert json.loads(response.body) == {"detail": "Resource owner lookup unavailable"}
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_foreign_owner_lookup_denies_api_key() -> None:
    upstream = MagicMock(status_code=200)
    upstream.json.return_value = {"organization_id": ORG_B}
    app = _app_with_lookup(upstream)
    request = _api_key_request(app)
    call_next = AsyncMock(return_value=JSONResponse({"ok": True}))

    response = await CedarAuthMiddleware(app=MagicMock()).dispatch(
        request,
        call_next,
    )

    assert response.status_code == 403
    assert json.loads(response.body) == {"detail": "API key does not have access to this organization"}
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_tenant_lookup_forwards_exact_permission_and_continues() -> None:
    upstream = MagicMock(status_code=200)
    upstream.json.return_value = {"organization_id": ORG_A}
    app = _app_with_lookup(upstream)
    request = _api_key_request(app)
    call_next = AsyncMock(return_value=JSONResponse({"ok": True}))

    response = await CedarAuthMiddleware(app=MagicMock()).dispatch(
        request,
        call_next,
    )

    assert response.status_code == 200
    assert request.state.organization_id == ORG_A
    assert request.state.required_permission == "presentation-policy:view"
    lookup = app.state.http_client.get.await_args
    assert lookup.args == ("http://presentation-policy:8009/v1/presentation-policies/policy-b",)
    assert lookup.kwargs["timeout"] == 10.0
    assert lookup.kwargs["headers"] == {
        "X-User-Id": "api_key:key-a",
        "X-Organization-ID": ORG_A,
        "X-Api-Key-Id": "key-a",
        "X-Api-Key-Scopes": "trust:read",
        "X-Required-Permission": "presentation-policy:view",
    }
    call_next.assert_awaited_once_with(request)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("upstream", "expected_status", "expected_detail"),
    [
        (
            SimpleNamespace(status_code=404, json=MagicMock()),
            404,
            "Resource not found",
        ),
        (
            SimpleNamespace(status_code=403, json=MagicMock()),
            403,
            "Resource access denied",
        ),
        (
            SimpleNamespace(status_code=500, json=MagicMock()),
            502,
            "Resource owner lookup failed",
        ),
        (
            SimpleNamespace(
                status_code=200,
                json=MagicMock(side_effect=ValueError("invalid JSON")),
            ),
            502,
            "Resource owner lookup failed",
        ),
        (
            SimpleNamespace(
                status_code=200,
                json=MagicMock(return_value={"organization_id": "   "}),
            ),
            502,
            "Resource owner lookup failed",
        ),
    ],
)
async def test_known_detail_lookup_never_falls_back_on_missing_owner(
    upstream,
    expected_status: int,
    expected_detail: str,
) -> None:
    app = _app_with_lookup(upstream)
    request = _api_key_request(app)
    call_next = AsyncMock(return_value=JSONResponse({"ok": True}))

    response = await CedarAuthMiddleware(app=MagicMock()).dispatch(
        request,
        call_next,
    )

    assert response.status_code == expected_status
    assert json.loads(response.body) == {"detail": expected_detail}
    call_next.assert_not_awaited()
