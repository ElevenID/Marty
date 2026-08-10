"""Golden-vector checks for the Marty compatibility adapters."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from marty_common.crypto.certificate_validator import CertificateChainValidator
from marty_common.crypto.data_group_hasher import DataGroupHashComputer
from marty_common.crypto.sod_parser import SODProcessor
from marty_common.crypto.sod_signer import verify_sod_signature
from marty_common.native_backends import NativeOperationError
from marty_common.utils.mrz_utils import (
    MRZException,
    MRZParser,
    parse_td1_mrz,
    parse_td2_mrz,
    parse_td3_mrz,
)
from marty_common.utils.mrz_hardened import parse_mrz_simple, parse_mrz_with_validation
from marty_common.vds_nc.cmc_vds_nc_service import CMCVDSNCService
from marty_common.verification.trust_verification import (
    TrustValidationLevel,
    TrustValidator,
)


FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures/emrtd_verification_vectors.json"
)


def _fixture() -> tuple[bytes, bytes, bytes, dict[int, bytes]]:
    values = json.loads(FIXTURE.read_text(encoding="utf-8"))
    decode = lambda value: base64.b64decode(value, validate=True)  # noqa: E731
    return (
        decode(values["sod_der_base64"]),
        decode(values["dsc_der_base64"]),
        decode(values["csca_der_base64"]),
        {int(key): decode(value) for key, value in values["data_groups"].items()},
    )


def test_native_sod_and_data_group_adapters_match_golden_vector() -> None:
    sod, _dsc, _csca, data_groups = _fixture()
    processor = SODProcessor()
    parsed = processor.parse_sod_data(sod)

    assert processor.extract_hash_algorithm(parsed) == "sha256"
    assert processor.verify_data_group_integrity(parsed, data_groups) == (True, [])
    assert DataGroupHashComputer().verify_data_group_integrity_with_sod(
        sod, data_groups
    )[0]

    altered = dict(data_groups)
    altered[1] = bytes([altered[1][0] ^ 1]) + altered[1][1:]
    assert not processor.verify_data_group_integrity(parsed, altered)[0]


def test_native_sod_signature_requires_trust_and_chain_adapter_fails_closed() -> None:
    sod, dsc, csca, _data_groups = _fixture()

    assert verify_sod_signature(sod, [csca])
    assert not verify_sod_signature(sod, None)

    validator = CertificateChainValidator()
    assert not validator.validate_certificate_chain(dsc).is_valid
    validator.add_trust_anchor(csca)
    result = validator.validate_certificate_chain(dsc)
    assert result.is_valid
    assert result.signature_verified
    assert result.trust_anchor == csca


def test_legacy_vds_service_has_no_generated_key_or_unsigned_success() -> None:
    service = CMCVDSNCService()

    assert service.verify_barcode("DC03UTO~{}~unsigned") == (
        False,
        None,
        ["CMC VDS-NC verification requires an explicitly configured native verifier"],
    )
    with pytest.raises(NativeOperationError):
        service.get_certificate_reference()


@pytest.mark.asyncio
async def test_native_trust_compatibility_layer_validates_chain_and_sod() -> None:
    sod, dsc, csca, _data_groups = _fixture()

    class PKD:
        async def list_trust_anchors(self, country_code: str) -> list[bytes]:
            assert country_code == "TST"
            return [csca]

    document = {
        "issuing_authority": "TST",
        "chip_data": {"sod": sod, "dsc_certificate": dsc},
    }
    standard = await TrustValidator(PKD()).validate_trust(
        document, "P", TrustValidationLevel.STANDARD
    )
    assert standard and all(result.passed for result in standard)

    strict = await TrustValidator(PKD()).validate_trust(
        document, "P", TrustValidationLevel.STRICT
    )
    assert strict[-1].check_name == "certificate_revocation_check"
    assert strict[-1].passed is False


@pytest.mark.parametrize(
    ("parser", "lines", "expected_format"),
    (
        (
            parse_td1_mrz,
            (
                "I<UTOD231458907<<<<<<<<<<<<<<<",
                "7408122F1204159UTO<<<<<<<<<<<6",
                "ERIKSSON<<ANNA<MARIA<<<<<<<<<<",
            ),
            "TD1",
        ),
        (
            parse_td2_mrz,
            (
                "I<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<",
                "D231458907UTO7408122F1204159<<<<<<<6",
            ),
            "TD2",
        ),
        (
            parse_td3_mrz,
            (
                "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
                "L898902C36UTO7408122F1204159ZE184226B<<<<<10",
            ),
            "TD3",
        ),
    ),
)
def test_native_mrz_adapters_accept_valid_and_reject_altered_check_digits(
    parser, lines: tuple[str, ...], expected_format: str
) -> None:
    mrz = "\n".join(lines)
    parsed = parser(mrz)

    assert parsed["format"] == expected_format
    assert parsed["check_digits_valid"] is True
    assert parsed["document_number"]
    assert (
        MRZParser._parse(mrz, expected_format).document_number
        == parsed["document_number"]
    )

    altered = list(lines)
    altered[1] = f"{altered[1][:-1]}{'0' if altered[1][-1] != '0' else '1'}"
    invalid_mrz = "\n".join(altered)
    assert parser(invalid_mrz)["check_digits_valid"] is False
    with pytest.raises(MRZException):
        MRZParser._parse(invalid_mrz, expected_format)
    assert parse_mrz_with_validation(mrz).is_valid
    assert parse_mrz_simple(mrz) is not None
    assert not parse_mrz_with_validation(invalid_mrz).is_valid
    assert parse_mrz_simple(invalid_mrz) is None
