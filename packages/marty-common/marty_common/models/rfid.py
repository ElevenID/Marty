"""
RFID communication models for e-passport chip access.

Models for ISO/IEC 14443 Proximity Card Protocol used for RFID communication with e-passport chips:
- Command and Response APDUs
- RFID Protocol Layers
- Communication Parameters
- Channel Security

These models comply with ISO/IEC 14443 standard for contactless smart cards.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Any


class ISO14443Type(str, Enum):
    """ISO/IEC 14443 card types."""

    TYPE_A = "TYPE_A"
    TYPE_B = "TYPE_B"


class ISO14443Speed(IntEnum):
    """ISO/IEC 14443 communication speed."""

    SPEED_106K = 106  # 106 kbit/s
    SPEED_212K = 212  # 212 kbit/s
    SPEED_424K = 424  # 424 kbit/s
    SPEED_848K = 848  # 848 kbit/s


class ISO7816InstructionCode(IntEnum):
    """ISO/IEC 7816-4 instruction codes for APDUs."""

    SELECT = 0xA4
    READ_BINARY = 0xB0
    GET_CHALLENGE = 0x84
    EXTERNAL_AUTHENTICATE = 0x82
    INTERNAL_AUTHENTICATE = 0x88
    GET_DATA = 0xCA
    PSO = 0x2A  # Perform Security Operation
    MUTUAL_AUTHENTICATE = 0x82
    MANAGE_SECURITY_ENVIRONMENT = 0x22


class ISO7816StatusCode(IntEnum):
    """ISO/IEC 7816-4 status codes for responses."""

    SUCCESS = 0x9000
    WRONG_LENGTH = 0x6700
    SECURITY_STATUS_NOT_SATISFIED = 0x6982
    AUTHENTICATION_METHOD_BLOCKED = 0x6983
    CONDITIONS_NOT_SATISFIED = 0x6985
    INCORRECT_PARAMETERS = 0x6A80
    FILE_NOT_FOUND = 0x6A82
    INCORRECT_P1P2 = 0x6A86
    WRONG_DATA = 0x6A80
    INS_NOT_SUPPORTED = 0x6D00
    CLASS_NOT_SUPPORTED = 0x6E00


@dataclass
class APDU:
    """Abstract base class for Application Protocol Data Units (APDUs)."""

    raw_bytes: bytearray | None = None

    def to_bytes(self) -> bytearray:
        """Convert to byte array."""
        if self.raw_bytes:
            return self.raw_bytes
        return bytearray()


@dataclass
class CommandAPDU(APDU):
    """Command APDU according to ISO/IEC 7816-4."""

    cla: int  # Class byte
    ins: int  # Instruction byte
    p1: int  # Parameter 1
    p2: int  # Parameter 2
    data: bytearray | None = None  # Command data
    le: int | None = None  # Expected response length

    def __post_init__(self):
        """Compute raw_bytes from fields if not provided."""
        if not self.raw_bytes:
            # Construct APDU from components
            self.raw_bytes = bytearray([self.cla, self.ins, self.p1, self.p2])

            if self.data:
                self.raw_bytes.append(len(self.data))
                self.raw_bytes.extend(self.data)

            if self.le is not None:
                if not self.data:
                    # If no data, we need a 0 for Lc
                    self.raw_bytes.append(0)
                self.raw_bytes.append(self.le)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "cla": self.cla,
            "ins": self.ins,
            "p1": self.p1,
            "p2": self.p2,
        }

        if self.data:
            result["data"] = base64.b64encode(self.data).decode("ascii")

        if self.le is not None:
            result["le"] = self.le

        result["rawBytes"] = base64.b64encode(self.raw_bytes).decode("ascii")

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CommandAPDU:
        """Create CommandAPDU from dictionary."""
        command = cls(
            cla=data["cla"], ins=data["ins"], p1=data["p1"], p2=data["p2"], le=data.get("le")
        )

        if "data" in data:
            command.data = bytearray(base64.b64decode(data["data"]))

        if "rawBytes" in data:
            command.raw_bytes = bytearray(base64.b64decode(data["rawBytes"]))

        return command

    @classmethod
    def select_file(cls, file_id: bytes) -> CommandAPDU:
        """Create a SELECT FILE command APDU."""
        return cls(
            cla=0x00,
            ins=ISO7816InstructionCode.SELECT,
            p1=0x02,  # Select by File ID
            p2=0x0C,  # First occurrence, return no FCI
            data=bytearray(file_id),
        )

    @classmethod
    def read_binary(cls, offset: int, length: int) -> CommandAPDU:
        """Create a READ BINARY command APDU."""
        return cls(
            cla=0x00,
            ins=ISO7816InstructionCode.READ_BINARY,
            p1=(offset >> 8) & 0xFF,  # High byte of offset
            p2=offset & 0xFF,  # Low byte of offset
            le=length,
        )

    @classmethod
    def get_challenge(cls, length: int) -> CommandAPDU:
        """Create a GET CHALLENGE command APDU."""
        return cls(cla=0x00, ins=ISO7816InstructionCode.GET_CHALLENGE, p1=0x00, p2=0x00, le=length)


@dataclass
class ResponseAPDU(APDU):
    """Response APDU according to ISO/IEC 7816-4."""

    data: bytearray | None = None  # Response data
    sw1: int = 0x90  # Status Word 1
    sw2: int = 0x00  # Status Word 2

    def __post_init__(self):
        """Compute sw and data from raw bytes if provided."""
        if self.raw_bytes and not self.data and len(self.raw_bytes) >= 2:
            self.sw1 = self.raw_bytes[-2]
            self.sw2 = self.raw_bytes[-1]
            if len(self.raw_bytes) > 2:
                self.data = self.raw_bytes[:-2]

    def get_status_word(self) -> int:
        """Get the status word as a 16-bit integer."""
        return (self.sw1 << 8) | self.sw2

    def is_success(self) -> bool:
        """Check if response indicates success."""
        return self.get_status_word() == ISO7816StatusCode.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {"sw1": self.sw1, "sw2": self.sw2, "statusWord": self.get_status_word()}

        if self.data:
            result["data"] = base64.b64encode(self.data).decode("ascii")

        if self.raw_bytes:
            result["rawBytes"] = base64.b64encode(self.raw_bytes).decode("ascii")

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResponseAPDU:
        """Create ResponseAPDU from dictionary."""
        response = cls(sw1=data["sw1"], sw2=data["sw2"])

        if "data" in data:
            response.data = bytearray(base64.b64decode(data["data"]))

        if "rawBytes" in data:
            response.raw_bytes = bytearray(base64.b64decode(data["rawBytes"]))

        return response

    @classmethod
    def from_bytes(cls, data: bytearray) -> ResponseAPDU:
        """Create ResponseAPDU from raw bytes."""
        return cls(raw_bytes=data)


@dataclass
class ISO14443Parameters:
    """ISO/IEC 14443 connection parameters."""

    card_type: ISO14443Type
    speed: ISO14443Speed
    atqa: bytearray | None = None  # Answer to Request Type A
    atqb: bytearray | None = None  # Answer to Request Type B
    uid: bytearray | None = None  # Unique Identifier
    ats: bytearray | None = None  # Answer to Select

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {"cardType": self.card_type.value, "speed": self.speed.value}

        if self.atqa:
            result["atqa"] = base64.b64encode(self.atqa).decode("ascii")

        if self.atqb:
            result["atqb"] = base64.b64encode(self.atqb).decode("ascii")

        if self.uid:
            result["uid"] = base64.b64encode(self.uid).decode("ascii")

        if self.ats:
            result["ats"] = base64.b64encode(self.ats).decode("ascii")

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ISO14443Parameters:
        """Create ISO14443Parameters from dictionary."""
        params = cls(card_type=ISO14443Type(data["cardType"]), speed=ISO14443Speed(data["speed"]))

        if "atqa" in data:
            params.atqa = bytearray(base64.b64decode(data["atqa"]))

        if "atqb" in data:
            params.atqb = bytearray(base64.b64decode(data["atqb"]))

        if "uid" in data:
            params.uid = bytearray(base64.b64decode(data["uid"]))

        if "ats" in data:
            params.ats = bytearray(base64.b64decode(data["ats"]))

        return params


@dataclass
class SecureMessagingContext:
    """Context for secure messaging according to ISO/IEC 7816-4."""

    encryption_key: bytearray
    mac_key: bytearray
    send_sequence_counter: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "encryptionKey": base64.b64encode(self.encryption_key).decode("ascii"),
            "macKey": base64.b64encode(self.mac_key).decode("ascii"),
            "sendSequenceCounter": self.send_sequence_counter,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SecureMessagingContext:
        """Create SecureMessagingContext from dictionary."""
        return cls(
            encryption_key=bytearray(base64.b64decode(data["encryptionKey"])),
            mac_key=bytearray(base64.b64decode(data["macKey"])),
            send_sequence_counter=data.get("sendSequenceCounter", 0),
        )

    def protect_command(self, command: CommandAPDU) -> CommandAPDU:
        """
        Apply secure messaging to a command APDU (stub implementation).

        In a real implementation, this would apply encryption and MAC
        according to the secure messaging protocol.
        """
        # This would be a complex implementation applying secure messaging
        # For now, just return the original command
        self.send_sequence_counter += 1
        return command

    def unprotect_response(self, response: ResponseAPDU) -> ResponseAPDU:
        """
        Remove secure messaging from a response APDU (stub implementation).

        In a real implementation, this would verify MAC and decrypt
        according to the secure messaging protocol.
        """
        # This would be a complex implementation removing secure messaging
        # For now, just return the original response
        return response


@dataclass
class RFIDSessionInfo:
    """Information about an active RFID session."""

    reader_id: str
    connection_params: ISO14443Parameters
    secure_messaging: SecureMessagingContext | None = None
    is_active: bool = True
    secure_channel_established: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "readerId": self.reader_id,
            "connectionParams": self.connection_params.to_dict(),
            "isActive": self.is_active,
            "secureChannelEstablished": self.secure_channel_established,
        }

        if self.secure_messaging:
            result["secureMessaging"] = self.secure_messaging.to_dict()

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RFIDSessionInfo:
        """Create RFIDSessionInfo from dictionary."""
        session = cls(
            reader_id=data["readerId"],
            connection_params=ISO14443Parameters.from_dict(data["connectionParams"]),
            is_active=data.get("isActive", True),
            secure_channel_established=data.get("secureChannelEstablished", False),
        )

        if "secureMessaging" in data:
            session.secure_messaging = SecureMessagingContext.from_dict(data["secureMessaging"])

        return session
