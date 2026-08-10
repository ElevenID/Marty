"""Tests for fail-closed native backend loading."""

import asyncio
import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

from marty_plugin.native_backends import (
    NativeBackendUnavailable,
    NativeOperationError,
    backend_diagnostics,
    require_backend,
)
from marty_plugin.pkd_service.app.utils.certificate_validator import (
    CertificateValidator,
)


def test_missing_native_backend_raises_typed_error() -> None:
    with pytest.raises(NativeBackendUnavailable, match="Required native backend"):
        require_backend("marty_backend_that_does_not_exist")


def test_backend_diagnostics_reports_unavailable_backends() -> None:
    diagnostics = backend_diagnostics()

    assert set(diagnostics) == {"marty_iso18013", "marty_verification", "_marty_rs"}
    assert all("available" in value for value in diagnostics.values())


def test_incompatible_native_backend_raises_typed_error(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules, "marty_verification", ModuleType("marty_verification")
    )
    with pytest.raises(NativeBackendUnavailable, match="incompatible; missing"):
        require_backend("marty_verification")


def test_iso18013_transport_adapter_uses_native_surface(monkeypatch) -> None:
    class FakeHttpsTransport:
        def __init__(self, url: str) -> None:
            self.url = url
            self.connected = False

        def connect(self) -> None:
            self.connected = True

        def send(self, data: bytes) -> None:
            assert data == b"request"

        def receive(self) -> bytes:
            return b"response"

        def close(self) -> None:
            self.connected = False

        def is_connected(self) -> bool:
            return self.connected

    native = ModuleType("marty_iso18013")
    for name in (
        "TransportMethod",
        "EngagementMethod",
        "SessionState",
        "ResponseStatus",
        "DeviceEngagement",
        "MdlRequest",
        "MdlResponse",
        "SelectiveDisclosure",
        "Session",
        "SessionConfig",
    ):
        setattr(native, name, object())
    native.HttpsTransport = FakeHttpsTransport
    native.BleTransport = object()
    native.NfcTransport = object()
    monkeypatch.setitem(sys.modules, "marty_iso18013", native)
    sys.modules.pop("marty_plugin.iso18013_bridge", None)

    try:
        bridge = importlib.import_module("marty_plugin.iso18013_bridge")
        assert bridge.transport_capabilities() == {
            "ble": True,
            "nfc": True,
            "https": True,
        }

        async def exercise() -> None:
            transport = bridge.HttpsTransport("https://example.invalid/mdl")
            await transport.connect()
            assert transport.is_connected()
            await transport.send(b"request")
            assert await transport.receive() == b"response"
            await transport.close()
            assert not transport.is_connected()

        asyncio.run(exercise())
    finally:
        sys.modules.pop("marty_plugin.iso18013_bridge", None)


def test_legacy_iso_crypto_surface_fails_closed() -> None:
    module = importlib.import_module("marty_plugin.iso18013.crypto")

    with pytest.raises(NativeOperationError, match="remain in Rust"):
        module.SessionEncryption(b"python-session-key")


def test_legacy_iso_protocol_surface_fails_closed() -> None:
    module = importlib.import_module("marty_plugin.iso18013.protocols")

    with pytest.raises(NativeOperationError, match="state machine was removed"):
        module.ISO18013_5Protocol()


def test_legacy_iso_reference_apps_fail_closed() -> None:
    holder = importlib.import_module("marty_plugin.iso18013.apps.holder")
    reader = importlib.import_module("marty_plugin.iso18013.apps.reader")

    with pytest.raises(NativeOperationError, match="holder demo was retired"):
        holder.ISO18013HolderApp(holder.HolderConfig(holder_id="holder"))
    with pytest.raises(NativeOperationError, match="reader demo was retired"):
        reader.ISO18013ReaderApp(
            reader.ReaderConfig(
                reader_id="reader",
                organization="Example",
                supported_transports=["https"],
            )
        )


def test_pkd_certificate_validator_routes_chain_to_native(monkeypatch) -> None:
    anchors: list[bytes] = []
    intermediates: list[bytes] = []
    validated: list[str] = []

    class Result:
        valid = True

    class FakeChainValidator:
        def add_trust_anchor_der(self, value: bytes) -> None:
            anchors.append(value)

        def add_intermediate_der(self, value: bytes) -> None:
            intermediates.append(value)

        def validate_chain(self, chain: list[str]) -> Result:
            validated.extend(chain)
            return Result()

    native = ModuleType("marty_verification")
    native.ChainValidator = FakeChainValidator
    native.load_certificate_der = bytes
    native.certificate_der_to_pem = lambda value: f"pem:{value.decode()}"
    native.certificate_pem_to_der = lambda value: value.removeprefix("pem:").encode()

    module = importlib.import_module(
        "marty_plugin.pkd_service.app.utils.certificate_validator"
    )
    monkeypatch.setattr(module, "require_backend", lambda _name: native)

    validator = CertificateValidator(
        trust_roots=[b"root"], other_certs=[b"intermediate"]
    )
    assert validator.validate_chain([b"leaf", b"issuer"])
    assert anchors == [b"root"]
    assert intermediates == [b"intermediate"]
    assert validated == ["pem:leaf", "pem:issuer"]


def test_pkd_certificate_validator_propagates_missing_backend(monkeypatch) -> None:
    module = importlib.import_module(
        "marty_plugin.pkd_service.app.utils.certificate_validator"
    )

    def unavailable(_name: str) -> None:
        raise NativeBackendUnavailable("native backend missing")

    monkeypatch.setattr(module, "require_backend", unavailable)
    with pytest.raises(NativeBackendUnavailable, match="native backend missing"):
        CertificateValidator().validate(b"certificate")


def test_trust_master_list_upload_uses_native_signature_and_parsing(
    monkeypatch,
) -> None:
    from marty_plugin.trust_svc import api
    from marty_plugin.trust_svc.models import MasterListUploadRequest

    class Native:
        def parse_master_list(self, value: bytes) -> dict:
            assert value == b"signed-master-list"
            return {
                "certificates": [
                    {
                        "subject": "C=US,CN=CSCA",
                        "issuer": "C=US,CN=CSCA",
                        "serial_number": "01",
                        "country": "US",
                        "not_before": "2026-01-01T00:00:00Z",
                        "not_after": "2036-01-01T00:00:00Z",
                        "der_bytes": b"csca",
                    }
                ]
            }

        def verify_master_list_signature(self, value: bytes, signer: bytes) -> bool:
            return value == b"signed-master-list" and signer == b"signer"

        def get_certificate_info(self, _value: bytes) -> dict:
            return {"fingerprint_sha256": "ab", "key_usage": ["keyCertSign"]}

        def get_certificate_public_key(self, _value: bytes) -> bytes:
            return b"spki"

        def detect_public_key_type(self, _value: bytes) -> str:
            return "ecdsa-p256"

        def certificate_pem_to_der(self, _value: str) -> bytes:
            raise AssertionError("DER signer should not require conversion")

    class Database:
        added: list[dict] = []

        async def get_trust_anchors(self, active_only: bool = True) -> list[dict]:
            assert active_only
            return [{"certificate_data": b"signer"}]

        async def add_trust_anchor(self, value: dict) -> str:
            self.added.append(value)
            return "anchor-1"

    database = Database()
    monkeypatch.setattr(api, "require_backend", lambda _name: Native())
    result = asyncio.run(
        api.process_master_list_upload(
            MasterListUploadRequest(
                country_code="USA", master_list_data=b"signed-master-list"
            ),
            database,
        )
    )

    assert result.success
    assert result.certificates_processed == 1
    assert result.trust_anchors_added == 1
    assert database.added[0]["certificate_data"] == b"csca"


def test_trust_master_list_rejects_untrusted_signature(monkeypatch) -> None:
    from marty_plugin.trust_svc import api
    from marty_plugin.trust_svc.models import MasterListUploadRequest

    native = SimpleNamespace(
        parse_master_list=lambda _value: {"certificates": [{"der_bytes": b"csca"}]},
        verify_master_list_signature=lambda _value, _signer: False,
    )
    database = SimpleNamespace(
        get_trust_anchors=lambda active_only=True: None,
    )

    async def anchors(active_only: bool = True) -> list[dict]:
        assert active_only
        return [{"certificate_data": b"untrusted"}]

    database.get_trust_anchors = anchors
    monkeypatch.setattr(api, "require_backend", lambda _name: native)

    with pytest.raises(NativeOperationError, match="pinned trust anchor"):
        asyncio.run(
            api.process_master_list_upload(
                MasterListUploadRequest(
                    country_code="USA", master_list_data=b"signed-master-list"
                ),
                database,
            )
        )
