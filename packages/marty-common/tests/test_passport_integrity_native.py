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
sys.modules.setdefault("marty_common", common_package)
sys.modules.setdefault("marty_common.crypto", crypto_package)

from marty_common.crypto.hash_comparison import DataGroupHashResult, HashComparisonEngine  # noqa: E402
from marty_common.crypto.sod_parser import HashAlgorithm  # noqa: E402


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
