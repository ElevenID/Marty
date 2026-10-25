"""Conformance and fail-closed tests for the Rust-owned VDS-NC adapter."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from marty_common.native_backends import NativeBackendUnavailable, NativeOperationError
from marty_plugin.shared.models.visa import (
    Gender,
    PersonalData,
    PolicyConstraints,
    SecurityModel,
    Visa,
    VisaCategory,
    VisaDocumentData,
    VisaType,
)
from marty_plugin.shared.utils.vds_nc import VDSNCDecoder, VDSNCEncoder, VDSNCValidator
from marty_plugin.shared.vds_nc import (
    BarcodeFormat,
    DocumentType,
    ErrorCorrectionLevel,
    SignatureAlgorithm,
    VDSNCBarcodeSelector,
    VDSNCProcessor,
)
from marty_plugin.shared.vds_nc import native as native_adapter


def _profile(name: str):
    return json.loads(
        (Path(__file__).parents[2] / "fixtures/vds_nc_public_profiles.json").read_text(
            encoding="utf-8"
        )
    )[name]


def _cmc_claims() -> dict[str, object]:
    return {
        "docType": "CMC",
        "issuingCountry": "AUS",
        "documentNumber": "X123456",
        "surname": "EXAMPLE",
        "givenNames": "ADA",
        "dateOfBirth": "19900102",
        "nationality": "AUS",
        "gender": "F",
        "dateOfIssue": "20260101",
        "dateOfExpiry": "20300101",
    }


def _visa() -> Visa:
    return Visa(
        personal_data=PersonalData(
            surname="EXAMPLE",
            given_names="ADA",
            nationality="AUS",
            date_of_birth=date(1990, 1, 2),
            gender=Gender.FEMALE,
        ),
        document_data=VisaDocumentData(
            document_number="V123456",
            issuing_state="AUS",
            visa_category=VisaCategory.B2,
            visa_type=VisaType.E_VISA,
            date_of_issue=date(2026, 1, 1),
            date_of_expiry=date(2030, 1, 1),
            place_of_issue="CANBERRA",
        ),
        security_model=SecurityModel.VDS_NC,
        policy_constraints=PolicyConstraints(allowed_countries=["AUS", "NZL"]),
    )


@pytest.mark.unit
@pytest.mark.security
@pytest.mark.parametrize("profile_name", ["cmc_es256", "cmc_ps256"])
def test_processor_verifies_public_signed_vector_and_component_policy(profile_name):

    fixture = _profile(profile_name)
    public_pem = fixture["public_key_pem"]
    algorithm = SignatureAlgorithm(fixture["algorithm"])
    barcode_data = fixture["barcode_data"]
    result = VDSNCProcessor(public_keys={"TESTSGN": public_pem}).verify_vds_nc_document(
        barcode_data,
        {"surname": "example"},
    )

    assert result.is_valid
    assert result.signature_valid
    assert result.canonicalization_ok
    assert result.field_consistency_valid
    assert result.temporal_validity_ok
    assert result.verification_details == {
        "native_backend": "_marty_rs",
        "algorithm": algorithm.value,
    }
    document = result.document
    assert document.verify_signature(public_pem)
    assert document.validate_field_consistency({"surname": "changed"}) == [
        "VDS_NC.FIELD_MISMATCH: surname"
    ]


@pytest.mark.unit
@pytest.mark.security
def test_malformed_and_missing_key_inputs_fail_closed() -> None:
    malformed = VDSNCProcessor().verify_vds_nc_document("not-a-vds-nc-envelope")
    assert not malformed.is_valid
    assert malformed.errors

    result = VDSNCProcessor().verify_vds_nc_document(
        _profile("cmc_es256")["barcode_data"]
    )
    assert not result.is_valid
    assert not result.signature_valid
    assert any("Public key not found" in error for error in result.errors)


@pytest.mark.unit
@pytest.mark.security
def test_missing_native_backend_never_invokes_a_python_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(_module_name: str) -> None:
        raise NativeBackendUnavailable("test backend unavailable")

    monkeypatch.setattr(native_adapter, "require_backend", unavailable)
    with pytest.raises(NativeBackendUnavailable, match="test backend unavailable"):
        native_adapter.canonicalize_profile("CMC", _cmc_claims())


@pytest.mark.unit
@pytest.mark.security
def test_visa_compatibility_view_retains_signed_policy_constraints() -> None:
    fixture = _profile("visa_es256")
    visa = _visa()
    decoded, signature_valid = VDSNCDecoder.decode_vds_nc(
        fixture["barcode_data"], fixture["public_key_pem"]
    )

    assert signature_valid
    assert decoded["message"]["pol"]["allowed_countries"] == ["AUS", "NZL"]
    assert VDSNCValidator.validate_header(decoded["header"]) == []
    assert VDSNCValidator.validate_visa_message(decoded["message"]) == []
    assert VDSNCValidator.validate_field_consistency(decoded, visa) == []


@pytest.mark.unit
@pytest.mark.security
def test_removed_low_level_python_protocol_paths_raise_typed_errors() -> None:
    with pytest.raises(NativeOperationError, match="CBOR encoding"):
        VDSNCEncoder.encode_cbor({}, {})
    with pytest.raises(NativeOperationError, match="detached verification"):
        VDSNCDecoder.verify_signature(b"input", b"signature", "public key")


@pytest.mark.unit
def test_explicit_barcode_correction_compatibility_is_rust_owned() -> None:
    assert (
        VDSNCBarcodeSelector.select_optimal_format(
            2_000,
            ErrorCorrectionLevel.LOW,
            BarcodeFormat.QR_CODE,
        )
        is BarcodeFormat.QR_CODE
    )
    assert (
        VDSNCBarcodeSelector.select_optimal_format(
            2_000,
            ErrorCorrectionLevel.HIGH,
            BarcodeFormat.QR_CODE,
        )
        is BarcodeFormat.DATA_MATRIX
    )


@pytest.mark.unit
def test_python_vds_nc_ownership_guard() -> None:
    repository = Path(__file__).resolve().parents[3]
    implementation_paths = [
        repository / "src/marty_plugin/shared/vds_nc",
        repository / "src/marty_plugin/shared/utils/vds_nc.py",
    ]
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for target in implementation_paths
        for path in ([target] if target.is_file() else target.glob("*.py"))
    )
    forbidden = [
        "import cbor2",
        "ecdsa_p256_sign",
        "rsa_pss_sha256_sign",
        "SIZE_THRESHOLDS",
        '.split("~")',
        "CANONICAL_FIELDS",
    ]
    assert not [token for token in forbidden if token in source]
    assert not (
        repository / "packages/marty-common/marty_common/vds_nc/vds_nc_impl.py"
    ).exists()
