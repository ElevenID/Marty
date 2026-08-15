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
utils_package = types.ModuleType("marty_common.utils")
utils_package.__path__ = [str(PACKAGE_ROOT / "utils")]
sys.modules.setdefault("marty_common", common_package)
sys.modules.setdefault("marty_common.crypto", crypto_package)
sys.modules.setdefault("marty_common.rfid", rfid_package)
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
from marty_common.rfid.secure_messaging import SecureMessaging  # noqa: E402


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
