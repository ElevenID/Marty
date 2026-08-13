

def test_signed_object():
    """Test the SignedObject class which is used to represent SODs in Marty."""
    import base64
    import time

    from marty_common.models.passport import SignedObject

    # Create a test signature (base64 encoded)
    signature_bytes = b"This is a test signature"
    signature_b64 = base64.b64encode(signature_bytes).decode("utf-8")
    timestamp = int(time.time())

    # Create a SignedObject
    sod = SignedObject(signature=signature_b64, timestamp=timestamp)

    # Test properties
    assert sod.signature == signature_b64
    assert sod.timestamp == timestamp
    assert sod.algorithm == "SHA256withRSA"  # Default value

    # Test methods
    sod_string = sod.to_string()
    assert sod_string == f"{signature_b64}.{timestamp}"

    # Test reconstruction from string
    sod_reconstructed = SignedObject.from_string(sod_string)
    assert sod_reconstructed.signature == signature_b64
    assert sod_reconstructed.timestamp == timestamp

    # Test dictionary conversion
    sod_dict = sod.to_dict()
    assert sod_dict["signature"] == signature_b64
    assert sod_dict["timestamp"] == timestamp
    assert sod_dict["algorithm"] == "SHA256withRSA"

    # Test reconstruction from dictionary
    sod_reconstructed2 = SignedObject.from_dict(sod_dict)
    assert sod_reconstructed2.signature == signature_b64
    assert sod_reconstructed2.timestamp == timestamp
    assert sod_reconstructed2.algorithm == "SHA256withRSA"
