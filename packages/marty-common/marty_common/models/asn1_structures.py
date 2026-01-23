"""
ASN.1 data structures for e-passport chip data.

These structures implement the ASN.1 formats defined in ICAO Doc 9303.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from asn1crypto import algos, cms, core, pem, x509


class ElementaryFile(core.Asn1Value):
    """Generic ASN.1 wrapper representing an elementary file structure.

    This class intentionally does not define a concrete ASN.1 schema. It
    leverages asn1crypto's base loader validation on ``class_``, ``method``,
    and ``tag``. Tests may modify these class attributes at runtime to validate
    error handling for invalid headers. The default values are ``None`` so the
    base loader will not enforce header expectations unless explicitly set.
    """

    # These are class-level attributes on purpose; tests mutate them.
    class_: int | None = None
    method: int | None = None
    tag: int | None = None

    @classmethod
    def load(cls, encoded_data, strict: bool = False, **kwargs):  # type: ignore[override]
        """Minimal header validation to support unit tests.

        This validates ASN.1 identifier octet expectations when test code
        mutates the class attributes `class_`, `method`, and `tag`.
        """
        # Match expected error messages from tests/asn1 expectations
        if encoded_data is None:
            msg = "contents must be a byte string, not NoneType"
            raise TypeError(msg)

        if not isinstance(encoded_data, (bytes, bytearray)):
            msg = f"contents must be a byte string, not {type(encoded_data).__name__}"
            raise TypeError(msg)

        if len(encoded_data) < 1:
            msg = "Insufficient data - 1 bytes requested but only 0 available"
            raise ValueError(msg)

        # Read first identifier octet
        first_octet = encoded_data[0]

        # Extract class (bits 7-8), method/pc (bit 6), short-form tag (bits 1-5)
        actual_class = (first_octet & 0b1100_0000) >> 6
        actual_constructed = (first_octet & 0b0010_0000) >> 5  # 1 => constructed, 0 => primitive
        actual_tag = first_octet & 0b0001_1111

        # Map class numbers to names for readable errors
        try:
            from asn1crypto.core import NUM_TO_CLASS_NAME_MAP  # type: ignore
        except Exception:
            NUM_TO_CLASS_NAME_MAP = {0: "universal", 1: "application", 2: "context", 3: "private"}

        if cls.class_ is not None and actual_class != cls.class_:
            expected_name = NUM_TO_CLASS_NAME_MAP.get(cls.class_, str(cls.class_))
            got_name = NUM_TO_CLASS_NAME_MAP.get(actual_class, str(actual_class))
            msg = (
                f"Invalid elementary file class, expected class '{expected_name}' got '{got_name}'"
            )
            raise ValueError(msg)

        if cls.method is not None and actual_constructed != cls.method:
            expected = "constructed" if cls.method == 1 else "primitive"
            got = "constructed" if actual_constructed == 1 else "primitive"
            msg = f"Invalid elementary file method , expected method '{expected}' got '{got}'"
            raise ValueError(msg)

        if cls.tag is not None and actual_tag != cls.tag:
            msg = f"Invalid elementary file tag, expected tag '{cls.tag}' got '{actual_tag}'"
            raise ValueError(msg)

        # If validation passes, delegate to base implementation for completeness
        return super().load(encoded_data, strict=strict, **kwargs)


class LDSVersionInfo(core.Sequence):
    """LDS Version Information according to ICAO Doc 9303."""

    _fields = [
        ("ldsVersion", core.PrintableString),
        ("unicodeVersion", core.PrintableString),
    ]


class DataGroupHash(core.Sequence):
    """Data Group Hash structure for Document Security Object."""

    _fields = [
        ("dataGroupNumber", core.Integer),
        ("dataGroupHashValue", core.OctetString),
    ]


class DataGroupHashValues(core.SequenceOf):
    """Collection of Data Group Hash values."""

    _child_spec = DataGroupHash


class SecurityInfos(core.SequenceOf):
    """Collection of Security Infos for DG14."""

    _child_spec = core.Any


class LDSSecurityObject(core.Sequence):
    """LDS Security Object as defined in ICAO Doc 9303."""

    _fields = [
        ("version", core.Integer, {"default": 0}),
        ("hashAlgorithm", algos.DigestAlgorithm),
        ("dataGroupHashValues", DataGroupHashValues),
        ("ldsVersionInfo", LDSVersionInfo, {"optional": True}),
    ]


class EFCardAccess(core.Sequence):
    """EF.CardAccess file structure."""

    _fields = [
        ("paceInfo", SecurityInfos, {"optional": True}),
        ("chipAuthenticationInfo", SecurityInfos, {"optional": True}),
    ]


class PACEInfo(core.Sequence):
    """PACE Info structure."""

    _fields = [
        ("protocol", core.ObjectIdentifier),
        ("version", core.Integer, {"default": 1}),
        ("parameterId", core.Integer, {"optional": True}),
    ]


class PACEDomainParameterInfo(core.Sequence):
    """PACE Domain Parameter Info structure."""

    _fields = [
        ("protocol", core.ObjectIdentifier),
        ("domainParameter", core.Any),
        ("parameterId", core.Integer, {"optional": True}),
    ]


class ChipAuthenticationInfo(core.Sequence):
    """Chip Authentication Info structure."""

    _fields = [
        ("protocol", core.ObjectIdentifier),
        ("version", core.Integer, {"default": 1}),
        ("keyId", core.Integer, {"optional": True}),
    ]


class ChipAuthenticationPublicKeyInfo(core.Sequence):
    """Chip Authentication Public Key Info structure."""

    _fields = [
        ("protocol", core.ObjectIdentifier),
        ("chipAuthenticationPublicKey", core.Any),
        ("keyId", core.Integer, {"optional": True}),
    ]


class ActiveAuthenticationInfo(core.Sequence):
    """Active Authentication Info structure."""

    _fields = [
        ("protocol", core.ObjectIdentifier),
        ("signatureAlgorithm", core.ObjectIdentifier, {"optional": True}),
    ]


class DSCertificate(x509.Certificate):
    """Document Signer Certificate."""


class SOD(cms.ContentInfo):
    """Document Security Object (SOD) for e-passport."""

    @classmethod
    def load(cls, encoded_data: bytes) -> SOD:  # type: ignore[override]
        """Load SOD from DER or PEM encoded bytes."""

        if pem.detect(encoded_data):
            _, _, encoded_data = pem.unarmor(encoded_data)

        return super().load(encoded_data)

    @property
    def signed_data(self) -> cms.SignedData:
        """Return embedded SignedData structure."""

        content = self["content"]
        if isinstance(content, cms.SignedData):
            return content
        return content.parsed  # type: ignore[return-value]

    def get_security_object(self) -> LDSSecurityObject:
        """
        Extract the LDSSecurityObject from the SOD.

        Returns:
            LDSSecurityObject containing the data group hashes
        """
        signed_data = self.signed_data
        encap_content_info = signed_data["encap_content_info"]
        content = encap_content_info["content"].parsed

        return LDSSecurityObject.load(content.dump())

    def get_signing_time(self) -> datetime | None:
        """
        Get the signing time from the SOD.

        Returns:
            Signing time as datetime or None if not available
        """
        for signer_info in self.signed_data["signer_infos"]:
            signed_attrs = signer_info["signed_attrs"]
            for attr in signed_attrs:
                if attr["type"].native == "signing_time":
                    return attr["values"][0].native

        return None

    def get_certificate(self) -> DSCertificate | None:
        """
        Get the Document Signer Certificate from the SOD.

        Returns:
            DSC or None if not available
        """
        signed_data = self.signed_data

        if not signed_data["certificates"]:
            return None

        # Usually the first certificate is the DSC
        return DSCertificate.load(signed_data["certificates"][0].dump())


def parse_dg1_content(dg1_data: bytes) -> dict[str, Any]:
    """
    Parse DG1 content (MRZ data).

    Args:
        dg1_data: The raw DG1 data

    Returns:
        Dictionary containing the parsed MRZ data
    """
    # The structure of DG1 is a simple TLV with tag 61
    # The content is the MRZ data as text
    if dg1_data[0] != 0x61:
        msg = "Invalid DG1 data: Expected tag 0x61"
        raise ValueError(msg)

    # Skip the tag and length bytes to get to the value
    # This is a simplification - in real implementation we would need proper TLV parsing
    if dg1_data[1] < 128:
        offset = 2  # Simple length encoding
    else:
        length_bytes = dg1_data[1] & 0x7F
        offset = 2 + length_bytes

    # The value contains another TLV structure with tag 5F1F
    if dg1_data[offset] != 0x5F or dg1_data[offset + 1] != 0x1F:
        msg = "Invalid DG1 data: Expected tag 0x5F1F for MRZ"
        raise ValueError(msg)

    # Skip to the MRZ value
    if dg1_data[offset + 2] < 128:
        mrz_offset = offset + 3
    else:
        length_bytes = dg1_data[offset + 2] & 0x7F
        mrz_offset = offset + 3 + length_bytes

    # The MRZ is stored as ASCII text
    mrz_data = dg1_data[mrz_offset:].decode("ascii")

    # Now we should parse the MRZ data according to its format
    # This would normally be done using the MRZParser class
    return {"raw_mrz": mrz_data}


def parse_dg2_content(dg2_data: bytes) -> dict[str, Any]:
    """
    Parse DG2 content (Facial image).

    Args:
        dg2_data: The raw DG2 data

    Returns:
        Dictionary containing the parsed facial image data
    """
    # DG2 has a complex nested structure according to ISO/IEC 19794-5
    # This is a simplified implementation
    result = {"facial_images": []}

    # In a real implementation, we would parse the nested TLV structures
    # to extract the facial images and their metadata

    # For now, just indicate that we have data
    result["raw_data_length"] = len(dg2_data)
    return result


def parse_dg15_content(dg15_data: bytes) -> dict[str, Any]:
    """
    Parse DG15 content (Active Authentication Public Key).

    Args:
        dg15_data: The raw DG15 data

    Returns:
        Dictionary containing the parsed public key data
    """
    # DG15 contains a SubjectPublicKeyInfo structure
    # Skip the TLV header
    if dg15_data[0] != 0x6F:
        msg = "Invalid DG15 data: Expected tag 0x6F"
        raise ValueError(msg)

    # Find the actual key data
    # This is a simplification - in real implementation we would need proper TLV parsing
    if dg15_data[1] < 128:
        offset = 2  # Simple length encoding
    else:
        length_bytes = dg15_data[1] & 0x7F
        offset = 2 + length_bytes

    # Parse the public key
    try:
        from cryptography.hazmat.primitives.serialization import load_der_public_key

        public_key = load_der_public_key(dg15_data[offset:])

        # Extract key information
        from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, rsa

        key_info = {"algorithm": "unknown"}

        if isinstance(public_key, rsa.RSAPublicKey):
            key_info["algorithm"] = "RSA"
            key_info["key_size"] = public_key.key_size
            key_info["public_numbers"] = {
                "e": public_key.public_numbers().e,
                "n": str(public_key.public_numbers().n)[:20] + "...",  # Truncated for readability
            }
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            key_info["algorithm"] = "EC"
            key_info["curve"] = public_key.curve.name
        elif isinstance(public_key, ed25519.Ed25519PublicKey):
            key_info["algorithm"] = "Ed25519"
        elif isinstance(public_key, ed448.Ed448PublicKey):
            key_info["algorithm"] = "Ed448"

    except Exception as e:
        # Fallback if the cryptography module can't parse the key
        return {
            "error": f"Could not parse public key: {e!s}",
            "raw_data_length": len(dg15_data) - offset,
        }
    else:
        return key_info
