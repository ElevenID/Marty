from __future__ import annotations

# ruff: noqa: E402, I001 -- namespace stubs must precede focused imports.

import json
import sys
import types
from pathlib import Path

import pytest

# Keep this focused native-boundary test independent of marty-common's web,
# database, and policy dependencies. Normal imports still use the real package.
PACKAGE_ROOT = Path(__file__).parents[1] / "marty_common"
common_package = types.ModuleType("marty_common")
common_package.__path__ = [str(PACKAGE_ROOT)]
crypto_package = types.ModuleType("marty_common.crypto")
crypto_package.__path__ = [str(PACKAGE_ROOT / "crypto")]
rfid_package = types.ModuleType("marty_common.rfid")
rfid_package.__path__ = [str(PACKAGE_ROOT / "rfid")]
security_package = types.ModuleType("marty_common.security")
security_package.__path__ = [str(PACKAGE_ROOT / "security")]
utils_package = types.ModuleType("marty_common.utils")
utils_package.__path__ = [str(PACKAGE_ROOT / "utils")]
sys.modules.setdefault("marty_common", common_package)
sys.modules.setdefault("marty_common.crypto", crypto_package)
sys.modules.setdefault("marty_common.rfid", rfid_package)
sys.modules.setdefault("marty_common.security", security_package)
sys.modules.setdefault("marty_common.utils", utils_package)
crypto_bridge = types.ModuleType("marty_common.crypto_bridge")


def _unused_crypto(*_args, **_kwargs):
    raise AssertionError("PACE crypto is outside this focused BAC test")


crypto_bridge.tdes_cbc_decrypt = _unused_crypto
crypto_bridge.p256_generate = _unused_crypto
crypto_bridge.p256_agree = _unused_crypto
sys.modules.setdefault("marty_common.crypto_bridge", crypto_bridge)

from marty_common.crypto.hash_comparison import DataGroupHashResult, HashComparisonEngine  # noqa: E402
from marty_common.crypto.sod_parser import HashAlgorithm  # noqa: E402
from marty_common.native_backends import NativeBackendUnavailable  # noqa: E402
from marty_common.rfid.secure_messaging import SecureMessaging  # noqa: E402
from marty_common.security.active_authentication import (  # noqa: E402
    ActiveAuthenticationChallenge,
    ActiveAuthenticationProtocol,
)
from marty_common.security.eac_protocol import (  # noqa: E402
    ChipAuthenticationError,
    EACChipAuthentication,
    EACCryptoAlgorithm,
    EACError,
    EACSecureMessaging,
    EACTerminalAuthentication,
    MockEACCertificate,
)
from marty_common.security.iso9796_verifier import (  # noqa: E402
    ISO9796Scheme,
    ISO9796Verifier,
    PassportActiveAuthenticationVerifier,
)


FIXTURE = Path(__file__).parents[3] / "tests" / "fixtures" / "passport_integrity_behavior.json"


@pytest.mark.parametrize("case", json.loads(FIXTURE.read_text())["cases"], ids=lambda case: case["name"])
def test_shared_passport_integrity_behavior(case: dict) -> None:
    request = case["request"]
    expected = case["expected"]
    report = HashComparisonEngine().compare_hashes(
        computed_hashes=[
            DataGroupHashResult(
                data_group=item["data_group"],
                hash_value=bytes.fromhex(item["hash"]),
                algorithm=HashAlgorithm(item["algorithm"]),
                success=item.get("success", True),
                error_message=item.get("error_message"),
            )
            for item in request["computed_hashes"]
        ],
        expected_hashes={
            int(data_group): bytes.fromhex(value)
            for data_group, value in request["expected_hashes"].items()
        },
        algorithm=HashAlgorithm(request["algorithm"]),
    )

    assert report.is_passport_valid is expected["is_passport_valid"]
    assert report.successful_verifications == expected["successful_verifications"]
    assert report.failed_verifications == expected["failed_verifications"]
    assert report.critical_errors == expected["critical_errors"]
    assert report.warnings == expected["warnings"]
    assert report.overall_status == expected["overall_status"]
    assert [entry.result.value for entry in report.comparison_entries] == expected["results"]

    analysis = HashComparisonEngine().generate_detailed_mismatch_report(report)
    implications = analysis.get("security_implications")
    risk_level = implications["risk_level"] if implications else None
    assert risk_level == expected["risk_level"]


def test_duplicate_computed_hashes_fail_closed() -> None:
    duplicate = DataGroupHashResult(1, bytes(32), HashAlgorithm.SHA256)
    with pytest.raises(ValueError, match="duplicate computed hash"):
        HashComparisonEngine().compare_hashes(
            [duplicate, duplicate],
            {1: bytes(32)},
            HashAlgorithm.SHA256,
        )


def test_shared_icao_bac_behavior() -> None:
    vector = json.loads(
        (Path(__file__).parents[3] / "tests" / "fixtures" / "passport_chip_behavior.json").read_text()
    )["bac_annex_d"]
    secure_messaging = SecureMessaging()
    keys = secure_messaging.derive_bac_keys(
        vector["passport_number"],
        vector["date_of_birth"],
        vector["date_of_expiry"],
    )
    assert keys.k_seed.hex().upper() == vector["base_seed"]
    assert keys.k_enc.hex().upper() == vector["base_encryption_key"]
    assert keys.k_mac.hex().upper() == vector["base_mac_key"]

    command = secure_messaging._native_bac.start_bac_with_random(
        vector["passport_number"],
        vector["date_of_birth"],
        vector["date_of_expiry"],
        bytes.fromhex(vector["chip_challenge"]),
        bytes.fromhex(vector["reader_challenge"]),
        bytes.fromhex(vector["reader_key"]),
    )
    assert command.hex().upper() == vector["authentication_command_data"]
    session = secure_messaging.complete_basic_access_control(
        keys, bytes.fromhex(vector["authentication_response_data"])
    )
    assert session.k_s_enc.hex().upper() == vector["session_encryption_key"]
    assert session.k_s_mac.hex().upper() == vector["session_mac_key"]
    assert session.ssc.to_bytes(8, "big").hex().upper() == vector["initial_ssc"]
    assert (
        secure_messaging.encrypt_command(bytes.fromhex(vector["plain_select_ef_com"]))
        .hex()
        .upper()
        == vector["protected_select_ef_com"]
    )


def test_bac_response_mac_failure_is_rejected() -> None:
    vector = json.loads(
        (Path(__file__).parents[3] / "tests" / "fixtures" / "passport_chip_behavior.json").read_text()
    )["bac_annex_d"]
    secure_messaging = SecureMessaging()
    keys = secure_messaging.derive_bac_keys(
        vector["passport_number"], vector["date_of_birth"], vector["date_of_expiry"]
    )
    secure_messaging._native_bac.start_bac_with_random(
        vector["passport_number"],
        vector["date_of_birth"],
        vector["date_of_expiry"],
        bytes.fromhex(vector["chip_challenge"]),
        bytes.fromhex(vector["reader_challenge"]),
        bytes.fromhex(vector["reader_key"]),
    )
    response = bytearray.fromhex(vector["authentication_response_data"])
    response[-1] ^= 1
    with pytest.raises(ValueError, match="MAC verification failed"):
        secure_messaging.complete_basic_access_control(keys, bytes(response))


def test_shared_active_authentication_apdu_behavior() -> None:
    vector = json.loads(
        (Path(__file__).parents[3] / "tests" / "fixtures" / "passport_chip_behavior.json").read_text()
    )["active_authentication"]
    protocol = ActiveAuthenticationProtocol()
    challenge = ActiveAuthenticationChallenge(
        bytes.fromhex(vector["challenge_hex"]), "SHA-256", 128
    )
    assert protocol.create_aa_apdu_command(challenge).hex().upper() == vector[
        "expected_command_apdu"
    ]
    response = protocol.parse_aa_response(bytes.fromhex(vector["successful_response"]), challenge)
    assert response.signature.hex().upper() == vector["expected_signature"]
    for raw_response in vector["error_responses"]:
        with pytest.raises((RuntimeError, ValueError)):
            protocol.parse_aa_response(bytes.fromhex(raw_response), challenge)
    for key_size in vector["invalid_challenge_sizes_bits"]:
        with pytest.raises((RuntimeError, ValueError)):
            protocol.generate_challenge(key_size)


def test_native_active_authentication_round_trip_and_exact_challenge() -> None:
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    public_key = private_key.public_key()
    challenge = ActiveAuthenticationChallenge(b"0123456789abcdef", "SHA-256", 128)
    protocol = ActiveAuthenticationProtocol()
    raw_response = protocol.create_mock_aa_response(challenge, private_key)
    response = protocol.parse_aa_response(raw_response, challenge)
    assert protocol.verify_active_authentication(response, challenge, public_key)
    assert response.recovered_message == challenge.challenge

    wrong_challenge = ActiveAuthenticationChallenge(b"1123456789abcdef", "SHA-256", 128)
    assert not protocol.verify_active_authentication(response, wrong_challenge, public_key)

    verifier = ISO9796Verifier()
    signature = verifier.create_test_signature(challenge.challenge, private_key)
    result = verifier.verify_signature(
        signature, challenge.challenge, public_key, ISO9796Scheme.SCHEME_1
    )
    assert result.is_valid
    assert result.recovered_message == challenge.challenge
    assert PassportActiveAuthenticationVerifier().verify_active_authentication_response(
        challenge.challenge, signature, public_key
    )


def test_active_authentication_missing_native_capability_fails_closed(monkeypatch) -> None:
    import marty_verification

    monkeypatch.delattr(marty_verification, "active_authentication_build_apdu")
    challenge = ActiveAuthenticationChallenge(b"0123456789abcdef", "SHA-256", 128)
    with pytest.raises(NativeBackendUnavailable, match="active_authentication_build_apdu"):
        ActiveAuthenticationProtocol().create_aa_apdu_command(challenge)


def test_shared_eac_secure_messaging_behavior() -> None:
    vector = json.loads(
        (Path(__file__).parents[3] / "tests" / "fixtures" / "eac_behavior.json").read_text()
    )["secure_messaging"]
    messaging = EACSecureMessaging(
        bytes.fromhex(vector["shared_secret"]),
        EACCryptoAlgorithm(vector["algorithm"]),
    )
    assert messaging.secure_channel.mac_key.hex().upper() == vector["mac_key"]
    assert messaging.secure_channel.encryption_key.hex().upper() == vector["encryption_key"]
    protected = bytes(
        messaging._native.encrypt_apdu_with_iv(
            bytes.fromhex(vector["plaintext"]), bytes.fromhex(vector["iv"])
        )
    )
    assert protected.hex().upper() == vector["protected"]
    assert messaging.decrypt_apdu(protected).hex().upper() == vector["plaintext"]

    tampered = bytearray(protected)
    tampered[0] ^= 1
    with pytest.raises(EACError, match="MAC verification failed"):
        messaging.decrypt_apdu(bytes(tampered))


def test_native_eac_key_agreement_and_unsupported_algorithms() -> None:
    placeholder = object()
    left = EACChipAuthentication(placeholder)
    right = EACChipAuthentication(placeholder)
    left_public, _ = left.generate_ephemeral_keypair()
    right_public, _ = right.generate_ephemeral_keypair()
    assert left.perform_chip_authentication(right_public) == right.perform_chip_authentication(
        left_public
    )

    fixture = json.loads(
        (Path(__file__).parents[3] / "tests" / "fixtures" / "eac_behavior.json").read_text()
    )
    for algorithm in fixture["unsupported_algorithms"]:
        with pytest.raises(ChipAuthenticationError):
            EACChipAuthentication(
                placeholder, EACCryptoAlgorithm(algorithm)
            ).generate_ephemeral_keypair()


def test_native_eac_terminal_signature_and_missing_backend_failure(monkeypatch) -> None:
    import marty_verification
    from cryptography.hazmat.primitives import serialization

    certificate, private_key = MockEACCertificate.create_mock_terminal_certificate()
    terminal = EACTerminalAuthentication(certificate, private_key)
    terminal.set_certificate_chain([certificate])
    challenge = b"chip-terminal-authentication-challenge"
    signature = terminal.perform_terminal_authentication(challenge)
    assert marty_verification.eac_verify_certificate_signature(
        certificate.algorithm.value,
        certificate.public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ),
        challenge,
        signature,
    )

    monkeypatch.delattr(marty_verification, "NativeEacSecureMessaging")
    with pytest.raises(NativeBackendUnavailable, match="NativeEacSecureMessaging"):
        EACSecureMessaging(b"shared", EACCryptoAlgorithm.ECDH_P256_SHA256)
