"""APDU (Application Protocol Data Unit) Command Processing.

Implements ISO 7816-4 APDU commands for smart card communication.
Supports both short and extended APDU formats.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class APDUClass(Enum):
    """APDU instruction classes for different operations."""

    ISO7816 = 0x00  # Standard ISO 7816 commands
    GLOBAL_PLATFORM = 0x80  # Global Platform commands
    PROPRIETARY = 0xFF  # Proprietary commands


class APDUInstruction(Enum):
    """Common APDU instruction codes."""

    SELECT = 0xA4  # Select file or application
    READ_BINARY = 0xB0  # Read binary data
    READ_RECORD = 0xB2  # Read record data
    GET_CHALLENGE = 0x84  # Get challenge for authentication
    EXTERNAL_AUTHENTICATE = 0x82  # External authentication
    INTERNAL_AUTHENTICATE = 0x88  # Internal authentication
    GET_DATA = 0xCA  # Get data objects
    GENERAL_AUTHENTICATE = 0x86  # General authenticate (PACE)
    VERIFY = 0x20  # Verify PIN/password


@dataclass
class APDUCommand:
    """APDU Command structure following ISO 7816-4."""

    cla: int  # Class byte
    ins: int  # Instruction byte
    p1: int  # Parameter 1
    p2: int  # Parameter 2
    data: bytes | None = None  # Command data
    le: int | None = None  # Expected response length

    def __post_init__(self):
        """Validate APDU command parameters."""
        if not (0 <= self.cla <= 0xFF):
            msg = f"Invalid CLA: {self.cla}"
            raise ValueError(msg)
        if not (0 <= self.ins <= 0xFF):
            msg = f"Invalid INS: {self.ins}"
            raise ValueError(msg)
        if not (0 <= self.p1 <= 0xFF):
            msg = f"Invalid P1: {self.p1}"
            raise ValueError(msg)
        if not (0 <= self.p2 <= 0xFF):
            msg = f"Invalid P2: {self.p2}"
            raise ValueError(msg)

    def to_bytes(self) -> bytes:
        """Convert APDU command to byte array."""
        command = struct.pack("BBBB", self.cla, self.ins, self.p1, self.p2)

        if self.data is not None:
            # Case 3 or 4: Command with data
            lc = len(self.data)
            if lc <= 255:
                # Short APDU
                command += struct.pack("B", lc) + self.data
            else:
                # Extended APDU
                command += struct.pack(">BH", 0, lc) + self.data

        if self.le is not None:
            # Case 2 or 4: Command expecting response
            if self.le <= 255:
                command += struct.pack("B", max(0, self.le))
            elif self.data is None:
                # Case 2 extended
                command += struct.pack(">BH", 0, self.le)
            else:
                # Case 4 extended
                command += struct.pack(">H", self.le)

        return command

    @classmethod
    def select_file(cls, file_id: bytes | int, select_type: int = 0x00) -> APDUCommand:
        """Create SELECT FILE command."""
        if isinstance(file_id, int):
            file_id = struct.pack(">H", file_id)
        return cls(
            cla=0x00, ins=APDUInstruction.SELECT.value, p1=select_type, p2=0x0C, data=file_id
        )

    @classmethod
    def read_binary(cls, offset: int, length: int) -> APDUCommand:
        """Create READ BINARY command."""
        p1 = (offset >> 8) & 0xFF
        p2 = offset & 0xFF
        return cls(cla=0x00, ins=APDUInstruction.READ_BINARY.value, p1=p1, p2=p2, le=length)

    @classmethod
    def get_challenge(cls, length: int = 8) -> APDUCommand:
        """Create GET CHALLENGE command for authentication."""
        return cls(cla=0x00, ins=APDUInstruction.GET_CHALLENGE.value, p1=0x00, p2=0x00, le=length)

    @classmethod
    def mutual_authenticate(cls, payload: bytes) -> APDUCommand:
        """Create MUTUAL AUTHENTICATE (External Authenticate) command."""
        return cls(
            cla=0x00,
            ins=APDUInstruction.EXTERNAL_AUTHENTICATE.value,
            p1=0x00,
            p2=0x00,
            data=payload,
        )

    @classmethod
    def general_authenticate(cls, payload: bytes, p1: int = 0x00, p2: int = 0x00) -> APDUCommand:
        """Create GENERAL AUTHENTICATE command used by PACE (ISO 7816-4)."""

        return cls(
            cla=0x00,
            ins=APDUInstruction.GENERAL_AUTHENTICATE.value,
            p1=p1,
            p2=p2,
            data=payload,
        )


@dataclass
class APDUResponse:
    """APDU Response structure."""

    data: bytes
    sw1: int  # Status word 1
    sw2: int  # Status word 2

    @property
    def sw(self) -> int:
        """Combined status word."""
        return (self.sw1 << 8) | self.sw2

    @property
    def is_success(self) -> bool:
        """Check if response indicates success."""
        return self.sw == 0x9000

    @property
    def is_warning(self) -> bool:
        """Check if response indicates warning."""
        return self.sw1 in (98, 99)

    @property
    def is_error(self) -> bool:
        """Check if response indicates error."""
        return self.sw1 >= 0x64

    @property
    def status_description(self) -> str:
        """Get human-readable status description."""
        status_codes = {
            0x9000: "Success",
            0x6100: "Response bytes available",
            0x6281: "Part of returned data corrupted",
            0x6282: "End of file reached",
            0x6283: "Selected file invalidated",
            0x6284: "File control information not formatted",
            0x6300: "Authentication failed",
            0x6381: "File filled up by last write",
            0x6400: "Execution error",
            0x6581: "Memory failure",
            0x6700: "Wrong length",
            0x6800: "Functions in CLA not supported",
            0x6900: "Command not allowed",
            0x6A00: "Wrong parameters P1-P2",
            0x6A80: "Incorrect parameters in data field",
            0x6A81: "Function not supported",
            0x6A82: "File not found",
            0x6A83: "Record not found",
            0x6A84: "Not enough memory space",
            0x6A86: "Incorrect parameters P1-P2",
            0x6A88: "Referenced data not found",
            0x6B00: "Wrong parameters P1-P2",
            0x6C00: "Wrong Le field",
            0x6D00: "Instruction code not supported",
            0x6E00: "Class not supported",
            0x6F00: "No precise diagnosis",
        }

        # Check exact match first
        if self.sw in status_codes:
            return status_codes[self.sw]

        # Check masked matches
        masked_sw = self.sw & 0xFF00
        if masked_sw in status_codes:
            return f"{status_codes[masked_sw]} (0x{self.sw:04X})"

        return f"Unknown status: 0x{self.sw:04X}"

    @classmethod
    def from_bytes(cls, response: bytes) -> APDUResponse:
        """Create APDUResponse from byte array."""
        if len(response) < 2:
            msg = "Response too short"
            raise ValueError(msg)

        data = response[:-2]
        sw1 = response[-2]
        sw2 = response[-1]

        return cls(data=data, sw1=sw1, sw2=sw2)


class APDUProcessor:
    """High-level APDU command processor."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def build_select_application(self, aid: bytes) -> APDUCommand:
        """Build SELECT APPLICATION command."""
        return APDUCommand(
            cla=0x00,
            ins=APDUInstruction.SELECT.value,
            p1=0x04,  # Select by AID
            p2=0x0C,  # First or only occurrence
            data=aid,
        )

    def build_select_ef(self, ef_id: int) -> APDUCommand:
        """Build SELECT EF (Elementary File) command."""
        return APDUCommand.select_file(ef_id, select_type=0x02)

    def build_read_ef(self, length: int, offset: int = 0) -> list[APDUCommand]:
        """Build commands to read Elementary File data."""
        commands = []
        bytes_read = 0

        while bytes_read < length:
            chunk_size = min(255, length - bytes_read)
            command = APDUCommand.read_binary(offset + bytes_read, chunk_size)
            commands.append(command)
            bytes_read += chunk_size

        return commands

    def validate_response(self, response: APDUResponse) -> bool:
        """Validate APDU response and log any issues."""
        if response.is_success:
            return True
        if response.is_warning:
            self.logger.warning(f"APDU warning: {response.status_description}")
            return True
        self.logger.error(f"APDU error: {response.status_description}")
        return False


# Common APDU commands for passport operations
class PassportAPDU:
    """Common APDU commands for electronic passport operations."""

    # Passport application AID
    PASSPORT_AID = bytes.fromhex("A0000002471001")

    # Elementary File identifiers
    EF_COM = 0x011E  # Common Data Elements
    EF_SOD = 0x011D  # Security Object Data
    EF_DG1 = 0x0101  # Data Group 1 (MRZ)
    EF_DG2 = 0x0102  # Data Group 2 (Facial Image)
    EF_DG3 = 0x0103  # Data Group 3 (Fingerprints)
    EF_DG4 = 0x0104  # Data Group 4 (Iris Data)
    EF_DG14 = 0x010E  # Data Group 14 (Security Features)
    EF_DG15 = 0x010F  # Data Group 15 (Active Auth Public Key)

    @classmethod
    def select_passport_application(cls) -> APDUCommand:
        """Select passport application."""
        return APDUCommand(cla=0x00, ins=0xA4, p1=0x04, p2=0x0C, data=cls.PASSPORT_AID)

    @classmethod
    def select_data_group(cls, dg_number: int) -> APDUCommand:
        """Select specific data group."""
        ef_map = {
            1: cls.EF_DG1,
            2: cls.EF_DG2,
            3: cls.EF_DG3,
            4: cls.EF_DG4,
            14: cls.EF_DG14,
            15: cls.EF_DG15,
        }

        if dg_number not in ef_map:
            msg = f"Unsupported data group: {dg_number}"
            raise ValueError(msg)

        ef_id = ef_map[dg_number]
        return APDUCommand.select_file(ef_id, select_type=0x02)
