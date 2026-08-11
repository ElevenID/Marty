from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_native_wheel_downloads_are_versioned_and_digest_verified() -> None:
    script = (ROOT / "scripts" / "download-native-wheels.sh").read_text(
        encoding="utf-8"
    )

    assert "MARTY_CORE_NATIVE_TAG:-v0.1.46" in script
    assert "MARTY_CREDENTIALS_NATIVE_TAG" not in script
    assert "marty_iso18013" in script
    assert "marty_verification_py" in script
    assert "marty_rs" in script
    assert script.count('download_and_verify ElevenID/marty-core "$core_tag"') == 3
    assert "ElevenID/marty-credentials" not in script
    assert "actual" in script and "expected" in script
    assert "sha256:" in script

    package_metadata = (
        ROOT / "packages" / "marty-common" / "pyproject.toml"
    ).read_text(encoding="utf-8")
    assert '"marty-rs==0.1.46"' in package_metadata
    assert '"marty-verification-py==0.1.46"' in package_metadata


def test_release_image_embeds_and_validates_native_wheels() -> None:
    dockerfile = (ROOT / "docker" / "mmf-plugin.Dockerfile").read_text(encoding="utf-8")
    release_workflow = (ROOT / ".github" / "workflows" / "cd.yml").read_text(
        encoding="utf-8"
    )

    assert "COPY native-wheels /native-wheels" in dockerfile
    assert "COPY packages/marty-common ./packages/marty-common" in dockerfile
    assert "./packages/marty-common" in dockerfile
    assert "libdbus-1-3 libpcsclite1" in dockerfile
    assert "--find-links=/native-wheels" in dockerfile
    assert "require_native_backends()" in dockerfile
    assert "download-native-wheels.sh all" in release_workflow

    metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"marty-common==0.2.8"' in metadata
    assert 'marty-common = { path = "packages/marty-common" }' in metadata


def test_ci_builds_all_native_wheels_from_an_immutable_core_revision() -> None:
    build_script = (ROOT / "scripts" / "build-native-wheels.sh").read_text(
        encoding="utf-8"
    )
    workflows = "\n".join(
        (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        for name in ("ci.yml", "license-compliance.yml")
    )

    for package in ("marty-bindings", "marty-verification", "marty-iso18013"):
        assert f'{package}/Cargo.toml"' in build_script
    for distribution in ("marty_rs", "marty_verification_py", "marty_iso18013"):
        assert f"require_one_wheel {distribution}" in build_script

    assert "MARTY_CORE_REVISION: c8a028e803e7278f7842f5085855ac12a80b14ba" in workflows
    assert "repository: ElevenID/marty-core" in workflows
    assert "ref: ${{ env.MARTY_CORE_REVISION }}" in workflows
    assert "bash scripts/build-native-wheels.sh" in workflows


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


def test_pkd_offline_verifier_does_not_log_certificate_record_values() -> None:
    source = (
        ROOT / "src/marty_plugin/pkd_service/app/services/offline_verifier.py"
    ).read_text(encoding="utf-8")

    assert (
        'logger.warning("Skipping invalid CSCA %s: %s", item.get("id"), exc)'
        not in source
    )


def test_document_and_dtc_compatibility_paths_cannot_report_synthetic_success() -> None:
    service_clients = (
        ROOT / "src/marty_plugin/document_processing/app/services/service_clients.py"
    ).read_text(encoding="utf-8")
    dtc_service = (
        ROOT / "src/marty_plugin/dtc_engine/src/dtc_engine_service.py"
    ).read_text(encoding="utf-8")
    cmc_lds = (
        ROOT / "packages/marty-common/marty_common/lds/cmc_lds_impl.py"
    ).read_text(encoding="utf-8")

    assert '"valid": True, "checksums_valid": True' not in service_clients
    assert '"signature_valid": True, "trusted": True' not in service_clients
    assert "mock backend is disabled" in service_clients
    assert "signer_id as a public key placeholder" not in dtc_service
    assert "Rust DTC verification failed; falling back" not in dtc_service
    assert "falling back to document signer" not in dtc_service
    assert "dtc_prepare_signing" in dtc_service
    assert "dtc_assemble_signature" in dtc_service
    assert "document_content=signing_input" in dtc_service
    assert "mock_signature" not in cmc_lds
    assert "requires a native or remote document-signer adapter" in cmc_lds


def test_legacy_emrtd_and_vds_paths_fail_closed() -> None:
    passport = (
        ROOT / "packages/marty-common/marty_common/models/passport.py"
    ).read_text()
    cmc = (
        ROOT / "packages/marty-common/marty_common/verification/cmc_verification.py"
    ).read_text()
    vds_service = (
        ROOT / "packages/marty-common/marty_common/vds_nc/cmc_vds_nc_service.py"
    ).read_text()
    vds_impl = ROOT / "packages/marty-common/marty_common/vds_nc/vds_nc_impl.py"
    vds_adapters = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "src/marty_plugin/shared/vds_nc/processor.py",
            ROOT / "src/marty_plugin/shared/vds_nc/canonicalization.py",
            ROOT / "src/marty_plugin/shared/vds_nc/barcode.py",
            ROOT / "src/marty_plugin/shared/utils/vds_nc.py",
        )
    )

    assert "simulate successful authentication" not in passport
    assert "Create a basic DG1 from MRZ" not in passport
    assert "falling back to basic validation" not in passport
    assert "assume not revoked if status is ACTIVE" not in cmc
    assert "SOD signature structure is valid" not in cmc
    assert "All data group hashes are valid" not in cmc
    assert "initialized with test keys" not in vds_service
    assert not vds_impl.exists()
    for prohibited in (
        "import cbor2",
        "ecdsa_p256_sign",
        "rsa_pss_sha256_sign",
        "SIZE_THRESHOLDS",
        "CANONICAL_FIELDS",
        '.split("~")',
    ):
        assert prohibited not in vds_adapters


def test_shared_verification_kernels_do_not_import_python_cryptography() -> None:
    native_only_paths = (
        "crypto/certificate_validator.py",
        "crypto/csca_trust_store.py",
        "crypto/data_group_hasher.py",
        "crypto/evidence_signing.py",
        "crypto/sod_parser.py",
        "crypto/sod_signer.py",
        "crypto/vds_nc_keys.py",
        "security/passport_crypto_validator.py",
        "services/certificate_validation.py",
        "utils/asn1_utils.py",
        "utils/mrz_utils.py",
        "vc/sd_jwt_verifier.py",
        "verification/authenticity_verification.py",
        "verification/cmc_verification.py",
        "verification/trust_list_manager.py",
    )
    common = ROOT / "packages/marty-common/marty_common"
    sources = "\n".join(
        (common / relative).read_text(encoding="utf-8")
        for relative in native_only_paths
    )
    vds_processor = (ROOT / "src/marty_plugin/shared/vds_nc/processor.py").read_text(
        encoding="utf-8"
    )
    key_management = (
        ROOT / "src/marty_plugin/shared/services/key_management_service.py"
    ).read_text(encoding="utf-8")
    legacy_vds = (ROOT / "src/marty_plugin/shared/utils/vds_nc.py").read_text(
        encoding="utf-8"
    )
    visa_verification = (
        ROOT / "src/marty_plugin/shared/services/visa_verification.py"
    ).read_text(encoding="utf-8")
    mrz_hardened = (common / "utils/mrz_hardened.py").read_text(encoding="utf-8")
    mrz_enhanced = (common / "utils/mrz_enhanced.py").read_text(encoding="utf-8")
    trust_verification = (common / "verification/trust_verification.py").read_text(
        encoding="utf-8"
    )
    hsm = (common / "security/hsm.py").read_text(encoding="utf-8")

    assert "from cryptography" not in sources
    assert "import cryptography" not in sources
    assert "from cryptography" not in vds_processor
    assert "sign_profile" in vds_processor
    assert "load_private_key_pem" not in vds_processor
    assert "from cryptography" not in key_management
    assert "import cryptography" not in key_management
    assert "_generate_ec_key_python" not in key_management
    assert "PKCS#12 serialization is not exposed" in key_management
    assert "from cryptography" not in legacy_vds
    assert "verify_profile" in legacy_vds
    assert "load_public_key_pem" not in legacy_vds
    assert '"signature_valid": True' not in visa_verification
    assert "MRZParser._parse" in mrz_hardened
    assert "def _parse_td" not in mrz_hardened
    assert "NativeMRZParser._parse" in mrz_enhanced
    assert "Mock Certificate" not in trust_verification
    assert "simulated" not in trust_verification
    assert "NativeChainValidator" in trust_verification
    assert "verify_sod_signature" in trust_verification
    assert "MOCK_PUBLIC_KEY_DER_DATA" not in hsm
    assert "MOCK_SIGNATURE_DATA" not in hsm
    assert "The mock HSM provider is disabled" in hsm

    common_crypto = (common / "crypto/__init__.py").read_text(encoding="utf-8")
    assert "secrets.token_bytes" not in common_crypto
    assert "generate_secure_random_bytes(16)" in common_crypto


def test_duplicate_python_dtc_verifier_has_been_deleted() -> None:
    duplicate = ROOT / "packages/marty-common/marty_common/crypto/dtc_verifier.py"
    assert not duplicate.exists()
