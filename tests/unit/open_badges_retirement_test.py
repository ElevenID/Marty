"""Adapter policy rejects legacy OB2 symbols independently of wheel age."""

import importlib
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest


@pytest.fixture
def adapters(monkeypatch):
    # Exercise the real adapter modules without unrelated platform integrations.
    # Native functions are traps: these tests make no cryptographic claims.
    previous = {
        name: module
        for name, module in sys.modules.items()
        if name == "marty_common" or name.startswith("marty_common.")
    }
    for name in previous:
        del sys.modules[name]
    package = ModuleType("marty_common")
    package.__path__ = [
        str(Path(__file__).resolve().parents[2] / "packages/marty-common/marty_common")
    ]
    sys.modules["marty_common"] = package

    def forbidden(*args, **kwargs):
        pytest.fail("retired or unrelated native operation was reached")

    try:
        policy = importlib.import_module("marty_common.native_policy")
        for module_name, names in policy.REQUIRED_NATIVE_BACKENDS.items():
            native = ModuleType(module_name)
            for name in names:
                setattr(native, name, forbidden)
            if module_name in {"_marty_rs", "marty_verification"}:
                native.OPEN_BADGES_SUPPORTED_VERSIONS = ("3.0",)
            monkeypatch.setitem(sys.modules, module_name, native)
        yield policy, importlib.import_module("marty_common.native_backends"), forbidden
    finally:
        for name in list(sys.modules):
            if name == "marty_common" or name.startswith("marty_common."):
                del sys.modules[name]
        sys.modules.update(previous)


@pytest.mark.parametrize("legacy_symbols", [False, True])
def test_ob2_is_neither_required_nor_exported_from_declared_ob3_wheels(adapters, legacy_symbols, monkeypatch):
    policy, backends, forbidden = adapters
    if legacy_symbols:
        for name in policy.RETIRED_OB2_OPERATIONS:
            setattr(sys.modules["marty_verification"], name, forbidden)
    bridge = importlib.import_module("marty_common.crypto_bridge")
    for name in (
        "open_badge_ob2_issue",
        "open_badge_ob2_verify",
        "issue_open_badge_ob2",
        "verify_open_badge_ob2",
    ):
        assert not hasattr(bridge, name)
        assert name not in bridge.__all__
        assert name not in bridge.get_available_functions()["marty_verification"]
    for alias in ("marty_verification", "marty_verification_py", "_marty_verification"):
        # Both canonical and legacy package names must receive the same filtered view.
        with monkeypatch.context() as aliases:
            aliases.setitem(sys.modules, alias, sys.modules["marty_verification"])
            view = backends.load_native_backend(alias)
            for name in policy.RETIRED_OB2_OPERATIONS:
                assert name not in dir(view)
                with pytest.raises(backends.NativeOperationError, match="Open Badges 3.0"):
                    getattr(view, name)


def test_ob3_adapter_keeps_request_and_response_unchanged(adapters):
    request = {"credential": {"type": ["VerifiableCredential", "OpenBadgeCredential"]}}
    response = {"valid": False, "errors": ["fixture verification result"]}
    calls = []

    def verify(request_json):
        calls.append(json.loads(request_json))
        return json.dumps(response)

    sys.modules["marty_verification"].open_badge_ob3_verify = verify
    bridge = importlib.import_module("marty_common.crypto_bridge")
    assert bridge.verify_open_badge_ob3(request) == response
    assert calls == [request]


@pytest.mark.parametrize("module_name", ["_marty_rs", "marty_verification"])
@pytest.mark.parametrize("versions", [None, (), ("2.0", "3.0"), "3.0"])
def test_historical_or_incompatible_wheels_fail_before_public_adapter_use(adapters, module_name, versions):
    _, backends, _ = adapters
    native = sys.modules[module_name]
    if versions is None:
        del native.OPEN_BADGES_SUPPORTED_VERSIONS
    else:
        native.OPEN_BADGES_SUPPORTED_VERSIONS = versions
    with pytest.raises(backends.NativeBackendUnavailable, match="Core revision with OB2 retired"):
        backends.load_native_backend(module_name)
    with pytest.raises(backends.NativeBackendUnavailable, match="Core revision with OB2 retired"):
        importlib.import_module("marty_common.crypto_bridge")
