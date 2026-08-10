"""Native-backed ICAO MRZ parsing with compatibility formatters."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from marty_common.models.passport import Gender, MRZData
from marty_common.native_backends import load_native_backend


class MRZException(ValueError):  # noqa: N818
    """Raised when native MRZ parsing or validation fails."""


def _native():
    return load_native_backend(
        "marty_verification",
        ("compute_check_digit", "parse_mrz", "validate_check_digit"),
    )


class MRZParser:
    """Compatibility adapter around the Rust TD1/TD2/TD3 parser."""

    @staticmethod
    def calculate_check_digit(input_string: str) -> str:
        return str(_native().compute_check_digit(input_string))

    @staticmethod
    def validate_check_digit(input_string: str, check_digit: str) -> bool:
        return bool(_native().validate_check_digit(input_string, check_digit))

    @staticmethod
    def clean_name(name: str) -> str:
        normalized = unicodedata.normalize("NFKD", name)
        ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^A-Z0-9<]", "<", ascii_name.upper().replace(" ", "<"))

    @classmethod
    def _parse(cls, mrz: str, expected_format: str | None = None) -> MRZData:
        lines = [line.strip() for line in mrz.strip().splitlines() if line.strip()]
        if len(lines) == 1:
            length = len(lines[0])
            if length == 88:
                lines = [lines[0][:44], lines[0][44:]]
            elif length == 90:
                lines = [lines[0][:30], lines[0][30:60], lines[0][60:]]
            elif length == 72:
                lines = [lines[0][:36], lines[0][36:]]
        try:
            parsed = _native().parse_mrz(lines)
            values = parsed.to_dict()
        except Exception as exc:
            raise MRZException(str(exc)) from exc
        if expected_format and values.get("format") != expected_format:
            raise MRZException(f"Expected {expected_format} MRZ, got {values.get('format')}")
        if expected_format == "TD3" and values.get("document_type") != "P":
            raise MRZException("TD3 MRZ must use the passport document designator P")
        if not values.get("check_digits_valid", False):
            raise MRZException("MRZ check digits are invalid")
        sex = values.get("sex") or "X"
        try:
            gender = Gender(sex)
        except ValueError:
            gender = Gender.UNSPECIFIED
        return MRZData(
            document_type=values.get("document_type", ""),
            issuing_country=values.get("issuing_country", ""),
            document_number=values.get("document_number", ""),
            surname=values.get("surname", ""),
            given_names=values.get("given_names", ""),
            nationality=values.get("nationality", ""),
            date_of_birth=values.get("date_of_birth", ""),
            gender=gender,
            date_of_expiry=values.get("date_of_expiry", ""),
            personal_number=values.get("optional_data") or None,
        )

    @classmethod
    def parse_td3_mrz(cls, mrz: str) -> MRZData:
        return cls._parse(mrz, "TD3")

    @classmethod
    def parse_td2_mrz(cls, mrz: str) -> MRZData:
        return cls._parse(mrz, "TD2")

    @classmethod
    def parse_td1_mrz(cls, mrz: str) -> MRZData:
        return cls._parse(mrz, "TD1")

    @classmethod
    def parse_mrz(cls, mrz: str) -> MRZData:
        return cls._parse(mrz)


def parse_td1_mrz(mrz: str) -> dict[str, Any]:
    """Return the historical dictionary shape from native TD1 parsing."""

    parsed = _native().parse_mrz(mrz.strip().splitlines())
    values = parsed.to_dict()
    if values.get("format") != "TD1":
        raise MRZException("MRZ is not TD1")
    return values


def parse_td2_mrz(mrz: str) -> dict[str, Any]:
    parsed = _native().parse_mrz(mrz.strip().splitlines())
    values = parsed.to_dict()
    if values.get("format") != "TD2":
        raise MRZException("MRZ is not TD2")
    return values


def parse_td3_mrz(mrz: str) -> dict[str, Any]:
    parsed = _native().parse_mrz(mrz.strip().splitlines())
    values = parsed.to_dict()
    if values.get("format") != "TD3":
        raise MRZException("MRZ is not TD3")
    return values


def validate_td1_check_digits(mrz: str) -> bool:
    try:
        MRZParser.parse_td1_mrz(mrz)
    except MRZException:
        return False
    return True


def generate_td1_mrz(data: Any) -> str:
    return MRZFormatter.generate_td1_mrz(data)


class MRZFormatter:
    """Format MRZ output while delegating every check digit to Rust."""

    @staticmethod
    def format_name(name: str, max_length: int) -> str:
        return MRZParser.clean_name(name)[:max_length]

    @staticmethod
    def format_document_number(number: str, total_length: int = 9) -> str:
        cleaned = re.sub(r"[^A-Z0-9]", "", number.upper())
        return cleaned[:total_length].ljust(total_length, "<")

    @staticmethod
    def generate_td3_mrz(data: MRZData) -> str:
        line1 = (
            f"{data.document_type}<{data.issuing_country.upper()}"
            f"{MRZParser.clean_name(data.surname)}<<{MRZParser.clean_name(data.given_names)}"
        )[:44].ljust(44, "<")
        document_number = MRZFormatter.format_document_number(data.document_number)
        document_check = MRZParser.calculate_check_digit(document_number)
        birth_check = MRZParser.calculate_check_digit(data.date_of_birth)
        expiry_check = MRZParser.calculate_check_digit(data.date_of_expiry)
        personal = re.sub(r"[^A-Z0-9<]", "", (data.personal_number or "").upper())[:14].ljust(14, "<")
        personal_check = MRZParser.calculate_check_digit(personal)
        composite = (
            document_number
            + document_check
            + data.date_of_birth
            + birth_check
            + data.date_of_expiry
            + expiry_check
            + personal
            + personal_check
        )
        line2 = (
            document_number
            + document_check
            + data.nationality.upper()
            + data.date_of_birth
            + birth_check
            + data.gender.value
            + data.date_of_expiry
            + expiry_check
            + personal
            + personal_check
            + MRZParser.calculate_check_digit(composite)
        )
        return f"{line1}\n{line2}"

    @staticmethod
    def generate_td1_mrz(data: Any) -> str:
        document_type = getattr(data, "document_type", "I")[:2].ljust(2, "<")
        country = getattr(data, "issuing_country", "").upper()[:3].ljust(3, "<")
        number = MRZFormatter.format_document_number(getattr(data, "document_number", ""), 9)
        optional = re.sub(r"[^A-Z0-9<]", "", (getattr(data, "optional_data", "") or "").upper())
        line1 = (
            document_type + country + number + MRZParser.calculate_check_digit(number) + optional[:15].ljust(15, "<")
        )
        birth = getattr(data, "date_of_birth", "")
        expiry = getattr(data, "date_of_expiry", "")
        nationality = getattr(data, "nationality", "").upper()[:3].ljust(3, "<")
        gender = getattr(data, "gender", Gender.UNSPECIFIED)
        gender_value = gender.value if hasattr(gender, "value") else str(gender)[:1]
        line2_without_composite = (
            birth
            + MRZParser.calculate_check_digit(birth)
            + gender_value
            + expiry
            + MRZParser.calculate_check_digit(expiry)
            + nationality
            + optional[15:26].ljust(11, "<")
        )
        composite_data = (
            line1[5:30] + line2_without_composite[:7] + line2_without_composite[8:15] + line2_without_composite[18:29]
        )
        line2 = line2_without_composite + MRZParser.calculate_check_digit(composite_data)
        names = (
            f"{MRZParser.clean_name(getattr(data, 'surname', ''))}"
            f"<<{MRZParser.clean_name(getattr(data, 'given_names', ''))}"
        )
        return f"{line1[:30].ljust(30, '<')}\n{line2[:30].ljust(30, '<')}\n{names[:30].ljust(30, '<')}"


__all__ = [
    "MRZException",
    "MRZFormatter",
    "MRZParser",
    "generate_td1_mrz",
    "parse_td1_mrz",
    "parse_td2_mrz",
    "parse_td3_mrz",
    "validate_td1_check_digits",
]
