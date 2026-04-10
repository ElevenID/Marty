import sys
from pathlib import Path

import pytest
from asn1crypto.core import CLASS_NAME_TO_NUM_MAP

# Add project root to path
project_root = Path(__file__).resolve().parents[3]
sys.path.append(str(project_root))

# Import the ElementaryFile from Marty's code base
from marty_backend_common.models.asn1_structures import ElementaryFile


def test_ef_base():
    # Fuzzy tests
    with pytest.raises(TypeError, match="contents must be a byte string, not NoneType"):
        ElementaryFile.load(None)
    with pytest.raises(
        ValueError, match="Insufficient data - 1 bytes requested but only 0 available"
    ):
        ElementaryFile.load(b"")
    with pytest.raises(
        ValueError, match="Insufficient data - 1 bytes requested but only 0 available"
    ):
        ElementaryFile.load(bytes.fromhex("01"))
    with pytest.raises(
        ValueError,
        match="Invalid elementary file class, expected class 'application' got 'universal'",
    ):
        ElementaryFile.class_ = CLASS_NAME_TO_NUM_MAP.get("application")
        ElementaryFile.load(bytes.fromhex("0000"))
    with pytest.raises(
        ValueError,
        match="Invalid elementary file method , expected method 'constructed' got 'primitive'",
    ):
        ElementaryFile.class_ = CLASS_NAME_TO_NUM_MAP.get("universal")
        ElementaryFile.method = 1
        ElementaryFile.load(bytes.fromhex("0000"))
    with pytest.raises(ValueError, match="Invalid elementary file tag, expected tag '1' got '0'"):
        ElementaryFile.method = None
        ElementaryFile.tag = 1
        ElementaryFile.load(bytes.fromhex("0000"))

    ElementaryFile.method = None
    ElementaryFile.class_ = None
    ElementaryFile.tag = None
