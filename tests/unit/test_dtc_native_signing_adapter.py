from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from marty_plugin.dtc_engine.src import dtc_engine_service as service_module
from marty_plugin.proto import dtc_engine_pb2


def _service(tmp_path: Any) -> Any:
    service = service_module.DTCEngineService.__new__(service_module.DTCEngineService)
    service.logger = logging.getLogger("test.dtc.native")
    service.dtc_storage_dir = str(tmp_path)
    service._dtc_store = {}
    service.signer_id = "configured-signer"
    service.signer_public_key_pem = "PUBLIC KEY PEM"
    service.document_signer_client = None
    return service


def _store_unsigned(service: Any, dtc_id: str = "dtc-1") -> dict[str, Any]:
    record: dict[str, Any] = {
        "dtc_id": dtc_id,
        "passport_number": "L898902C3",
        "access_key_hash": "owned-by-python",
        "is_signed": False,
        "signature_info": None,
    }
    path = Path(service.dtc_storage_dir) / f"{dtc_id}.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return record


def _request(dtc_id: str = "dtc-1") -> Any:
    return dtc_engine_pb2.SignDTCRequest(dtc_id=dtc_id, access_key="secret")


def _store_native_unsigned(service: Any, dtc_id: str = "dtc-1") -> dict[str, Any]:
    created = json.loads(
        service_module.crypto_bridge.dtc_create(
            json.dumps(
                {
                    "dtc_id": dtc_id,
                    "passport_number": "P1234567",
                    "issuing_authority": "USA",
                    "issue_date": "2024-01-01",
                    "expiry_date": "2030-01-01",
                    "personal_details": {
                        "first_name": "JOHN",
                        "last_name": "DOE",
                        "date_of_birth": "1990-01-01",
                        "gender": "M",
                        "nationality": "USA",
                    },
                    "data_groups": [
                        {"dg_number": 1, "data": "ZGcx", "data_type": "MRZ"}
                    ],
                    "dtc_type": 4,
                    "type1_profile": {
                        "mrz_line1": "P<USADOE<<JOHN<<<<<<<<<<<<<<<<<<<<<<<",
                        "mrz_line2": "1234567890USA8504031M3504027<<<<<<<6",
                        "sod_hash": "",
                        "issuing_state": "USA",
                        "passive_auth_ok": True,
                    },
                }
            )
        )
    )
    created["access_key_hash"] = "owned-by-python"
    path = Path(service.dtc_storage_dir) / f"{dtc_id}.json"
    path.write_text(json.dumps(created), encoding="utf-8")
    return created


def test_external_signer_receives_only_native_canonical_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    service = _service(tmp_path)
    record = _store_unsigned(service)
    canonical = b"canonical-rust-dtc-payload"
    provider_signature = b"provider-signature"
    observed: dict[str, Any] = {}

    def prepare(payload: str) -> str:
        native_record = json.loads(payload)
        native_record.pop("access_key_hash", None)
        return json.dumps(
            {
                "dtc": native_record,
                "signing_input_base64": base64.b64encode(canonical).decode("ascii"),
                "signature_encoding": "DER_BASE64",
            }
        )

    def assemble(payload: str) -> str:
        envelope = json.loads(payload)
        observed["envelope"] = envelope
        assert base64.b64decode(envelope["signature_base64"]) == provider_signature
        signed = dict(envelope["dtc"])
        signed["is_signed"] = True
        signed["signature_info"] = {
            "signature_date": "2026-08-11T00:00:00Z",
            "signer_id": envelope["signer_id"],
            "signature": envelope["signature_base64"],
            "is_valid": True,
            "signer_public_key_pem": envelope["signer_public_key_pem"],
        }
        return json.dumps(signed)

    class Stub:
        def SignDocument(self, request: Any) -> Any:  # noqa: N802
            observed["document_content"] = request.document_content
            return SimpleNamespace(
                success=True,
                error_message="",
                signature_info=SimpleNamespace(
                    signature=provider_signature,
                    signer_id="remote-signer",
                    signature_date="2026-08-11T00:00:00Z",
                ),
            )

    service.document_signer_client = SimpleNamespace(stub=Stub())
    monkeypatch.setattr(service_module, "verify_password", lambda *_: True)
    monkeypatch.setattr(service_module.crypto_bridge, "dtc_prepare_signing", prepare)
    monkeypatch.setattr(
        service_module.crypto_bridge, "dtc_assemble_signature", assemble
    )

    response = service.SignDTC(_request(), SimpleNamespace())

    assert response.success is True
    assert observed["document_content"] == canonical
    assert observed["envelope"]["signer_public_key_pem"] == "PUBLIC KEY PEM"
    stored = json.loads((tmp_path / "dtc-1.json").read_text(encoding="utf-8"))
    assert stored["is_signed"] is True
    assert stored["signature_info"]["is_valid"] is True
    assert stored["access_key_hash"] == record["access_key_hash"]


def test_external_signer_round_trip_uses_real_native_verification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    service = _service(tmp_path)
    record = _store_native_unsigned(service)
    private_raw, public_raw = service_module.crypto_bridge.ecdsa_p256_generate()
    public_der = service_module.crypto_bridge.raw_public_key_to_spki(public_raw, "P256")
    service.signer_public_key_pem = service_module.crypto_bridge.save_public_key_pem(
        public_der
    )
    observed: dict[str, bytes] = {}

    class Stub:
        def SignDocument(self, request: Any) -> Any:  # noqa: N802
            observed["document_content"] = request.document_content
            signature = service_module.crypto_bridge.ecdsa_p256_sign(
                private_raw, request.document_content
            )
            return SimpleNamespace(
                success=True,
                error_message="",
                signature_info=SimpleNamespace(
                    signature=signature,
                    signer_id="real-native-signer",
                    signature_date="2026-08-11T00:00:00Z",
                ),
            )

    service.document_signer_client = SimpleNamespace(stub=Stub())
    monkeypatch.setattr(service_module, "verify_password", lambda *_: True)

    response = service.SignDTC(_request(), SimpleNamespace())

    assert response.success is True
    assert observed["document_content"]
    stored = json.loads((tmp_path / "dtc-1.json").read_text(encoding="utf-8"))
    assert stored["is_signed"] is True
    assert stored["signature_info"]["is_valid"] is True
    assert stored["signature_info"]["signer_id"] == "real-native-signer"
    assert stored["access_key_hash"] == record["access_key_hash"]


def test_invalid_external_signature_is_never_persisted_as_signed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    service = _service(tmp_path)
    _store_unsigned(service)
    service.document_signer_client = SimpleNamespace(
        stub=SimpleNamespace(
            SignDocument=lambda _: SimpleNamespace(
                success=True,
                signature_info=SimpleNamespace(
                    signature=b"invalid",
                    signer_id="remote-signer",
                    signature_date="",
                ),
            )
        )
    )
    monkeypatch.setattr(service_module, "verify_password", lambda *_: True)
    monkeypatch.setattr(
        service_module.crypto_bridge,
        "dtc_prepare_signing",
        lambda payload: json.dumps(
            {
                "dtc": json.loads(payload),
                "signing_input_base64": base64.b64encode(b"canonical").decode("ascii"),
            }
        ),
    )

    def reject_signature(_: str) -> str:
        raise RuntimeError("external signature verification failed")

    monkeypatch.setattr(
        service_module.crypto_bridge, "dtc_assemble_signature", reject_signature
    )

    response = service.SignDTC(_request(), SimpleNamespace())

    assert response.success is False
    stored = json.loads((tmp_path / "dtc-1.json").read_text(encoding="utf-8"))
    assert stored["is_signed"] is False


@pytest.mark.parametrize("source", ["env-pem", "env-path", "config-pem", "config-path"])
def test_private_key_configuration_fails_before_files_or_provider(
    monkeypatch, tmp_path, source
):
    monkeypatch.delenv("DTC_SIGNING_KEY_PEM", raising=False)
    monkeypatch.delenv("DTC_SIGNING_KEY_PATH", raising=False)
    value = (
        "retired-private-key-material"
        if source.endswith("pem")
        else str(tmp_path / "absent-private-key.pem")
    )
    settings = {}
    if source.startswith("env"):
        monkeypatch.setenv(
            "DTC_SIGNING_KEY_PEM" if source.endswith("pem") else "DTC_SIGNING_KEY_PATH",
            value,
        )
    else:
        settings[
            "signing_key_pem" if source.endswith("pem") else "signing_key_path"
        ] = value
    config = SimpleNamespace(get_service=lambda _: settings)

    def forbidden(*args, **kwargs):
        pytest.fail(
            "retired private-key configuration reached a file or provider operation"
        )

    monkeypatch.setattr(service_module.os, "makedirs", forbidden)
    monkeypatch.setattr(service_module, "GRPCClient", forbidden)
    monkeypatch.setattr(service_module.crypto_bridge, "load_private_key_pem", forbidden)
    with pytest.raises(
        ValueError, match="Application-held DTC signing keys are retired"
    ) as error:
        service_module.DTCEngineService(config)
    assert value not in str(error.value)


def test_constructor_preserves_public_trust_identity_and_storage_settings(
    monkeypatch, tmp_path
):
    monkeypatch.delenv("DTC_SIGNING_KEY_PEM", raising=False)
    monkeypatch.delenv("DTC_SIGNING_KEY_PATH", raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("DTC_SIGNER_PUBLIC_KEY_PEM", raising=False)
    files = {}
    for name, content in {
        "public": "public-only-binding",
        "anchors": "anchor-a\n\nanchor-b",
        "chain": "chain-a\n\nchain-b",
    }.items():
        path = tmp_path / (name + ".pem")
        path.write_text(content, encoding="utf-8")
        files[name] = str(path)
    config = SimpleNamespace(
        get_service=lambda _: {
            "signer_id": "configured-provider",
            "signer_public_key_path": files["public"],
            "trust_anchors_path": files["anchors"],
            "certificate_chain_path": files["chain"],
        }
    )
    client = SimpleNamespace(stub=object())
    monkeypatch.setattr(service_module, "GRPCClient", lambda **kwargs: client)
    service = service_module.DTCEngineService(config)
    assert (
        service.document_signer_client is client
        and service.signer_id == "configured-provider"
    )
    assert service.signer_public_key_pem == "public-only-binding"
    assert service.trust_anchors_pem == ["anchor-a", "anchor-b"]
    assert service.certificate_chain_pem == ["chain-a", "chain-b"]
    assert Path(service.dtc_storage_dir).is_dir()
    assert not hasattr(service, "signing_key_pem")


def test_missing_provider_cannot_sign_or_mutate_record(monkeypatch, tmp_path):
    service = _service(tmp_path)
    _store_native_unsigned(service)
    path = tmp_path / "dtc-1.json"
    before = path.read_bytes()
    monkeypatch.setattr(service_module, "verify_password", lambda *_: True)

    def forbidden(*args, **kwargs):
        pytest.fail("DTC attempted local signing without a provider")

    monkeypatch.setattr(service_module.crypto_bridge, "dtc_sign", forbidden)
    response = service.SignDTC(_request(), SimpleNamespace())
    assert response.success is False
    assert path.read_bytes() == before and service._dtc_store == {}
