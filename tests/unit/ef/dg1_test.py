from marty_common.models.passport import DataGroup, DataGroupType


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
