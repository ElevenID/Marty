import asyncio
import ast
from pathlib import Path

from marty_plugin.shared.models.td2 import ChipData
from marty_plugin.shared.services.td2_verification import TD2VerificationEngine


ROOT = Path(__file__).resolve().parents[2]


def test_td2_chip_verification_has_no_python_hash_kernel() -> None:
    path = ROOT / "src/marty_plugin/shared/services/td2_verification.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )

    assert "hashlib" not in imported_modules
    assert "cryptography" not in imported_modules


def test_td2_sod_verification_requires_csca_store() -> None:
    engine = TD2VerificationEngine()
    result = asyncio.run(
        engine._verify_sod(ChipData(sod_signature=b"sod", dg1_mrz="mrz"))
    )

    assert result["valid"] is False
    assert result["error_codes"] == ["EMRTD_TRUST_STORE_UNAVAILABLE"]


def test_td2_sod_verification_routes_complete_result_through_rust(
    monkeypatch, tmp_path
) -> None:
    calls: dict[str, object] = {}

    class Registry:
        @classmethod
        def from_directory(cls, path: str):
            calls["trust_store"] = path
            return cls()

    class Native:
        CscaRegistry = Registry

        @staticmethod
        def verify_emrtd(sod: bytes, data_groups: dict[int, bytes], registry):
            calls["verify_emrtd"] = (sod, data_groups, registry)
            return {
                "verified": True,
                "errors": [],
                "error_codes": [],
                "warnings": ["DSC revocation was not checked"],
                "trust_anchor_subject": "C=TST,CN=CSCA",
                "certificate_chain": ["C=TST,CN=DSC", "C=TST,CN=CSCA"],
                "dsc_chain_status": "valid",
                "sod_signature_status": "valid",
                "dg_hash_status": "valid",
                "revocation_status": "unchecked",
            }

        @staticmethod
        def verify_sod_data_group_hash(sod: bytes, number: int, content: bytes):
            calls.setdefault("hashes", []).append((sod, number, content))
            return True

    from marty_plugin import native_backends

    monkeypatch.setattr(native_backends, "require_backend", lambda _name: Native())
    engine = TD2VerificationEngine(trust_store_path=str(tmp_path))
    result = asyncio.run(
        engine._verify_sod(
            ChipData(
                sod_signature=b"sod",
                dg1_mrz="mrz",
                dg2_portrait=b"portrait",
            )
        )
    )

    assert result["valid"] is True
    assert result["dg_hash_results"] == {"DG1": True, "DG2": True}
    assert result["trust_anchor_subject"] == "C=TST,CN=CSCA"
    assert result["certificate_chain"] == ["C=TST,CN=DSC", "C=TST,CN=CSCA"]
    assert result["component_statuses"] == {
        "dsc_chain": "valid",
        "sod_signature": "valid",
        "data_group_hashes": "valid",
        "revocation": "unchecked",
    }
    assert calls["trust_store"] == str(tmp_path)
    assert calls["verify_emrtd"][0:2] == (
        b"sod",
        {1: b"mrz", 2: b"portrait"},
    )
    assert calls["hashes"] == [
        (b"sod", 1, b"mrz"),
        (b"sod", 2, b"portrait"),
    ]


def test_td2_sod_verification_preserves_native_failure_codes(
    monkeypatch, tmp_path
) -> None:
    class Registry:
        @classmethod
        def from_directory(cls, _path: str):
            return cls()

    class Native:
        CscaRegistry = Registry

        @staticmethod
        def verify_emrtd(_sod: bytes, _data_groups: dict[int, bytes], _registry):
            return {
                "verified": False,
                "errors": ["No trust anchor found"],
                "error_codes": ["EMRTD_CHAIN_INVALID"],
                "warnings": [],
                "trust_anchor_subject": None,
                "certificate_chain": [],
                "dsc_chain_status": "invalid",
                "sod_signature_status": "unknown",
                "dg_hash_status": "unknown",
                "revocation_status": "unchecked",
            }

        @staticmethod
        def verify_sod_data_group_hash(
            _sod: bytes, _number: int, _content: bytes
        ) -> bool:
            return True

    from marty_plugin import native_backends

    monkeypatch.setattr(native_backends, "require_backend", lambda _name: Native())
    result = asyncio.run(
        TD2VerificationEngine(str(tmp_path))._verify_sod(
            ChipData(sod_signature=b"sod", dg1_mrz="mrz")
        )
    )

    assert result["valid"] is False
    assert result["error_codes"] == ["EMRTD_CHAIN_INVALID"]
    assert result["errors"] == ["No trust anchor found"]
