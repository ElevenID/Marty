import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).resolve().parents[3]
sys.path.append(str(project_root))

# Import from Marty's codebase
from marty_backend_common.models.passport import Gender, MRZData
from marty_backend_common.utils.mrz_utils import MRZException, MRZFormatter, MRZParser


def test_mrz_data_model():
    """Test the MRZData model basic functionality."""
    # Create an MRZData instance
    mrz_data = MRZData(
        document_type="P",
        issuing_country="USA",
        document_number="123456789",
        surname="SMITH",
        given_names="JOHN",
        nationality="USA",
        date_of_birth="900101",  # YYMMDD format
        gender=Gender.MALE,
        date_of_expiry="250101",  # YYMMDD format
        personal_number="AB123456",
    )

    # Check that the properties are set correctly
    assert mrz_data.document_type == "P"
    assert mrz_data.issuing_country == "USA"
    assert mrz_data.document_number == "123456789"
    assert mrz_data.surname == "SMITH"
    assert mrz_data.given_names == "JOHN"
    assert mrz_data.nationality == "USA"
    assert mrz_data.date_of_birth == "900101"
    assert mrz_data.gender == Gender.MALE
    assert mrz_data.date_of_expiry == "250101"
    assert mrz_data.personal_number == "AB123456"

    # Test dictionary conversion
    mrz_dict = mrz_data.to_dict()
    assert mrz_dict["documentType"] == "P"
    assert mrz_dict["issuingCountry"] == "USA"
    assert mrz_dict["documentNumber"] == "123456789"
    assert mrz_dict["surname"] == "SMITH"
    assert mrz_dict["givenNames"] == "JOHN"
    assert mrz_dict["nationality"] == "USA"
    assert mrz_dict["dateOfBirth"] == "900101"
    assert mrz_dict["gender"] == "M"
    assert mrz_dict["dateOfExpiry"] == "250101"
    assert mrz_dict["personalNumber"] == "AB123456"

    # Test reconstruction from dictionary
    mrz_reconstructed = MRZData.from_dict(mrz_dict)
    assert mrz_reconstructed.document_type == "P"
    assert mrz_reconstructed.issuing_country == "USA"
    assert mrz_reconstructed.document_number == "123456789"
    assert mrz_reconstructed.surname == "SMITH"
    assert mrz_reconstructed.given_names == "JOHN"
    assert mrz_reconstructed.nationality == "USA"
    assert mrz_reconstructed.date_of_birth == "900101"
    assert mrz_reconstructed.gender == Gender.MALE
    assert mrz_reconstructed.date_of_expiry == "250101"
    assert mrz_reconstructed.personal_number == "AB123456"


def test_mrz_formatter():
    """Test the MRZ formatter functionality."""
    # Create an MRZData instance
    mrz_data = MRZData(
        document_type="P",
        issuing_country="UTO",
        document_number="L898902C3",
        surname="ERIKSSON",
        given_names="ANNA MARIA",
        nationality="UTO",
        date_of_birth="740812",  # YYMMDD format
        gender=Gender.FEMALE,
        date_of_expiry="120415",  # YYMMDD format
        personal_number="ZE184226B",
    )

    # Generate MRZ string
    mrz_string = MRZFormatter.generate_td3_mrz(mrz_data)

    # Verify basic structure
    assert len(mrz_string.split("\n")) == 2
    assert all(len(line) == 44 for line in mrz_string.split("\n"))
    assert mrz_string.startswith("P<UTO")


def test_mrz_parser():
    """Test the MRZ parser functionality."""
    # TD3 format MRZ (passport) from ICAO 9303 part 4 Appendix B
    mrz_string = (
        "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\n"
        "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
    )

    # Parse the MRZ string
    mrz_data = MRZParser.parse_td3_mrz(mrz_string)

    # Verify parsed data
    assert mrz_data.document_type == "P"
    assert mrz_data.issuing_country == "UTO"
    assert mrz_data.document_number == "L898902C3"
    assert mrz_data.surname == "ERIKSSON"
    assert mrz_data.given_names == "ANNA MARIA"
    assert mrz_data.nationality == "UTO"
    assert mrz_data.date_of_birth == "740812"
    assert mrz_data.gender == Gender.FEMALE
    assert mrz_data.date_of_expiry == "120415"
    assert mrz_data.personal_number == "ZE184226B"


def test_mrz_validation():
    """Test MRZ validation functionality."""
    # Valid MRZ
    valid_mrz = (
        "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\n"
        "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
    )

    assert MRZParser.parse_mrz(valid_mrz) is not None

    # Invalid MRZs - test with wrong format
    with pytest.raises(MRZException):
        MRZParser.parse_mrz("Invalid MRZ")

    # Invalid MRZ - wrong document type
    invalid_doc_type = (
        "I<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\n"
        "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
    )

    with pytest.raises(MRZException):
        MRZParser.parse_td3_mrz(invalid_doc_type)
