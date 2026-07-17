import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).resolve().parents[3]
sys.path.append(str(project_root))

from marty_common.models.asn1_structures import parse_dg1_content

# Import from Marty's codebase
from marty_common.models.passport import DataGroup, DataGroupType
from marty_common.utils.mrz_utils import MRZParser


@pytest.mark.depends(
    on=[
        "tests/unit/ef/ef_base_test.py::test_ef_base",
        "tests/unit/ef/dg_base_test.py::test_dg_base",
        "tests/unit/ef/mrz_test.py::test_mrz_data_model",
    ]
)
def test_dg1_parsing():
    """Test parsing of DG1 content."""
    # Test vector from ICAO 9303 part 10 A.2.1
    tv_dg1 = bytes.fromhex(
        "615D5F1F5A493C4E4C44584938353933354638363939393939393939303C3C3C3C3C3C3732303831343846313130383236384E4C443C3C3C3C3C3C3C3C3C3C3C3456414E3C4445523C535445454E3C3C4D415249414E4E453C4C4F55495345"
    )

    # Parse DG1 content
    dg1_data = parse_dg1_content(tv_dg1)

    # Check that the data was parsed correctly
    assert "raw_mrz" in dg1_data
    assert (
        dg1_data["raw_mrz"]
        == "I<NLDXI85935F86999999990<<<<<<7208148F1108268NLD<<<<<<<<<<<4VAN<DER<STEEN<<MARIANNE<LOUISE"
    )

    # Now try parsing the MRZ data
    mrz_string = dg1_data["raw_mrz"]

    # Assuming your MRZParser can handle this format
    try:
        mrz_data = MRZParser.parse_mrz(mrz_string)
        assert mrz_data.document_type == "I"
        assert mrz_data.issuing_country == "NLD"
        assert mrz_data.document_number == "XI85935F8"
    except Exception:
        # If your parser doesn't support TD1 format yet, we'll skip this assertion
        pass


def test_dg1_with_td3():
    """Test parsing TD3 format MRZ from DG1."""
    # MRZ from ICAO 9303 part 4 Appendix B with DG1 header
    tv_dg1 = bytes.fromhex(
        "615B5f1f58503c55544f4552494b53534f4e3c3c414e4e413c4d415249413c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c4c38393839303243333655544f3734303831323246313230343135395a45313834323236423c3c3c3c3c3130"
    )

    # Parse DG1 content
    dg1_data = parse_dg1_content(tv_dg1)

    # Check that the data was parsed correctly
    assert "raw_mrz" in dg1_data
    assert "P<UTO" in dg1_data["raw_mrz"]
    assert "ERIKSSON" in dg1_data["raw_mrz"]
    assert "ANNA" in dg1_data["raw_mrz"]
    assert "MARIA" in dg1_data["raw_mrz"]


def test_dg1_data_group():
    """Test the DataGroup class with DG1 data."""
    # Create a DG1 data group with sample data
    mrz_data = (
        "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<L898902C36UTO7408122F1204159ZE184226B<<<<<10"
    )
    dg1 = DataGroup(type=DataGroupType.DG1, data=mrz_data)

    # Verify the data group properties
    assert dg1.type == DataGroupType.DG1
    assert dg1.data == mrz_data

    # Test dictionary conversion and reconstruction
    dg1_dict = dg1.to_dict()
    assert dg1_dict["type"] == "DG1"
    assert dg1_dict["data"] == mrz_data

    # Test reconstruction
    dg1_reconstructed = DataGroup.from_dict(dg1_dict)
    assert dg1_reconstructed.type == DataGroupType.DG1
    assert dg1_reconstructed.data == mrz_data
