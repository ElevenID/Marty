import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).resolve().parents[3]
sys.path.append(str(project_root))


# Import from Marty's codebase
from marty_backend_common.models.passport import DataGroup, DataGroupType


def test_dg_type():
    """Test the DataGroupType enum."""
    # Test basic functionality of DataGroupType
    assert DataGroupType.DG1 == "DG1"
    assert DataGroupType.DG2 == "DG2"
    assert DataGroupType.DG3 == "DG3"
    assert DataGroupType.DG4 == "DG4"
    assert DataGroupType.DG5 == "DG5"
    assert DataGroupType.DG6 == "DG6"
    assert DataGroupType.DG7 == "DG7"
    assert DataGroupType.DG8 == "DG8"
    assert DataGroupType.DG9 == "DG9"
    assert DataGroupType.DG10 == "DG10"
    assert DataGroupType.DG11 == "DG11"
    assert DataGroupType.DG12 == "DG12"
    assert DataGroupType.DG13 == "DG13"
    assert DataGroupType.DG14 == "DG14"
    assert DataGroupType.DG15 == "DG15"
    assert DataGroupType.DG16 == "DG16"
    assert DataGroupType.SOD == "SOD"

    # Test that all expected DGs are defined
    for i in range(1, 17):
        dg_name = f"DG{i}"
        assert dg_name in DataGroupType._member_names_

    # SOD should also be defined
    assert "SOD" in DataGroupType._member_names_


@pytest.mark.depends(on=["test_dg_type"])
def test_dg_base():
    """Test basic functionality of the DataGroup class."""
    # Test that DataGroup can be instantiated with different types
    dg1 = DataGroup(type=DataGroupType.DG1, data="Test DG1 data")
    assert dg1.type == DataGroupType.DG1
    assert dg1.data == "Test DG1 data"

    dg2 = DataGroup(type=DataGroupType.DG2, data=b"Test DG2 binary data")
    assert dg2.type == DataGroupType.DG2
    assert dg2.data == b"Test DG2 binary data"

    # Test dictionary conversion
    dg1_dict = dg1.to_dict()
    assert dg1_dict["type"] == "DG1"
    assert dg1_dict["data"] == "Test DG1 data"

    # Test reconstruction from dictionary
    dg1_reconstructed = DataGroup.from_dict(dg1_dict)
    assert dg1_reconstructed.type == DataGroupType.DG1
    assert dg1_reconstructed.data == "Test DG1 data"
