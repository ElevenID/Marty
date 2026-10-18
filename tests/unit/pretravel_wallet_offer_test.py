"""Pretravel hands verified facts to Rust; offers are never issued credentials."""

import asyncio
import importlib
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def modules(monkeypatch):
    saved = {
        name: value
        for name, value in sys.modules.items()
        if name == "app" or name.startswith("app.")
    }
    for name in saved:
        del sys.modules[name]
    monkeypatch.syspath_prepend(str(ROOT / "packages/marty-common"))
    monkeypatch.syspath_prepend(str(ROOT / "src"))
    monkeypatch.syspath_prepend(str(ROOT / "src/marty_plugin/document_processing"))
    monkeypatch.setenv("DEBUG", "false")
    try:
        yield SimpleNamespace(
            client=importlib.import_module("app.services.pretravel_issuance"),
            models=importlib.import_module("app.models.doc_models_clean"),
        )
    finally:
        for name in list(sys.modules):
            if name == "app" or name.startswith("app."):
                del sys.modules[name]
        sys.modules.update(saved)


@pytest.fixture
def binding(modules, tmp_path):
    key_file = tmp_path / "issuance-api-key"
    key_file.write_text("server-management-key", encoding="utf-8")
    return modules.client.PreTravelIssuanceConfig(
        base_url="https://issuance.example",
        organization_id="org-a",
        issuer_did="did:web:issuer.example",
        template_id="pretravel-template",
        api_key_file=str(key_file),
    )


def offer_payload():
    return {
        "id": "transaction-a",
        "organization_id": "org-a",
        "credential_template_id": "pretravel-template",
        "status": "pending",
        "credential_offer_uri": "openid-credential-offer://?credential_offer="
        + quote(
            json.dumps(
                {
                    "credential_issuer": "https://issuance.example/org/org-a",
                    "credential_configuration_ids": ["PreTravelCredential#sd-jwt"],
                    "grants": {
                        "urn:ietf:params:oauth:grant-type:pre-authorized_code": {
                            "pre-authorized_code": "wallet-bearer-secret"
                        }
                    },
                }
            )
        ),
        "credential_offer_uris": {},
        "credential_offer_labels": {},
        "pre_auth_code": "wallet-bearer-secret",
        "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
    }


def test_transport_sends_only_configured_offer_request_and_rotates_api_key(
    modules, binding
):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=offer_payload())

    client = modules.client.RustPreTravelIssuance(
        binding, transport=httpx.MockTransport(handler)
    )
    claims = {
        "documentNumber": "document-a",
        "barcodeDataPresent": False,
        "nfcPayloadPresent": True,
    }
    result = asyncio.run(client.offer(claims))
    assert result.status == "pending"
    assert "wallet-bearer-secret" not in repr(result)
    assert str(requests[0].url) == "https://issuance.example/v1/issuance/initiate"
    assert requests[0].headers["x-api-key"] == "server-management-key"
    assert json.loads(requests[0].content) == {
        "organization_id": "org-a",
        "issuer_did": "did:web:issuer.example",
        "credential_template_id": "pretravel-template",
        "delivery_mode": "wallet_only",
        "claims": claims,
    }
    Path(binding.api_key_file).write_text("rotated-management-key", encoding="utf-8")
    asyncio.run(client.offer(claims))
    assert requests[-1].headers["x-api-key"] == "rotated-management-key"


@pytest.mark.parametrize("status", [302, 401, 403, 500])
def test_transport_never_follows_redirects_or_echoes_upstream_errors(
    modules, binding, status
):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            json={"detail": "wallet-bearer-secret"},
            headers={"Location": "https://foreign.example"},
        )

    client = modules.client.RustPreTravelIssuance(
        binding, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(modules.client.PreTravelIssuanceError) as error:
        asyncio.run(client.offer({}))
    assert len(calls) == 1
    assert "wallet-bearer-secret" not in str(error.value)


@pytest.mark.parametrize(
    "change",
    [
        {"organization_id": "foreign"},
        {"credential_template_id": "foreign"},
        {"status": "issued"},
        {"pre_auth_code": ""},
        {"pre_auth_code": "different-code"},
        {"credential_offer_uri": "javascript:foreign"},
        {
            "credential_offer_uri": "openid-credential-offer://?credential_offer=malformed"
        },
        {"expires_at": "2000-01-01T00:00:00Z"},
        {"token": "must-not-be-a-credential"},
    ],
)
def test_transport_rejects_mismatched_expired_or_credential_responses(
    modules, binding, change
):
    payload = {**offer_payload(), **change}
    client = modules.client.RustPreTravelIssuance(
        binding,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    )
    with pytest.raises(modules.client.PreTravelIssuanceError):
        asyncio.run(client.offer({}))


@pytest.mark.parametrize(
    "content", [b"not json", b"x" * 65537], ids=["invalid-json", "oversized"]
)
def test_transport_rejects_invalid_or_oversized_bodies(modules, binding, content):
    client = modules.client.RustPreTravelIssuance(
        binding,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=content)),
    )
    with pytest.raises(modules.client.PreTravelIssuanceError):
        asyncio.run(client.offer({}))


@pytest.mark.parametrize(
    "url",
    [
        "http://issuance.example",
        "https://user:password@issuance.example",
        "https://issuance.example/path",
        "https://issuance.example?key=secret",
    ],
)
def test_transport_rejects_unsafe_configuration_before_network(modules, binding, url):
    def unexpected(_):
        pytest.fail("unsafe configuration reached transport")

    client = modules.client.RustPreTravelIssuance(
        replace(binding, base_url=url), transport=httpx.MockTransport(unexpected)
    )
    with pytest.raises(modules.client.PreTravelIssuanceError):
        asyncio.run(client.offer({}))


def test_service_rejects_failed_native_mrz_without_creating_offer(
    modules, binding, monkeypatch
):
    service_module = importlib.import_module("app.services.pretravel_service")
    calls = []
    issuance = modules.client.RustPreTravelIssuance(
        binding, transport=httpx.MockTransport(lambda request: calls.append(request))
    )
    service = service_module.PreTravelVerificationService(issuance=issuance)
    monkeypatch.setattr(
        service.mrz_service,
        "_process_mrz_lines",
        lambda _: modules.models.MRZResult(overallValid=False),
    )
    result = asyncio.run(
        service.verify_and_issue(
            modules.models.PreTravelVerificationRequest(mrz_lines=["invalid"])
        )
    )
    assert (
        result.is_valid is False
        and result.wallet_offer is None
        and result.credential is None
    )
    assert not calls


def test_real_native_mrz_creates_only_allowlisted_offer_claims(modules, binding):
    service_module = importlib.import_module("app.services.pretravel_service")
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=offer_payload())

    issuance = modules.client.RustPreTravelIssuance(
        binding, transport=httpx.MockTransport(handler)
    )
    service = service_module.PreTravelVerificationService(issuance=issuance)
    lines = [
        "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
        "L898902C36UTO7408122F1204159ZE184226B<<<<<10",
    ]
    result = asyncio.run(
        service.verify_and_issue(
            modules.models.PreTravelVerificationRequest(mrz_lines=lines)
        )
    )
    assert (
        result.is_valid
        and result.wallet_offer.status == "pending"
        and result.credential is None
    )
    assert calls[0]["claims"]["documentNumber"] == "L898902C3"
    assert calls[0]["claims"]["dateOfBirth"] == "740812"
    assert set(calls[0]["claims"]) == {
        "documentNumber",
        "surname",
        "givenNames",
        "issuingState",
        "nationality",
        "dateOfBirth",
        "dateOfExpiry",
        "barcodeDataPresent",
        "nfcPayloadPresent",
    }
    assert "wallet-bearer-secret" not in repr(result)


@pytest.mark.parametrize(
    "changes",
    [
        {"issuance_type": "mdoc"},
        {"audience": "client"},
        {"nonce": "client"},
        {"credential_type": "OtherCredential"},
    ],
)
def test_unsupported_contracts_cannot_create_offers(modules, changes):
    service_module = importlib.import_module("app.services.pretravel_service")

    class NoIssuance:
        async def offer(self, claims):
            pytest.fail("unsupported contract created an offer")

    service = service_module.PreTravelVerificationService(issuance=NoIssuance())
    with pytest.raises(ValueError):
        asyncio.run(
            service.verify_and_issue(
                modules.models.PreTravelVerificationRequest(**changes)
            )
        )


def test_absent_tampered_and_untrusted_evidence_cannot_create_offers(modules):
    service_module = importlib.import_module("app.services.pretravel_service")

    class NoIssuance:
        async def offer(self, claims):
            pytest.fail("invalid evidence created an offer")

    service = service_module.PreTravelVerificationService(issuance=NoIssuance())
    for evidence in (
        {},
        {
            "mrz_lines": [
                "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
                "L898902C36UTO7408123F1204159ZE184226B<<<<<10",
            ]
        },
        {"barcode_data": "untrusted-barcode"},
        {"nfc_payload": "invalid-sod"},
    ):
        result = asyncio.run(
            service.verify_and_issue(
                modules.models.PreTravelVerificationRequest(**evidence)
            )
        )
        assert (
            not result.is_valid
            and result.wallet_offer is None
            and result.credential is None
        )


def test_timeout_and_missing_key_never_expose_secrets_or_retry(modules, binding):
    calls = []

    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("wallet-bearer-secret", request=request)

    client = modules.client.RustPreTravelIssuance(
        binding, transport=httpx.MockTransport(timeout)
    )
    with pytest.raises(modules.client.PreTravelIssuanceError) as error:
        asyncio.run(client.offer({}))
    assert len(calls) == 1 and "wallet-bearer-secret" not in str(error.value)
    Path(binding.api_key_file).unlink()
    with pytest.raises(modules.client.PreTravelIssuanceError):
        asyncio.run(client.offer({}))
    assert len(calls) == 1


def test_http_route_authentication_bearer_headers_and_request_overrides(
    modules, monkeypatch
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    endpoints = importlib.import_module("app.api.endpoints")
    deps = importlib.import_module("app.api.deps")
    monkeypatch.setattr(deps.settings, "USE_API_KEY", True)
    monkeypatch.setattr(deps.settings, "API_KEY", "configured-key")
    calls = []

    class Service:
        async def verify_and_issue(self, request):
            calls.append(request)
            return modules.models.PreTravelVerificationResult(
                is_valid=True,
                wallet_offer=modules.models.PreTravelWalletOffer.model_validate_json(
                    json.dumps(offer_payload())
                ),
            )

    monkeypatch.setattr(endpoints, "pretravel_service", Service())
    app = FastAPI()
    app.include_router(endpoints.router)
    with TestClient(app) as client:
        for key in (None, "wrong-key", "test_api_key"):
            response = client.post(
                "/api/pre-travel/verify",
                json={},
                headers={"X-API-Key": key} if key else {},
            )
            assert response.status_code == 401
        assert calls == []
        headers = {"X-API-Key": "configured-key"}
        response = client.post(
            "/api/pre-travel/verify",
            json={"organization_id": "foreign"},
            headers=headers,
        )
        assert response.status_code == 422 and not calls
        response = client.post("/api/pre-travel/verify", json={}, headers=headers)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"
        assert response.json()["credential"] is None
        assert response.json()["wallet_offer"]["status"] == "pending"
        monkeypatch.setattr(deps.settings, "API_KEY", "")
        assert (
            client.post("/api/pre-travel/verify", json={}, headers=headers).status_code
            == 503
        )
        monkeypatch.setattr(deps.settings, "USE_API_KEY", False)
        assert (
            client.post("/api/pre-travel/verify", json={}, headers=headers).status_code
            == 503
        )
        assert len(calls) == 1


def test_transport_rejects_foreign_embedded_issuer(modules, binding):
    payload = offer_payload()
    payload["credential_offer_uri"] = payload["credential_offer_uri"].replace(
        "issuance.example", "foreign.example"
    )
    client = modules.client.RustPreTravelIssuance(
        binding,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    )
    with pytest.raises(modules.client.PreTravelIssuanceError):
        asyncio.run(client.offer({}))


def test_public_issuer_override_does_not_change_management_endpoint(modules, binding):
    payload = offer_payload()
    payload["credential_offer_uri"] = payload["credential_offer_uri"].replace(
        "issuance.example", "public.example"
    )
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=payload)

    client = modules.client.RustPreTravelIssuance(
        replace(binding, credential_issuer_url="https://public.example/org/org-a"),
        transport=httpx.MockTransport(handler),
    )
    assert asyncio.run(client.offer({})).status == "pending"
    assert requests[0].url.host == "issuance.example"


def test_transport_rejects_duplicate_offer_parameter_including_blank(modules, binding):
    payload = offer_payload()
    payload["credential_offer_uri"] += "&credential_offer="
    client = modules.client.RustPreTravelIssuance(
        binding,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    )
    with pytest.raises(modules.client.PreTravelIssuanceError):
        asyncio.run(client.offer({}))
