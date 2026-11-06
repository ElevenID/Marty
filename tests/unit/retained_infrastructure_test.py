"""Exercise the live billing/commerce common APIs with Core imports blocked."""

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def test_billing_and_commerce_import_and_use_without_identity_runtime(tmp_path):
    script = r'''
import asyncio
from dataclasses import dataclass
import importlib.abc
import os
from pathlib import Path
import sys

class NoIdentityRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.partition(".")[0] in {
            "_marty_rs", "marty_rs", "marty_verification", "marty_verification_py",
            "marty_iso18013", "marty_plugin", "digital_identity",
        }:
            raise AssertionError("Retired identity dependency requested: " + fullname)

sys.meta_path.insert(0, NoIdentityRuntime())
from marty_common.service_setup import create_service_app
from marty_common.database import DatabaseConfig, DatabaseManager
from marty_common.events import DomainEvent
from marty_common.cedar_engine import AuthzDecision, CedarEngine
from marty_common import compute_pairwise_id, generate_holder_secret
from fastapi.testclient import TestClient
from sqlalchemy import text

os.environ["ENVIRONMENT"] = "test"
# Use the factory's actual defaults, including its optional metrics import.
app = create_service_app(title="Billing", service_name="billing-service")
with TestClient(app) as client:
    for endpoint in ("/health", "/ready", "/startup"):
        response = client.get(endpoint, headers={"X-Request-ID": "billing-closure"})
        assert response.status_code == 200
        assert response.json()["service"] == "billing-service"
        assert response.headers["x-request-id"] == "billing-closure"
        assert response.headers["x-content-type-options"] == "nosniff"

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + str(Path.cwd() / "billing.sqlite")
config = DatabaseConfig.from_env("billing")
assert config.schema == "billing_service"
db = DatabaseManager(config)
factory = db.session_factory
assert factory is db.session_factory

async def use_database():
    async with factory() as session:
        assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    await db.close()

asyncio.run(use_database())

@dataclass
class InvoiceCreated(DomainEvent):
    invoice_id: str = "invoice-test"

event = InvoiceCreated(source_service="billing")
assert event.to_dict()["data"] == {"invoice_id": "invoice-test"}
assert event.to_dict()["event_type"] == "invoice.created"

schema = ''' + '"""' + '''namespace Billing {
  entity User;
  entity Organization;
  action "read" appliesTo { principal: User, resource: Organization, context: {} };
}''' + '"""' + '''
engine = CedarEngine(schema=schema, policies='permit(principal == Billing::User::"allowed", action, resource);')
def authorize(identity):
    return engine.is_authorized(
        principal='Billing::User::"' + identity + '"', action='Billing::Action::"read"',
        resource='Billing::Organization::"org"', context={}, entities=[],
    )
allowed, denied = authorize("allowed"), authorize("denied")
assert isinstance(allowed, AuthzDecision)
assert allowed.allowed and not allowed.errors
assert not denied.allowed and not denied.errors
engine.policies = "invalid Cedar"
assert not authorize("allowed").allowed

secret = generate_holder_secret()
assert compute_pairwise_id(secret, "a", "holder") != compute_pairwise_id(secret, "b", "holder")
'''
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "packages/marty-common")
    # The executor's transport proxy is irrelevant to local ASGI/SQLite tests.
    for name in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        env.pop(name, None)
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_removed_automatic_acme_mode_fails_before_file_or_network_access(monkeypatch):
    from marty_common import grpc_tls

    def forbid_file(*args, **kwargs):
        raise AssertionError("Removed ACME mode must reject before reading local key data")

    monkeypatch.setattr(grpc_tls, "_read_file_if_exists", forbid_file)
    import pytest
    with pytest.raises(RuntimeError, match="ACME issuance is retired"):
        grpc_tls.configure_server_security({"acme_enabled": True, "acme_domain": "example.test"})


def test_removed_jwt_environment_rejects_before_reading_key_files(monkeypatch):
    from marty_common.auth_interceptor import create_auth_interceptor
    import pytest

    def forbid_file(*args, **kwargs):
        raise AssertionError("Removed JWT mode must reject without reading key files")

    monkeypatch.setattr(Path, "read_text", forbid_file)
    monkeypatch.setenv("MARTY_JWT_JWKS_FILE", "/unused-retired-jwks")
    with pytest.raises(ValueError, match="JWT authentication is retired"):
        create_auth_interceptor()
