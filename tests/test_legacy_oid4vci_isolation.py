import sys
from pathlib import Path
from types import ModuleType

from fastapi.testclient import TestClient

# The repository's top-level package initializer imports the optional compiled
# `_marty_rs` extension. These legacy FastAPI routes are pure Python, so expose
# the package path without executing that unrelated native initializer.
if "marty_plugin" not in sys.modules:
    package = ModuleType("marty_plugin")
    package.__path__ = [str(Path(__file__).parents[1] / "src" / "marty_plugin")]
    sys.modules["marty_plugin"] = package

from marty_plugin.legacy_apps.ui_app.app import create_app
from marty_plugin.legacy_apps.ui_app.config import UiSettings


METADATA_PATH = "/oidc4vci/.well-known/openid-credential-issuer"


def test_legacy_oid4vci_is_disabled_by_default() -> None:
    client = TestClient(create_app(UiSettings()))

    response = client.get(METADATA_PATH)

    assert response.status_code == 410
    assert "draft-era" in response.json()["detail"]


def test_legacy_oid4vci_can_be_enabled_for_compatibility() -> None:
    settings = UiSettings(UI_LEGACY_OID4VCI_ENABLED=True)
    client = TestClient(create_app(settings))

    response = client.get(METADATA_PATH)

    assert response.status_code == 200
    assert response.json()["credential_issuer"] == settings.credential_issuer


def test_legacy_oid4vci_operations_are_marked_deprecated() -> None:
    client = TestClient(create_app(UiSettings()))

    schema = client.get("/openapi.json").json()

    assert schema["paths"][METADATA_PATH]["get"]["deprecated"] is True
    assert schema["paths"]["/oidc4vci/token"]["post"]["deprecated"] is True
    assert schema["paths"]["/oidc4vci/credential"]["post"]["deprecated"] is True
