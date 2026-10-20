"""Remote signing failures must never manufacture an active credential."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from tests.unit.authenticated_boundary_test import modules  # shared isolated import fixture


@pytest.fixture
def service(modules):
    module = modules("marty_plugin.mdoc_engine.service")
    pb = module.mdoc_engine_pb2
    instance = module.MDocEngineServicer(verification_keys={"kms-key-v1": ("EdDSA", b"public-spki")})
    context = SimpleNamespace(set_code=lambda code: None, set_details=lambda text: None, abort=AsyncMock())
    created = asyncio.run(instance.CreateMDoc(pb.CreateMDocRequest(
        document_type="ID_CARD", document_number="test", person_info=pb.PersonInfo(first_name="Alice"),
        images=[pb.DocumentImage(image_type="PORTRAIT", image_data=b"image")]), context))
    instance.document_signer_stub = SimpleNamespace(SignDocument=AsyncMock())
    return module, instance, context, created.mdoc_id


def response(module, **changes):
    fields = {"signature_date": datetime.now(timezone.utc).isoformat(), "signer_id": "kms-key-v1", "signature": b"signature"}
    fields.update(changes)
    return module.document_signer_pb2.SignResponse(success=True, signature_info=fields)


@pytest.mark.parametrize("case", ["empty", "wrong_type", "failed", "error", "no_signature", "unknown_key", "bad_date", "naive_date", "bad_signature", "native_missing"])
def test_invalid_provider_results_leave_document_pending(service, monkeypatch, case):
    module, instance, context, document_id = service
    result = response(module)
    if case == "empty":
        result = module.document_signer_pb2.SignResponse(success=True)
    elif case == "wrong_type":
        result = SimpleNamespace(success=True, signature_info=result.signature_info)
    elif case == "failed":
        result.success = False
    elif case == "error":
        result.error.code = 3
    elif case == "no_signature":
        result.signature_info.signature = b""
    elif case == "unknown_key":
        result.signature_info.signer_id = "attacker"
    elif case == "bad_date":
        result.signature_info.signature_date = "yesterday"
    elif case == "naive_date":
        result.signature_info.signature_date = "2026-10-20T00:00:00"

    def backend(*args):
        if case == "native_missing":
            raise ImportError("native verifier unavailable")
        return SimpleNamespace(verify_signature=lambda *args: case != "bad_signature")

    monkeypatch.setattr(module, "load_native_backend", backend)
    instance.document_signer_stub.SignDocument.return_value = result
    signed = asyncio.run(instance.SignMDoc(module.mdoc_engine_pb2.SignMDocRequest(mdoc_id=document_id), context))
    assert not signed.success
    assert instance._mdoc_store[document_id].status == "PENDING_SIGNATURE"
    assert not instance._mdoc_store[document_id].signature_info.signature


def test_missing_verification_configuration_does_not_call_remote_signer(service):
    module, instance, context, document_id = service
    instance.verification_keys.clear()
    result = asyncio.run(instance.SignMDoc(module.mdoc_engine_pb2.SignMDocRequest(mdoc_id=document_id), context))
    assert not result.success
    instance.document_signer_stub.SignDocument.assert_not_called()


def test_document_changed_while_signer_is_awaited_is_not_activated(service, monkeypatch):
    module, instance, context, document_id = service
    monkeypatch.setattr(module, "load_native_backend", lambda *args: SimpleNamespace(verify_signature=lambda *args: True))

    async def sign(request):
        instance._mdoc_store[document_id].person_info.first_name = "Changed"
        return response(module)

    instance.document_signer_stub.SignDocument.side_effect = sign
    signed = asyncio.run(instance.SignMDoc(module.mdoc_engine_pb2.SignMDocRequest(mdoc_id=document_id), context))
    assert not signed.success
    assert instance._mdoc_store[document_id].status == "PENDING_SIGNATURE"


def test_native_signature_verification_binds_current_document_and_signer(service):
    pytest.importorskip("marty_verification", reason="Pinned native wheel required; installed in mandatory CI test lane")
    module, instance, context, document_id = service
    key = ed25519.Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    instance.verification_keys = {"kms-key-v1": ("EdDSA", public)}

    async def sign(request):
        return response(module, signature=key.sign(request.document_content))

    instance.document_signer_stub.SignDocument.side_effect = sign
    pb = module.mdoc_engine_pb2
    signed = asyncio.run(instance.SignMDoc(pb.SignMDocRequest(mdoc_id=document_id), context))
    assert signed.success and instance._mdoc_store[document_id].status == "ACTIVE"
    def verify():
        result = asyncio.run(instance.VerifyMDoc(pb.VerifyMDocRequest(mdoc_id=document_id), context))
        assert result.is_valid == result.mdoc_data.signature_info.is_valid
        return result.is_valid
    assert verify()
    document = instance._mdoc_store[document_id]
    document.person_info.first_name = "Mallory"
    assert not verify()
    document.person_info.first_name = "Alice"
    assert verify()
    document.images[0].image_data = b"altered"
    assert not verify()
    document.images[0].image_data = b"image"
    document.signature_info.signer_id = "untrusted-version"
    assert not verify()
