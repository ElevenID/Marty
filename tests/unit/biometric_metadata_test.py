"""Optional biometric helpers must never invent extracted evidence."""

import importlib.util
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture
def biometric(monkeypatch):
    path = (
        Path(__file__).resolve().parents[2]
        / "packages/marty-common/marty_common/security/enhanced_biometric_processing.py"
    )
    spec = importlib.util.spec_from_file_location("biometric_metadata_subject", path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("declared_count", [0, 30, 100])
def test_wsq_extraction_fails_without_a_real_decoder(biometric, declared_count):
    header = biometric.BiometricHeader(
        format_owner=1,
        format_type=1,
        biometric_type=biometric.BiometricType.FINGER,
        biometric_subtype=1,
        creation_date=datetime.now(timezone.utc),
    )
    template = biometric.FingerprintTemplate(
        header=header,
        template_data=b"\xff\xa0synthetic-undecoded-WSQ",
        format=biometric.FingerprintFormat.WSQ,
        image_width=256,
        image_height=360,
        resolution=500,
        minutiae_count=declared_count,
    )
    with pytest.raises(biometric.BiometricTemplateError, match="WSQ.*not available"):
        template.extract_minutiae()
    assert template.minutiae_points == []
    assert template.quality_score is None
    assert template.minutiae_count == 0

    # A reused object must not retain metadata from an earlier extraction.
    template.minutiae_points = [{"id": 1, "x": 17, "y": 29}]
    template.quality_score = biometric.BiometricQualityScore(
        overall_score=90,
        quality_level=biometric.BiometricQualityLevel.EXCELLENT,
        assessment_algorithm="synthetic-test",
    )
    with pytest.raises(biometric.BiometricTemplateError, match="WSQ.*not available"):
        template.extract_minutiae()
    assert template.minutiae_points == []
    assert template.quality_score is None


def test_wsq_processing_does_not_cache_an_unqualified_template(biometric):
    processor = biometric.PassportBiometricProcessor()
    header = struct.pack(">HHH", 1, 1, 1) + bytes(14)
    payload = b"\xff\xa0synthetic-undecoded-WSQ"
    with pytest.raises(biometric.BiometricTemplateError, match="WSQ.*not available"):
        processor.process_dg3_fingerprint(header + struct.pack(">I", len(payload)) + payload)
    assert processor.processed_templates == {}


def test_iris_metadata_leaves_unknown_device_identity_explicit(biometric):
    payload = bytes(8) + struct.pack(">H", 217) + bytes(2) + struct.pack(">f", 1.5)
    processor = biometric.PassportBiometricProcessor()
    assert processor._extract_iris_metadata(payload) == (217, "UNKNOWN", 1.5)
    assert processor._extract_iris_metadata(payload) == (217, "UNKNOWN", 1.5)


def test_existing_minutiae_parser_still_reads_input_records(biometric):
    header = biometric.BiometricHeader(
        format_owner=1,
        format_type=1,
        biometric_type=biometric.BiometricType.FINGER,
        biometric_subtype=1,
        creation_date=datetime.now(timezone.utc),
    )
    data = bytes(28) + struct.pack(">H", 1) + struct.pack(">HHH", 17, 29, 0x124F)
    template = biometric.FingerprintTemplate(
        header=header,
        template_data=data,
        format=biometric.FingerprintFormat.ISO_FINGER_MINUTIAE,
        image_width=256,
        image_height=360,
        resolution=500,
        minutiae_count=1,
    )
    assert template.extract_minutiae() == [{
        "id": 1, "x": 17, "y": 29, "angle": 18,
        "type": "ridge_ending", "quality": 23,
    }]
