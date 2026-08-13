from marty_common.models.passport import DataGroup, DataGroupType


def test_dg15_with_data_group():
    """Test the DataGroup class with DG15 data."""
    # Create a test public key in base64 format - simulating how it might be stored in your system
    # (This is a stub, not an actual valid public key)
    import base64

    test_pubkey = base64.b64encode(b"Example RSA public key data").decode("utf-8")

    # Create a DG15 data group
    dg15 = DataGroup(type=DataGroupType.DG15, data=test_pubkey)

    # Verify the data group properties
    assert dg15.type == DataGroupType.DG15
    assert dg15.data == test_pubkey

    # Test dictionary conversion
    dg15_dict = dg15.to_dict()
    assert dg15_dict["type"] == "DG15"
    assert dg15_dict["data"] == test_pubkey

    # Test reconstruction from dictionary
    dg15_reconstructed = DataGroup.from_dict(dg15_dict)
    assert dg15_reconstructed.type == DataGroupType.DG15
    assert dg15_reconstructed.data == test_pubkey
