"""
Core ISO/IEC 18013-5 Components

This module implements the fundamental data structures and protocols
defined in ISO/IEC 18013-5 for mobile driving licenses.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import cbor2
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class ProtocolVersion(Enum):
    """Supported protocol versions"""

    V1_0 = "1.0"


class TransportMethod(Enum):
    """Transport methods for mDL transactions"""

    BLE = "BLE"
    NFC = "NFC"
    WIFI_AWARE = "WiFi-Aware"
    HTTP = "HTTP"


class EngagementMethod(Enum):
    """Device engagement methods"""

    QR_CODE = "QR"
    NFC_STATIC = "NFC-Static"
    NFC_NEGOTIATED = "NFC-Negotiated"


@dataclass
class DeviceEngagement:
    """
    Device Engagement structure according to ISO 18013-5 Section 8.3.1

    This structure contains the information needed to establish a secure
    connection between the mDL holder device and the mDL reader.
    """

    version: str = "1.0"
    security: dict[str, Any] = field(default_factory=dict)
    device_key_info: dict[str, Any] = field(default_factory=dict)
    protocol_info: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        """Initialize default values if not provided"""
        if not self.security:
            # Default security parameters (cipher suites, key agreement)
            self.security = {
                1: 2,  # cipher_suites: AES-256-GCM
                2: [  # key_agreement_methods
                    {"kty": "EC2", "crv": "P-256", "key_ops": ["keyAgreement"]}
                ],
            }

        if not self.device_key_info:
            # Generate ephemeral device key for this engagement
            private_key = ec.generate_private_key(ec.SECP256R1())
            public_key = private_key.public_key()

            # Convert to COSE key format
            public_numbers = public_key.public_numbers()
            self.device_key_info = {
                1: 2,  # kty: EC2
                3: -7,  # alg: ES256
                -1: 1,  # crv: P-256
                -2: public_numbers.x.to_bytes(32, "big"),  # x coordinate
                -3: public_numbers.y.to_bytes(32, "big"),  # y coordinate
            }

    def to_cbor(self) -> bytes:
        """Serialize to CBOR format"""
        return cbor2.dumps(
            {
                "version": self.version,
                "security": self.security,
                "deviceKeyInfo": self.device_key_info,
                "protocolInfo": self.protocol_info,
            }
        )

    @classmethod
    def from_cbor(cls, data: bytes) -> DeviceEngagement:
        """Deserialize from CBOR format"""
        decoded = cbor2.loads(data)
        return cls(
            version=decoded.get("version", "1.0"),
            security=decoded.get("security", {}),
            device_key_info=decoded.get("deviceKeyInfo", {}),
            protocol_info=decoded.get("protocolInfo", []),
        )

    def generate_qr_code(self) -> str:
        """Generate QR code content for device engagement"""
        # QR code format: "mdoc:" + base64url-encoded CBOR
        import base64

        cbor_data = self.to_cbor()
        b64_data = base64.urlsafe_b64encode(cbor_data).decode("ascii").rstrip("=")
        return f"mdoc:{b64_data}"


@dataclass
class mDLRequest:
    """
    mDL Request structure according to ISO 18013-5 Section 8.3.2.1.2.1

    Contains the data elements requested by the mDL reader.
    """

    version: str = "1.0"
    doc_requests: list[dict[str, Any]] = field(default_factory=list)

    def add_document_request(
        self,
        doc_type: str = "org.iso.18013.5.1.mDL",
        name_spaces: dict[str, list[str]] | None = None,
        request_info: dict[str, Any] | None = None,
    ) -> None:
        """Add a document request to the mDL request"""
        if name_spaces is None:
            # Default to basic mDL namespace
            name_spaces = {
                "org.iso.18013.5.1": [
                    "family_name",
                    "given_name",
                    "birth_date",
                    "issue_date",
                    "expiry_date",
                    "issuing_country",
                    "document_number",
                ]
            }

        doc_request = {"docType": doc_type, "nameSpaces": name_spaces}

        if request_info:
            doc_request["requestInfo"] = request_info

        self.doc_requests.append(doc_request)

    def to_cbor(self) -> bytes:
        """Serialize to CBOR format"""
        return cbor2.dumps({"version": self.version, "docRequests": self.doc_requests})

    @classmethod
    def from_cbor(cls, data: bytes) -> mDLRequest:
        """Deserialize from CBOR format"""
        decoded = cbor2.loads(data)
        return cls(
            version=decoded.get("version", "1.0"), doc_requests=decoded.get("docRequests", [])
        )


@dataclass
class mDLResponse:
    """
    mDL Response structure according to ISO 18013-5 Section 8.3.2.1.2.2

    Contains the response data from the mDL holder device.
    """

    version: str = "1.0"
    documents: list[dict[str, Any]] = field(default_factory=list)
    document_errors: list[dict[str, Any]] = field(default_factory=list)
    status: int = 0  # 0 = OK

    def add_document(
        self,
        doc_type: str,
        issuer_signed: dict[str, Any],
        device_signed: dict[str, Any],
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        """Add a document to the response"""
        document = {
            "docType": doc_type,
            "issuerSigned": issuer_signed,
            "deviceSigned": device_signed,
        }

        if errors:
            document["errors"] = errors

        self.documents.append(document)

    def to_cbor(self) -> bytes:
        """Serialize to CBOR format"""
        return cbor2.dumps(
            {
                "version": self.version,
                "documents": self.documents,
                "documentErrors": self.document_errors,
                "status": self.status,
            }
        )

    @classmethod
    def from_cbor(cls, data: bytes) -> mDLResponse:
        """Deserialize from CBOR format"""
        decoded = cbor2.loads(data)
        return cls(
            version=decoded.get("version", "1.0"),
            documents=decoded.get("documents", []),
            document_errors=decoded.get("documentErrors", []),
            status=decoded.get("status", 0),
        )


class SessionManager:
    """
    Manages secure sessions according to ISO 18013-5 Section 9

    Handles session establishment, key derivation, and secure messaging.
    """

    def __init__(self):
        self.session_id: str | None = None
        self.session_key: bytes | None = None
        self.reader_key: ec.EllipticCurvePrivateKey | None = None
        self.device_key: ec.EllipticCurvePublicKey | None = None
        self.encrypted_counter = 0

    def establish_session(
        self,
        device_engagement: DeviceEngagement,
        reader_key: ec.EllipticCurvePrivateKey | None = None,
    ) -> str:
        """
        Establish a secure session with the device

        Returns the session identifier
        """
        if reader_key is None:
            # Generate ephemeral reader key
            reader_key = ec.generate_private_key(ec.SECP256R1())

        self.reader_key = reader_key
        self.session_id = str(uuid.uuid4())

        # Extract device public key from engagement
        device_key_info = device_engagement.device_key_info
        x = int.from_bytes(device_key_info[-2], "big")
        y = int.from_bytes(device_key_info[-3], "big")

        # Reconstruct device public key
        public_numbers = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1())
        self.device_key = public_numbers.public_key()

        # Perform ECDH key agreement
        shared_key = self.reader_key.exchange(ec.ECDH(), self.device_key)

        # Derive session key using HKDF
        self.session_key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=b"ISO18013-5 Session Key"
        ).derive(shared_key)

        return self.session_id

    def encrypt_message(self, plaintext: bytes) -> bytes:
        """Encrypt a message using the session key"""
        if not self.session_key:
            raise ValueError("Session not established")

        # Use AES-256-GCM as specified in ISO 18013-5
        nonce = self.encrypted_counter.to_bytes(12, "big")
        cipher = Cipher(algorithms.AES(self.session_key), modes.GCM(nonce))
        encryptor = cipher.encryptor()

        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        self.encrypted_counter += 1

        return nonce + encryptor.tag + ciphertext

    def decrypt_message(self, encrypted_data: bytes) -> bytes:
        """Decrypt a message using the session key"""
        if not self.session_key:
            raise ValueError("Session not established")

        # Extract nonce, tag, and ciphertext
        nonce = encrypted_data[:12]
        tag = encrypted_data[12:28]
        ciphertext = encrypted_data[28:]

        cipher = Cipher(algorithms.AES(self.session_key), modes.GCM(nonce, tag))
        decryptor = cipher.decryptor()

        return decryptor.update(ciphertext) + decryptor.finalize()


@dataclass
class SelectiveDisclosure:
    """
    Implements selective disclosure according to ISO 18013-5 Section 7.2.4

    Allows the mDL holder to only disclose requested information.
    """

    namespace: str
    element_identifier: str
    element_value: Any
    random: bytes = field(default_factory=lambda: uuid.uuid4().bytes)

    def create_digest_id(self) -> int:
        """Create digest ID for this data element"""
        # Hash the namespace, element identifier and random value
        h = hashlib.sha256()
        h.update(self.namespace.encode("utf-8"))
        h.update(self.element_identifier.encode("utf-8"))
        h.update(self.random)

        # Use first 4 bytes as digest ID
        return int.from_bytes(h.digest()[:4], "big")

    def create_digest(self) -> bytes:
        """Create digest for this data element"""
        # Create CBOR array [DigestID, Random, ElementIdentifier, ElementValue]
        digest_data = [
            self.create_digest_id(),
            self.random,
            self.element_identifier,
            self.element_value,
        ]

        # Hash the CBOR encoded array
        cbor_data = cbor2.dumps(digest_data)
        return hashlib.sha256(cbor_data).digest()

    def to_issuer_signed_item(self) -> dict[str, Any]:
        """Convert to IssuerSignedItem format"""
        return {
            "digestID": self.create_digest_id(),
            "random": self.random,
            "elementIdentifier": self.element_identifier,
            "elementValue": self.element_value,
        }


def create_device_engagement_qr(transport_methods: list[TransportMethod] = None) -> str:
    """
    Create a device engagement QR code

    Args:
        transport_methods: List of supported transport methods

    Returns:
        QR code string content
    """
    if transport_methods is None:
        transport_methods = [TransportMethod.BLE, TransportMethod.NFC]

    # Create protocol info for each transport method
    protocol_info = []
    for method in transport_methods:
        if method == TransportMethod.BLE:
            protocol_info.append(
                {
                    "protocolID": 1,  # BLE
                    "transportSpecificParameters": {
                        "bluetoothDeviceAddress": "00:11:22:33:44:55",
                        "bluetoothServiceUuid": "00001234-0000-1000-8000-00805f9b34fb",
                    },
                }
            )
        elif method == TransportMethod.NFC:
            protocol_info.append(
                {
                    "protocolID": 2,  # NFC
                    "transportSpecificParameters": {
                        "nfcCommandDataLength": 255,
                        "nfcResponseDataLength": 255,
                    },
                }
            )

    engagement = DeviceEngagement(protocol_info=protocol_info)
    return engagement.generate_qr_code()
