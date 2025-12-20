"""
Digital signature models for e-passport security.

Models for XML Digital Signature (XMLDSIG) and Cryptographic Message Syntax (CMS)
structures used in e-passport security:
- XML Digital Signatures
- CMS SignedData structures
- Signature validation
- Key information

These models comply with W3C XML Digital Signature and RFC 5652 CMS standards.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class DigestAlgorithm(str, Enum):
    """Digest algorithms for digital signatures."""

    SHA1 = "SHA1"
    SHA256 = "SHA256"
    SHA384 = "SHA384"
    SHA512 = "SHA512"


class SignatureAlgorithm(str, Enum):
    """Signature algorithms for digital signatures."""

    RSA_WITH_SHA1 = "RSA-SHA1"
    RSA_WITH_SHA256 = "RSA-SHA256"
    RSA_WITH_SHA384 = "RSA-SHA384"
    RSA_WITH_SHA512 = "RSA-SHA512"
    ECDSA_WITH_SHA256 = "ECDSA-SHA256"
    ECDSA_WITH_SHA384 = "ECDSA-SHA384"
    ECDSA_WITH_SHA512 = "ECDSA-SHA512"


class CanonicalizationMethod(str, Enum):
    """XML canonicalization methods."""

    CANONICAL_XML_1_0 = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
    CANONICAL_XML_1_0_WITH_COMMENTS = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315#WithComments"
    CANONICAL_XML_1_1 = "http://www.w3.org/2006/12/xml-c14n11"
    CANONICAL_XML_1_1_WITH_COMMENTS = "http://www.w3.org/2006/12/xml-c14n11#WithComments"


class TransformAlgorithm(str, Enum):
    """XML transform algorithms."""

    ENVELOPED_SIGNATURE = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
    BASE64 = "http://www.w3.org/2000/09/xmldsig#base64"
    XPATH = "http://www.w3.org/TR/1999/REC-xpath-19991116"
    XPATH2 = "http://www.w3.org/2002/06/xmldsig-filter2"


@dataclass
class Reference:
    """Reference to a signed resource in XML Digital Signature."""

    uri: str
    digest_method: DigestAlgorithm
    digest_value: str  # Base64 encoded digest value
    transforms: list[TransformAlgorithm] = field(default_factory=list)
    id: str | None = None
    type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "uri": self.uri,
            "digestMethod": self.digest_method.value,
            "digestValue": self.digest_value,
        }

        if self.transforms:
            result["transforms"] = [t.value for t in self.transforms]

        if self.id:
            result["id"] = self.id

        if self.type:
            result["type"] = self.type

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Reference:
        """Create Reference from dictionary."""
        reference = cls(
            uri=data["uri"],
            digest_method=DigestAlgorithm(data["digestMethod"]),
            digest_value=data["digestValue"],
            id=data.get("id"),
            type=data.get("type"),
        )

        if "transforms" in data:
            reference.transforms = [
                TransformAlgorithm(transform) for transform in data["transforms"]
            ]

        return reference


@dataclass
class KeyInfo:
    """Key information in XML Digital Signature."""

    id: str | None = None
    x509_data: dict[str, Any] | None = None  # X.509 certificate data
    key_name: str | None = None
    key_value: dict[str, Any] | None = None  # Public key parameters
    retrieval_method: str | None = None  # URI to retrieve key

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {}

        if self.id:
            result["id"] = self.id

        if self.x509_data:
            result["x509Data"] = self.x509_data

        if self.key_name:
            result["keyName"] = self.key_name

        if self.key_value:
            result["keyValue"] = self.key_value

        if self.retrieval_method:
            result["retrievalMethod"] = self.retrieval_method

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KeyInfo:
        """Create KeyInfo from dictionary."""
        return cls(
            id=data.get("id"),
            x509_data=data.get("x509Data"),
            key_name=data.get("keyName"),
            key_value=data.get("keyValue"),
            retrieval_method=data.get("retrievalMethod"),
        )

    def set_x509_certificate(self, cert_data: str) -> None:
        """Set an X.509 certificate (PEM or Base64 encoded)."""
        if not self.x509_data:
            self.x509_data = {}
        self.x509_data["X509Certificate"] = cert_data


@dataclass
class SignedInfo:
    """SignedInfo element in XML Digital Signature."""

    canonicalization_method: CanonicalizationMethod
    signature_method: SignatureAlgorithm
    references: list[Reference]
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "canonicalizationMethod": self.canonicalization_method.value,
            "signatureMethod": self.signature_method.value,
            "references": [ref.to_dict() for ref in self.references],
        }

        if self.id:
            result["id"] = self.id

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SignedInfo:
        """Create SignedInfo from dictionary."""
        return cls(
            canonicalization_method=CanonicalizationMethod(data["canonicalizationMethod"]),
            signature_method=SignatureAlgorithm(data["signatureMethod"]),
            references=[Reference.from_dict(ref) for ref in data["references"]],
            id=data.get("id"),
        )


@dataclass
class XMLDSigSignature:
    """XML Digital Signature structure."""

    signed_info: SignedInfo
    signature_value: str  # Base64 encoded signature
    key_info: KeyInfo | None = None
    id: str | None = None
    object_data: list[dict[str, Any]] | None = None  # Additional objects

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {"signedInfo": self.signed_info.to_dict(), "signatureValue": self.signature_value}

        if self.key_info:
            result["keyInfo"] = self.key_info.to_dict()

        if self.id:
            result["id"] = self.id

        if self.object_data:
            result["objects"] = self.object_data

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> XMLDSigSignature:
        """Create XMLDSigSignature from dictionary."""
        signature = cls(
            signed_info=SignedInfo.from_dict(data["signedInfo"]),
            signature_value=data["signatureValue"],
            id=data.get("id"),
            object_data=data.get("objects"),
        )

        if "keyInfo" in data:
            signature.key_info = KeyInfo.from_dict(data["keyInfo"])

        return signature

    def to_xml(self) -> str:
        """
        Convert to XML format (stub implementation).

        In a real implementation, this would generate proper XML
        Digital Signature syntax.
        """
        # This would be a real XML generation in an implementation
        return f"<Signature>{self.id or ''}</Signature>"


@dataclass
class IssuerAndSerialNumber:
    """Issuer and serial number for CMS structures."""

    issuer_name: str  # Distinguished Name of issuer
    serial_number: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {"issuerName": self.issuer_name, "serialNumber": self.serial_number}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IssuerAndSerialNumber:
        """Create IssuerAndSerialNumber from dictionary."""
        return cls(issuer_name=data["issuerName"], serial_number=data["serialNumber"])


@dataclass
class SignerIdentifier:
    """Signer identifier for CMS structures."""

    issuer_and_serial: IssuerAndSerialNumber | None = None
    subject_key_identifier: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {}

        if self.issuer_and_serial:
            result["issuerAndSerial"] = self.issuer_and_serial.to_dict()

        if self.subject_key_identifier:
            result["subjectKeyIdentifier"] = self.subject_key_identifier

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SignerIdentifier:
        """Create SignerIdentifier from dictionary."""
        signer_id = cls()

        if "issuerAndSerial" in data:
            signer_id.issuer_and_serial = IssuerAndSerialNumber.from_dict(data["issuerAndSerial"])

        if "subjectKeyIdentifier" in data:
            signer_id.subject_key_identifier = data["subjectKeyIdentifier"]

        return signer_id


@dataclass
class AlgorithmIdentifier:
    """Algorithm identifier for CMS structures."""

    algorithm: str  # OID for the algorithm
    parameters: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {"algorithm": self.algorithm}

        if self.parameters is not None:
            result["parameters"] = self.parameters

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlgorithmIdentifier:
        """Create AlgorithmIdentifier from dictionary."""
        return cls(algorithm=data["algorithm"], parameters=data.get("parameters"))


@dataclass
class SignerInfo:
    """Signer information in CMS SignedData."""

    version: int
    signer_identifier: SignerIdentifier
    digest_algorithm: AlgorithmIdentifier
    signature_algorithm: AlgorithmIdentifier
    signature: str  # Base64 encoded signature
    signed_attrs: list[dict[str, Any]] | None = None
    unsigned_attrs: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "version": self.version,
            "signerIdentifier": self.signer_identifier.to_dict(),
            "digestAlgorithm": self.digest_algorithm.to_dict(),
            "signatureAlgorithm": self.signature_algorithm.to_dict(),
            "signature": self.signature,
        }

        if self.signed_attrs:
            result["signedAttrs"] = self.signed_attrs

        if self.unsigned_attrs:
            result["unsignedAttrs"] = self.unsigned_attrs

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SignerInfo:
        """Create SignerInfo from dictionary."""
        return cls(
            version=data["version"],
            signer_identifier=SignerIdentifier.from_dict(data["signerIdentifier"]),
            digest_algorithm=AlgorithmIdentifier.from_dict(data["digestAlgorithm"]),
            signature_algorithm=AlgorithmIdentifier.from_dict(data["signatureAlgorithm"]),
            signature=data["signature"],
            signed_attrs=data.get("signedAttrs"),
            unsigned_attrs=data.get("unsignedAttrs"),
        )


@dataclass
class EncapsulatedContent:
    """Encapsulated content in CMS structures."""

    content_type: str  # OID for content type
    content: str | bytes | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {"contentType": self.content_type}

        if isinstance(self.content, bytes):
            result["content"] = base64.b64encode(self.content).decode("ascii")
        elif self.content:
            result["content"] = self.content

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EncapsulatedContent:
        """Create EncapsulatedContent from dictionary."""
        content = data.get("content")

        # Try to detect if content is base64 encoded
        if content and isinstance(content, str) and len(content) % 4 == 0:
            try:
                decoded = base64.b64decode(content)
                content = decoded
            except:
                pass  # Not base64, keep as string

        return cls(content_type=data["contentType"], content=content)


@dataclass
class CMSSignedData:
    """CMS SignedData structure."""

    version: int
    digest_algorithms: list[AlgorithmIdentifier]
    encap_content_info: EncapsulatedContent
    signer_infos: list[SignerInfo]
    certificates: list[str] | None = None  # Base64 encoded X.509 certificates
    crls: list[str] | None = None  # Base64 encoded CRLs

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "version": self.version,
            "digestAlgorithms": [algo.to_dict() for algo in self.digest_algorithms],
            "encapContentInfo": self.encap_content_info.to_dict(),
            "signerInfos": [signer.to_dict() for signer in self.signer_infos],
        }

        if self.certificates:
            result["certificates"] = self.certificates

        if self.crls:
            result["crls"] = self.crls

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CMSSignedData:
        """Create CMSSignedData from dictionary."""
        return cls(
            version=data["version"],
            digest_algorithms=[
                AlgorithmIdentifier.from_dict(algo) for algo in data["digestAlgorithms"]
            ],
            encap_content_info=EncapsulatedContent.from_dict(data["encapContentInfo"]),
            signer_infos=[SignerInfo.from_dict(signer) for signer in data["signerInfos"]],
            certificates=data.get("certificates"),
            crls=data.get("crls"),
        )

    def to_der(self) -> bytes:
        """
        Convert to DER encoded format (stub implementation).

        In a real implementation, this would generate proper DER encoding.
        """
        # This would be real DER encoding in an implementation
        import json

        return json.dumps(self.to_dict()).encode("utf-8")

    @classmethod
    def from_der(cls, der_data: bytes) -> CMSSignedData:
        """
        Create CMSSignedData from DER encoded data (stub implementation).

        In a real implementation, this would parse proper DER encoding.
        """
        # This would be real DER decoding in an implementation
        import json

        return cls.from_dict(json.loads(der_data.decode("utf-8")))


@dataclass
class SignatureValidationResult:
    """Result of signature validation."""

    valid: bool
    signing_time: datetime | None = None
    signer_certificate: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {"valid": self.valid}

        if self.signing_time:
            result["signingTime"] = self.signing_time.isoformat()

        if self.signer_certificate:
            result["signerCertificate"] = self.signer_certificate

        if self.errors:
            result["errors"] = self.errors

        if self.warnings:
            result["warnings"] = self.warnings

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SignatureValidationResult:
        """Create SignatureValidationResult from dictionary."""
        result = cls(valid=data["valid"])

        if "signingTime" in data:
            result.signing_time = datetime.fromisoformat(data["signingTime"])

        if "signerCertificate" in data:
            result.signer_certificate = data["signerCertificate"]

        if "errors" in data:
            result.errors = data["errors"]

        if "warnings" in data:
            result.warnings = data["warnings"]

        return result
