"""Compatibility models and adapters for native ICAO elementary-file parsing.

All TLV, MRZ, biometric-field, and data-group parsing is implemented by the
canonical Rust eMRTD kernel. Python retains the established DTOs only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from marty_common.crypto_bridge import validate_check_digit as _rust_validate_check_digit
from marty_common.emrtd_native import (
    parse_ef_com as _native_parse_ef_com,
)
from marty_common.emrtd_native import (
    parse_ef_dg1 as _native_parse_ef_dg1,
)
from marty_common.emrtd_native import (
    parse_ef_dg2 as _native_parse_ef_dg2,
)
from marty_common.emrtd_native import (
    parse_elementary_file as _native_parse_elementary_file,
)
from marty_common.emrtd_native import (
    parse_tlv as _native_parse_tlv,
)


class DataGroup(Enum):
    """ICAO Data Group identifiers."""

    COM = "EF.COM"
    SOD = "EF.SOD"
    DG1 = "EF.DG1"
    DG2 = "EF.DG2"
    DG3 = "EF.DG3"
    DG4 = "EF.DG4"
    DG5 = "EF.DG5"
    DG6 = "EF.DG6"
    DG7 = "EF.DG7"
    DG8 = "EF.DG8"
    DG9 = "EF.DG9"
    DG10 = "EF.DG10"
    DG11 = "EF.DG11"
    DG12 = "EF.DG12"
    DG13 = "EF.DG13"
    DG14 = "EF.DG14"
    DG15 = "EF.DG15"
    DG16 = "EF.DG16"


@dataclass
class EFData:
    """Parsed Elementary File data."""

    file_id: str
    tag: int
    length: int
    data: bytes
    parsed_content: dict[str, Any] | None = None


@dataclass
class MRZInfo:
    """Machine Readable Zone information from DG1."""

    document_code: str
    issuing_country: str
    surname: str
    given_names: str
    passport_number: str
    nationality: str
    date_of_birth: str
    sex: str
    date_of_expiry: str
    personal_number: str | None
    check_digit_composite: str


@dataclass
class BiometricInfo:
    """Biometric information structure."""

    biometric_type: int
    biometric_subtype: int
    creation_date: str | None
    validity_period: tuple[str, str] | None
    creator: str | None
    format_owner: int
    format_type: int
    quality: int | None
    data: bytes


def _mrz_info(result: dict[str, Any]) -> MRZInfo:
    return MRZInfo(
        document_code=str(result["document_code"]),
        issuing_country=str(result["issuing_country"]),
        surname=str(result["surname"]),
        given_names=str(result["given_names"]),
        passport_number=str(result["passport_number"]),
        nationality=str(result["nationality"]),
        date_of_birth=str(result["date_of_birth"]),
        sex=str(result["sex"]),
        date_of_expiry=str(result["date_of_expiry"]),
        personal_number=(str(result["personal_number"]) if result.get("personal_number") is not None else None),
        check_digit_composite=str(result["check_digit_composite"]),
    )


def _biometric_info(result: dict[str, Any]) -> BiometricInfo:
    validity = result.get("validity_period")
    return BiometricInfo(
        biometric_type=int(result["biometric_type"]),
        biometric_subtype=int(result["biometric_subtype"]),
        creation_date=result.get("creation_date"),
        validity_period=(tuple(validity) if validity is not None else None),
        creator=result.get("creator"),
        format_owner=int(result["format_owner"]),
        format_type=int(result["format_type"]),
        quality=(int(result["quality"]) if result.get("quality") is not None else None),
        data=bytes(result["data"]),
    )


class ElementaryFileParser:
    """Stable Python surface over the native elementary-file parser."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def parse_tlv(self, data: bytes, offset: int = 0) -> tuple[int, int, bytes, int]:
        """Parse a bounded BER/DER TLV using Rust."""

        result = _native_parse_tlv(data, offset)
        return (
            int(result["tag"]),
            int(result["length"]),
            bytes(result["value"]),
            int(result["next_offset"]),
        )

    def parse_ef_com(self, data: bytes) -> dict[str, Any]:
        """Parse EF.COM using Rust."""

        return _native_parse_ef_com(data)

    def parse_ef_dg1(self, data: bytes) -> MRZInfo:
        """Parse EF.DG1 and its TD1/TD2/TD3 MRZ using Rust."""

        return _mrz_info(_native_parse_ef_dg1(data))

    def parse_ef_dg2(self, data: bytes) -> BiometricInfo:
        """Parse EF.DG2 biometric metadata using Rust."""

        return _biometric_info(_native_parse_ef_dg2(data))

    def parse_elementary_file(self, file_id: str, data: bytes) -> EFData:
        """Parse any elementary file through the canonical Rust dispatcher."""

        result = _native_parse_elementary_file(file_id, data)
        parsed_content = result.get("parsed_content")
        if parsed_content is not None:
            parsed_content = dict(parsed_content)
            if file_id == DataGroup.DG2.value:
                parsed_content["data"] = bytes(parsed_content["data"])
        return EFData(
            file_id=str(result["file_id"]),
            tag=int(result["tag"]),
            length=int(result["length"]),
            data=bytes(result["data"]),
            parsed_content=parsed_content,
        )

    def validate_mrz_check_digit(self, data: str, check_digit: str) -> bool:
        """Validate an ICAO MRZ check digit using Rust."""

        return bool(_rust_validate_check_digit(data, check_digit))


__all__ = [
    "BiometricInfo",
    "DataGroup",
    "EFData",
    "ElementaryFileParser",
    "MRZInfo",
]
