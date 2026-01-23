"""
Validation utilities for Marty services.

This module provides validation functions used across multiple Marty services,
including format checking, data verification, and validation against schemas.
"""

import re
from datetime import datetime
from typing import Any  # Removed Optional, Union

from .exceptions import InvalidInputError
from .utils.mrz_utils import MRZException, MRZParser


def validate_passport_data(data: dict[str, Any]) -> None:
    """
    Validate passport data against expected format and requirements.
    Raises InvalidInputError if validation fails.

    Args:
        data: The passport data to validate
    """
    errors = []

    # Check required fields
    required_fields = [
        "documentNumber",
        "issuingCountry",
        "surname",
        "givenNames",
        "nationality",
        "dateOfBirth",
        "gender",
        "dateOfExpiry",
    ]

    errors.extend(
        f"Missing required field: {field}" for field in required_fields if field not in data
    )

    if errors:
        raise InvalidInputError(", ".join(errors))

    # Document number validation
    if not re.match(r"^[A-Z0-9]{5,15}$", data["documentNumber"]):
        errors.append("Document number must be 5-15 alphanumeric characters")

    # Country code validation
    if not re.match(r"^[A-Z]{3}$", data["issuingCountry"]):
        errors.append("Issuing country must be a 3-letter country code")

    # Name validation
    if not re.match(r"^[A-Z\s\-\']{1,40}$", data["surname"]):
        errors.append(
            "Surname must contain only uppercase letters, spaces, hyphens or apostrophes"
            " (1-40 chars)"
        )

    if not re.match(r"^[A-Z\s\-\']{1,40}$", data["givenNames"]):
        errors.append(
            "Given names must contain only uppercase letters, spaces, hyphens or apostrophes"
            " (1-40 chars)"
        )

    # Gender validation
    if data["gender"] not in ["M", "F", "X"]:
        errors.append("Gender must be 'M', 'F', or 'X'")

    # Date validation
    try:
        date_format = "%Y-%m-%d"
        dob = datetime.strptime(data["dateOfBirth"], date_format).date()
        expiry = datetime.strptime(data["dateOfExpiry"], date_format).date()

        today = datetime.now().date()
        if dob > today:
            errors.append("Date of birth cannot be in the future")

        if expiry < today:
            errors.append("Date of expiry cannot be in the past")

    except ValueError:
        errors.append("Dates must be in YYYY-MM-DD format")

    if errors:
        raise InvalidInputError(", ".join(errors))


def validate_certificate_data(data: dict[str, Any]) -> None:
    """
    Validate certificate data against expected format.
    Raises InvalidInputError if validation fails.

    Args:
        data: The certificate data to validate
    """
    errors = []

    # Check required fields
    required_fields = [
        "id",
        "subject",
        "issuer",
        "validFrom",
        "validTo",
        "certificateData",
        "status",
    ]

    errors.extend(
        f"Missing required field: {field}" for field in required_fields if field not in data
    )

    if errors:
        raise InvalidInputError(", ".join(errors))

    # Status validation
    valid_statuses = ["ACTIVE", "EXPIRED", "REVOKED"]
    if data["status"] not in valid_statuses:
        errors.append(f"Status must be one of: {', '.join(valid_statuses)}")

    # Date format validation
    try:
        datetime.fromisoformat(data["validFrom"])
    except ValueError:
        errors.append("validFrom date must be in ISO format (YYYY-MM-DDTHH:MM:SS)")

    try:
        datetime.fromisoformat(data["validTo"])
    except ValueError:
        errors.append("validTo date must be in ISO format (YYYY-MM-DDTHH:MM:SS)")

    if errors:
        raise InvalidInputError(", ".join(errors))


def validate_mrz(mrz_string: str) -> None:
    """
    Validate Machine Readable Zone (MRZ) string format.
    Raises InvalidInputError if validation fails.

    Args:
        mrz_string: The MRZ string to validate
    """
    try:
        MRZParser.parse_td3_mrz(mrz_string)
    except MRZException as exc:
        raise InvalidInputError(str(exc)) from exc


def is_valid_dn(dn: str) -> bool:
    """
    Validate if a string is a valid Distinguished Name (DN) format.

    Args:
        dn: The Distinguished Name to validate

    Returns:
        True if valid, False otherwise
    """
    dn_pattern = r"^CN=[^,]+,((OU|O|C|DC|ST|L)=[^,]+,)*((OU|O|C|DC|ST|L)=[^,]+)$"
    return bool(re.match(dn_pattern, dn))
