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
    subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        cwd=ROOT,
        env=environment,
    )


def test_shared_software_key_management_uses_native_or_fails_closed() -> None:
    with TemporaryDirectory() as directory:
        service = KeyManagementService(directory)
        for curve_name in ("secp256r1", "secp384r1"):
            key_id = f"test-{curve_name}"
            service.generate_key(
                key_id,
                KeyType.EC,
                KeyUsage.DOCUMENT_SIGNING,
                curve_name=curve_name,
            )
            assert service.export_key_as_pem(key_id).startswith(
                b"-----BEGIN PUBLIC KEY-----"
            )
            assert service.export_key_as_pem(key_id, include_private=True).startswith(
                b"-----BEGIN PRIVATE KEY-----"
            )

        service.generate_key(
            "test-rsa",
            KeyType.RSA,
            KeyUsage.DOCUMENT_SIGNING,
            key_size=2048,
        )
        assert service.export_key_as_pem("test-rsa").startswith(
            b"-----BEGIN PUBLIC KEY-----"
        )

        with pytest.raises(NativeOperationError, match="P-521"):
            service.generate_key(
                "test-p521",
                KeyType.EC,
                KeyUsage.DOCUMENT_SIGNING,
                curve_name="secp521r1",
            )
        with pytest.raises(NativeOperationError, match="PKCS#12"):
            service.export_key_as_pkcs12("test-rsa", b"secret")
        with pytest.raises(NativeOperationError, match="backup"):
            service.backup_keys("retired.zip", b"secret")
        with pytest.raises(NativeOperationError, match="restore"):
            service.restore_keys("retired.zip", b"secret")

    with pytest.raises(HSMOperationError, match="disabled"):
        MockHSMService().initialize({})
