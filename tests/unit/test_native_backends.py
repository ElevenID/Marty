"""Tests for fail-closed native backend loading."""

import asyncio
import importlib
import sys
from types import ModuleType

import pytest

from marty_plugin.native_backends import (
    NativeBackendUnavailable,
    backend_diagnostics,
    require_backend,
)
from marty_plugin.pkd_service.app.utils.certificate_validator import CertificateValidator


def test_missing_native_backend_raises_typed_error() -> None:
    with pytest.raises(NativeBackendUnavailable, match="Required native backend"):
        require_backend("marty_backend_that_does_not_exist")


def test_backend_diagnostics_reports_unavailable_backends() -> None:
    diagnostics = backend_diagnostics()

    assert set(diagnostics) == {"marty_iso18013", "marty_verification", "_marty_rs"}
    assert all("available" in value for value in diagnostics.values())


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
    for name in ("TransportMethod", "EngagementMethod", "SessionState", "ResponseStatus"):
        setattr(native, name, object())
    native.HttpsTransport = FakeHttpsTransport
    monkeypatch.setitem(sys.modules, "marty_iso18013", native)
    sys.modules.pop("marty_plugin.iso18013_bridge", None)

    try:
        bridge = importlib.import_module("marty_plugin.iso18013_bridge")
        assert bridge.transport_capabilities() == {
            "ble": False,
            "nfc": False,
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

    validator = CertificateValidator(trust_roots=[b"root"], other_certs=[b"intermediate"])
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
