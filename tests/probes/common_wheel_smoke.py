"""Behavioral probe shared by source tests and isolated installed-wheel qualification."""

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
            "marty_iso18013", "_marty_verification", "_marty_iso18013", "marty_plugin", "digital_identity",
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
import marty_common
if "--installed-wheel" in sys.argv:
    from importlib.metadata import distribution
    package_root = Path(marty_common.__file__).resolve()
    assert package_root.is_relative_to(Path(sys.prefix).resolve()), package_root
    installed = distribution("marty-common")
    assert installed.version == marty_common.__version__
    assert not any("editable" in str(entry).lower() for entry in installed.files or [])

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

schema = """namespace Billing {
  entity User;
  entity Organization;
  action "read" appliesTo { principal: User, resource: Organization, context: {} };
}"""
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

print("Common infrastructure works without the identity runtime")
