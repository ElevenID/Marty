"""Behavioral checks for fail-closed document-service compatibility adapters."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import pytest

from marty_common.native_backends import NativeOperationError
from marty_common.security.hsm import HSMOperationError, MockHSMService
from marty_plugin.shared.services.key_management_service import (
    KeyManagementService,
    KeyType,
    KeyUsage,
)


ROOT = Path(__file__).resolve().parents[2]


def test_document_mrz_adapter_uses_native_and_mock_adapter_fails_closed() -> None:
    environment = os.environ.copy()
    environment["DEBUG"] = "false"
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(ROOT / "src"),
            str(ROOT / "packages/marty-common"),
            str(ROOT / "src/marty_plugin/document_processing"),
        )
    )
    script = """
import asyncio
from app.services.service_clients import (
    GrpcInspectionSystemClient,
    MockInspectionSystemClient,
    ServiceClientError,
)

lines = [
    "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
    "L898902C36UTO7408122F1204159ZE184226B<<<<<10",
]
result = asyncio.run(
    GrpcInspectionSystemClient().validate_mrz({"mrzLines": lines})
)
assert result["valid"] is True
assert result["checksums_valid"] is True

try:
    asyncio.run(MockInspectionSystemClient().validate_mrz({}))
except ServiceClientError as exc:
    assert "mock backend is disabled" in str(exc)
else:
    raise AssertionError("retired mock verification adapter returned successfully")
"""
    with TemporaryDirectory() as directory:
        Path(directory, ".env").write_text(
            "UNRELATED_COMPATIBILITY_SETTING=must-not-break-startup\n",
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            cwd=directory,
            env=environment,
        )


def test_shared_key_management_rejects_software_custody_without_writing_files(tmp_path):
    service = KeyManagementService(str(tmp_path))
    for key_type in (KeyType.RSA, KeyType.EC):
        with pytest.raises(NativeOperationError, match="Rust managed-KMS"):
            service.generate_key("test-key", key_type, KeyUsage.DOCUMENT_SIGNING)
    with pytest.raises(NativeOperationError, match="Private-key export"):
        service.export_key_as_pem("test-key", include_private=True)
    assert list(tmp_path.iterdir()) == []


def test_existing_software_key_data_is_preserved_but_cannot_be_loaded(tmp_path):
    import json

    (tmp_path / "old.json").write_text(
        json.dumps({"key_id": "old", "hsm_backed": False})
    )
    (tmp_path / "old.key").write_bytes(b"private-data-must-remain-untouched")
    service = KeyManagementService(str(tmp_path))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(NativeOperationError, match="Private-key loading"):
        service.load_private_key("old")
    with pytest.raises(NativeOperationError, match="Private-key export"):
        service.export_key_as_pem("old", include_private=True)
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_shared_key_management_preserves_managed_provider_metadata_and_public_export(
    tmp_path,
):
    from types import SimpleNamespace
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    public_pem = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        .decode("ascii")
    )
    calls = []

    def generate_key(**kwargs):
        calls.append(kwargs)
        return {"key_handle": "opaque-test-handle", "public_key_pem": public_pem}

    service = KeyManagementService(
        str(tmp_path),
        use_hsm=True,
        hsm_service=SimpleNamespace(generate_key=generate_key),
    )
    result = service.generate_key(
        "test-key",
        KeyType.EC,
        KeyUsage.DOCUMENT_SIGNING,
        metadata={"intent": "retained"},
    )
    assert result["hsm_key_handle"] == "opaque-test-handle"
    assert result["metadata"] == {"intent": "retained"}
    assert calls == [{"key_id": "test-key", "key_type": "ec", "key_size": None}]
    assert service.export_key_as_pem("test-key").replace(
        b"\r\n", b"\n"
    ) == public_pem.encode("ascii")
    assert not list(tmp_path.glob("*.key"))
    with pytest.raises(NativeOperationError, match="PKCS#12"):
        service.export_key_as_pkcs12("test-key", b"secret")
    with pytest.raises(NativeOperationError, match="backup"):
        service.backup_keys("retired.zip", b"secret")
    with pytest.raises(NativeOperationError, match="restore"):
        service.restore_keys("retired.zip", b"secret")
    with pytest.raises(HSMOperationError, match="disabled"):
        MockHSMService().initialize({})


def test_private_key_loader_never_invokes_provider_secret_export(tmp_path):
    from types import SimpleNamespace

    def forbidden(*args, **kwargs):
        raise AssertionError("private provider retrieval must never be attempted")

    service = KeyManagementService(
        str(tmp_path), use_hsm=True, hsm_service=SimpleNamespace(get_key=forbidden)
    )
    with pytest.raises(NativeOperationError, match="Private-key loading"):
        service.load_private_key("managed-key")
    assert list(tmp_path.iterdir()) == []
