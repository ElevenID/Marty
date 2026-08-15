"""Behavioral parity tests for the native eMRTD data boundary."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from marty_common.crypto_bridge import Encoding, PublicFormat, RSAPublicKeyBridge
from marty_common.native_backends import NativeBackendUnavailable
from marty_common.rfid.biometric_templates import (
    BiometricTemplateProcessor,
    BiometricType,
    FacialImageTemplate,
    FingerprintTemplate,
    IrisTemplate,
)
from marty_common.rfid.elementary_files import DataGroup, ElementaryFileParser
from marty_common.security.dg15_parser import DG15Parser

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "emrtd_data_vectors.json"


@pytest.fixture(scope="module")
def vectors() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _bytes(value: str) -> bytes:
    return bytes.fromhex(value)


def _tlv(tag: bytes, value: bytes) -> bytes:
    length = bytes([len(value)]) if len(value) < 128 else b"\x81" + bytes([len(value)])
    return tag + length + value


def test_elementary_file_behavior_matches_shared_vectors(vectors: dict) -> None:
    parser = ElementaryFileParser()
    ef_com = vectors["ef_com"]
    parsed_com = parser.parse_ef_com(_bytes(ef_com["hex"]))
    assert parsed_com["lds_version"] == ef_com["lds_version"]
    assert parsed_com["unicode_version"] == ef_com["unicode_version"]
    assert parsed_com["data_groups"] == ef_com["data_groups"]

    for vector in vectors["dg1"]:
        encoded = _tlv(b"\x61", _tlv(b"\x5f\x1f", vector["mrz"].encode("ascii")))
        assert asdict(parser.parse_ef_dg1(encoded)) == vector["expected"]

    dg2 = vectors["dg2"]
    parsed_dg2 = parser.parse_ef_dg2(_bytes(dg2["hex"]))
    assert parsed_dg2.biometric_type == dg2["expected"]["biometric_type"]
    assert parsed_dg2.biometric_subtype == dg2["expected"]["biometric_subtype"]
    assert parsed_dg2.format_owner == dg2["expected"]["format_owner"]
    assert parsed_dg2.format_type == dg2["expected"]["format_type"]
    assert parsed_dg2.data.hex().upper() == dg2["expected"]["data_hex"]

    generic = parser.parse_elementary_file(DataGroup.DG2.value, _bytes(dg2["hex"]))
    assert generic.file_id == DataGroup.DG2.value
    assert generic.parsed_content is not None
    assert generic.parsed_content["data"] == parsed_dg2.data


def test_biometric_behavior_matches_shared_vectors(vectors: dict) -> None:
    processor = BiometricTemplateProcessor()
    type_map = {
        "facial_image": BiometricType.FACIAL_IMAGE,
        "fingerprint": BiometricType.FINGERPRINT,
        "iris": BiometricType.IRIS,
    }
    class_map = {
        "facial_image": FacialImageTemplate,
        "fingerprint": FingerprintTemplate,
        "iris": IrisTemplate,
    }

    for vector in vectors["biometric_templates"]:
        parsed = processor.parse_biometric_template(_bytes(vector["hex"]), type_map[vector["type"]])
        expected = vector["expected"]
        assert isinstance(parsed, class_map[vector["type"]])
        assert parsed.image_width == expected["width"]
        assert parsed.image_height == expected["height"]
        assert parsed.image_data is not None
        assert parsed.image_data.hex().upper() == expected["image_hex"]

        report = processor.validate_template_quality(parsed)
        assert report["overall_quality"] == pytest.approx(expected["overall_quality"])
        assert len(report["issues"]) == expected["issue_count"]


def test_dg15_behavior_and_public_key_contract_match_shared_vector(vectors: dict) -> None:
    vector = vectors["dg15"]
    parser = DG15Parser()
    parsed = parser.parse_dg15(_bytes(vector["hex"]))

    assert parsed.algorithm_oid == vector["algorithm_oid"]
    assert parsed.key_size == vector["key_size"]
    assert parsed.public_exponent == vector["public_exponent"]
    assert parsed.modulus == int(vector["modulus"])
    assert parser.validate_chip_key(parsed)
    assert parser.extract_key_fingerprint(parsed) == vector["fingerprint_sha256"]

    spki_der = parsed.public_key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    assert spki_der == bytes.fromhex(vector["hex"])[3:]
    assert parsed.public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).startswith(
        b"-----BEGIN PUBLIC KEY-----"
    )

    reconstructed = RSAPublicKeyBridge(parsed.modulus, parsed.public_exponent)
    assert reconstructed.key_size == parsed.key_size
    assert reconstructed.public_bytes(Encoding.DER) == spki_der


def test_malformed_inputs_fail_closed_with_normalized_codes(vectors: dict) -> None:
    ef_parser = ElementaryFileParser()
    biometric = BiometricTemplateProcessor()
    dg15 = DG15Parser()
    operations = {
        "tlv": lambda data: ef_parser.parse_tlv(data),
        "dg1": lambda data: ef_parser.parse_ef_dg1(data),
        "dg2": lambda data: ef_parser.parse_ef_dg2(data),
        "facial_image": lambda data: biometric.parse_facial_image_template(data),
        "dg15": lambda data: dg15.parse_dg15(data),
    }

    for vector in vectors["invalid"]:
        with pytest.raises(ValueError, match=f"^{vector['code']}"):
            operations[vector["operation"]](_bytes(vector["hex"]))


def test_missing_native_backend_never_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    from marty_common import emrtd_native

    def unavailable():
        raise NativeBackendUnavailable("required test backend missing")

    monkeypatch.setattr(emrtd_native, "_backend", unavailable)
    with pytest.raises(NativeBackendUnavailable, match="required test backend missing"):
        ElementaryFileParser().parse_tlv(b"\x61\x00")


def test_superseded_python_parser_kernels_are_absent() -> None:
    package_root = Path(__file__).parents[1] / "marty_common"
    sources = (
        package_root / "rfid" / "elementary_files.py",
        package_root / "rfid" / "biometric_templates.py",
        package_root / "security" / "dg15_parser.py",
    )
    forbidden = ("import struct", "pyasn1", "der_decoder", "hashlib")
    offenders = {
        path.name: token for path in sources for token in forbidden if token in path.read_text(encoding="utf-8")
    }
    assert not offenders
