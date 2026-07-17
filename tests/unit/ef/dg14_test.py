import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).resolve().parents[3]
sys.path.append(str(project_root))

# Import from Marty's codebase
from marty_common.models.passport import DataGroup, DataGroupType


@pytest.mark.depends(
    on=[
        "tests/unit/ef/ef_base_test.py::test_ef_base",
        "tests/unit/ef/dg_base_test.py::test_dg_base",
    ]
)
def test_dg14_data_group():
    """Test the DataGroup class with DG14 data (Security Options)."""
    # Create a test security data structure - simulating how it might be stored in your system
    # In reality, this would be more complex structured data for Chip Authentication
    import json

    security_info = {
        "chipAuthenticationInfo": {"protocol": "id-CA-ECDH-3DES-CBC-CBC", "version": 1},
        "chipAuthenticationPublicKeyInfo": {
            "algorithm": "ECDH",
            "parameters": "secp256r1",
            "publicKey": "base64_encoded_public_key_would_go_here",
        },
    }

    # Convert to JSON string as a simple representation
    security_data = json.dumps(security_info)

    # Create a DG14 data group
    dg14 = DataGroup(type=DataGroupType.DG14, data=security_data)

    # Verify the data group properties
    assert dg14.type == DataGroupType.DG14
    assert dg14.data == security_data

    # Test dictionary conversion
    dg14_dict = dg14.to_dict()
    assert dg14_dict["type"] == "DG14"
    assert dg14_dict["data"] == security_data

    # Test reconstruction from dictionary
    dg14_reconstructed = DataGroup.from_dict(dg14_dict)
    assert dg14_reconstructed.type == DataGroupType.DG14
    assert dg14_reconstructed.data == security_data

    # Verify we can parse the data back to JSON
    reconstructed_data = json.loads(dg14_reconstructed.data)
    assert reconstructed_data["chipAuthenticationInfo"]["protocol"] == "id-CA-ECDH-3DES-CBC-CBC"
    assert reconstructed_data["chipAuthenticationInfo"]["version"] == 1
    assert reconstructed_data["chipAuthenticationPublicKeyInfo"]["algorithm"] == "ECDH"


def test_dg14_binary():
    """Test with actual DG14 binary data from a standard."""
    # Test vector taken from German BSI TR-03105-5 ReferenceDataSet
    tv_dg14 = bytes.fromhex(
        "6E82014A3182014630820122060904007F000702020102308201133081D406072A8648CE3D02013081C8020101302806072A8648CE3D0101021D00D7C134AA264366862A18302575D1D787B09F075797DA89F57EC8C0FF303C041C68A5E62CA9CE6C1C299803A6C1530B514E182AD8B0042A59CAD29F43041C2580F63CCFE44138870713B1A92369E33E2135D266DBB372386C400B0439040D9029AD2C7E5CF4340823B2A87DC68C9E4CE3174C1E6EFDEE12C07D58AA56F772C0726F24C6B89E4ECDAC24354B9E99CAA3F6D3761402CD021D00D7C134AA264366862A18302575D0FB98D116BC4B6DDEBCA3A5A7939F020101033A0004A847F020F71DF33D386BE7C9223A354D6AC7727018B26E281C6FFB96A83B142AAF303C23F2BCF2CDE4706C14E45914A9BE42C15BCB67A01F300F060A04007F00070202030201020101300D060804007F0007020202020101"
    )

    # Since we don't have a specific parser for DG14 in the Marty codebase,
    # we'll just create a DataGroup with the hex data
    import base64

    encoded_binary = base64.b64encode(tv_dg14).decode("utf-8")

    dg14 = DataGroup(type=DataGroupType.DG14, data=encoded_binary)

    assert dg14.type == DataGroupType.DG14
    assert dg14.data == encoded_binary
