"""Exercise the live billing/commerce common APIs with Core imports blocked."""

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def test_billing_and_commerce_import_and_use_without_identity_runtime(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "packages/marty-common")
    # The executor's transport proxy is irrelevant to local ASGI/SQLite tests.
    for name in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        env.pop(name, None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests/probes/common_wheel_smoke.py")], cwd=tmp_path, env=env,
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
