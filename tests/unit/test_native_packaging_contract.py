from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_native_wheel_downloads_are_versioned_and_digest_verified() -> None:
    script = (ROOT / "scripts" / "download-native-wheels.sh").read_text(
        encoding="utf-8"
    )

    assert "MARTY_CORE_NATIVE_TAG:-v0.1.39" in script
    assert "MARTY_CREDENTIALS_NATIVE_TAG" not in script
    assert "marty_iso18013" in script
    assert "marty_verification_py" in script
    assert "marty_rs" in script
    assert script.count('download_and_verify ElevenID/marty-core "$core_tag"') == 3
    assert "ElevenID/marty-credentials" not in script
    assert "actual" in script and "expected" in script
    assert "sha256:" in script


def test_release_image_embeds_and_validates_native_wheels() -> None:
    dockerfile = (ROOT / "docker" / "mmf-plugin.Dockerfile").read_text(encoding="utf-8")
    release_workflow = (ROOT / ".github" / "workflows" / "cd.yml").read_text(
        encoding="utf-8"
    )

    assert "COPY native-wheels /native-wheels" in dockerfile
    assert "--find-links=/native-wheels" in dockerfile
    assert "require_native_backends()" in dockerfile
    assert "download-native-wheels.sh all" in release_workflow


def test_legacy_iso_modules_contain_no_python_protocol_or_transport_kernel() -> None:
    paths = [
        ROOT / "src/marty_plugin/iso18013/core.py",
        ROOT / "src/marty_plugin/iso18013/crypto.py",
        ROOT / "src/marty_plugin/iso18013/online.py",
        ROOT / "src/marty_plugin/iso18013/protocols.py",
        ROOT / "src/marty_plugin/iso18013/transport/__init__.py",
        ROOT / "src/marty_plugin/iso18013/transport/ble_real.py",
        ROOT / "src/marty_plugin/iso18013/transport/nfc_real.py",
        ROOT / "src/marty_plugin/iso18013/apps/holder.py",
        ROOT / "src/marty_plugin/iso18013/apps/reader.py",
    ]
    contents = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    for prohibited in (
        "import cbor2",
        "import hmac",
        "from cryptography",
        "from bleak",
        "from smartcard",
        "simulated BLE response",
        "simulated NFC response",
    ):
        assert prohibited not in contents


def test_trust_api_contains_no_synthetic_success_or_signature() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "src/marty_plugin/trust_svc/api.py",
            ROOT
            / "src/marty_plugin/pkd_service/app/services/masterlist_sync_service.py",
            ROOT / "src/marty_plugin/pkd_service/app/services/deviationlist_service.py",
        )
    )

    assert "MOCK_KMS_SIGNATURE" not in source
    assert "For now, return a mock response" not in source
    assert "encode_raw_certificates" not in source
    assert "Fallback to mock data" not in source
