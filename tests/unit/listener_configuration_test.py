"""Keep explicit deployment bind controls while defaulting diagnostics to loopback."""

import asyncio
import importlib.util
import sys
from types import SimpleNamespace

import pytest

from tests.unit.authenticated_boundary_test import ROOT, modules


@pytest.mark.parametrize("host", [None, "192.0.2.10"])
def test_metrics_listener_passes_selected_bind_to_uvicorn(modules, monkeypatch, host):
    module = modules("marty_common.metrics_server")
    configurations = []

    async def serve():
        await asyncio.Event().wait()

    def server(configuration):
        configurations.append(configuration)
        return SimpleNamespace(serve=serve)

    monkeypatch.setattr(module.uvicorn, "Server", server)
    instance = module.init_metrics_server("listener-test", **({"host": host} if host else {}))

    async def run():
        await instance.start()
        await instance.stop()

    asyncio.run(run())
    assert configurations[0].host == (host or "127.0.0.1")
    assert "/health" in {route.path for route in instance.app.routes}


@pytest.mark.parametrize("host", [None, "192.0.2.11"])
def test_trust_service_configuration_keeps_explicit_environment_bind(monkeypatch, host):
    monkeypatch.delenv("TRUST_SVC_HOST", raising=False)
    if host:
        monkeypatch.setenv("TRUST_SVC_HOST", host)
    name = "trust_listener_configuration_test_module"
    spec = importlib.util.spec_from_file_location(name, ROOT / "src/marty_plugin/trust_svc/config.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    configuration = module.TrustServiceConfig.from_env()
    assert configuration.service.host == (host or "127.0.0.1")
    assert configuration.to_dict()["service"]["host"] == configuration.service.host
