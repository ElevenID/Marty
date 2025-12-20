"""Hardware abstraction layer for RFID readers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ReaderType(Enum):
    """Supported RFID reader types."""

    PCSC = "PC/SC Compatible"
    ACR122U = "ACR122U USB NFC Reader"
    OMNIKEY = "OMNIKEY Series"
    MOCK = "Mock Reader (Testing)"


class ReaderStatus(Enum):
    """Reader connection status."""

    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    BUSY = "busy"
    ERROR = "error"


@dataclass
class ReaderInfo:
    """Information about an RFID reader."""

    name: str
    reader_type: ReaderType
    status: ReaderStatus
    atr: bytes | None = None  # Answer To Reset
    protocol: str | None = None


class ReaderInterface(ABC):
    """Abstract interface for RFID readers."""

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the reader."""

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the reader."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if reader is connected."""

    @abstractmethod
    def send_apdu(self, apdu: bytes) -> bytes:
        """Send APDU command and return response."""

    @abstractmethod
    def get_atr(self) -> bytes | None:
        """Get Answer To Reset from card."""


class MockReader(ReaderInterface):
    """Mock reader for testing purposes."""

    def __init__(self, name: str = "Mock Reader") -> None:
        self.name = name
        self.connected = False
        self.atr = bytes.fromhex("3B8F8001804F0CA000000306030001000000006A")
        self.logger = logging.getLogger(__name__)

    def connect(self) -> bool:
        """Simulate connection."""
        self.connected = True
        self.logger.info("Mock reader connected: %s", self.name)
        return True

    def disconnect(self) -> None:
        """Simulate disconnection."""
        self.connected = False
        self.logger.info("Mock reader disconnected: %s", self.name)

    def is_connected(self) -> bool:
        """Return connection status."""
        return self.connected

    def send_apdu(self, apdu: bytes) -> bytes:
        """Simulate APDU response."""
        if not self.connected:
            msg = "Reader not connected"
            raise RuntimeError(msg)

        # Simulate basic responses for common commands
        if len(apdu) >= 4:
            _cla, ins, p1, p2 = apdu[0], apdu[1], apdu[2], apdu[3]

            # SELECT commands
            if ins == 0xA4:
                return bytes([0x90, 0x00])  # Success

            # READ BINARY commands
            if ins == 0xB0:
                # Return mock data based on offset/length
                mock_data = b"MOCK_PASSPORT_DATA" * 10
                start = (p1 << 8) | p2
                length = apdu[4] if len(apdu) > 4 else 0

                if start + length <= len(mock_data):
                    return mock_data[start : start + length] + bytes([0x90, 0x00])

            # GET CHALLENGE
            if ins == 0x84:
                challenge = b"\x12\x34\x56\x78\x9a\xbc\xde\xf0"
                return challenge + bytes([0x90, 0x00])

        # Default error response
        return bytes([0x6D, 0x00])  # Instruction not supported

    def get_atr(self) -> bytes | None:
        """Return mock ATR."""
        return self.atr if self.connected else None


class ReaderManager:
    """Manages multiple RFID readers."""

    def __init__(self) -> None:
        self.readers: dict[str, ReaderInterface] = {}
        self.logger = logging.getLogger(__name__)

    def discover_readers(self) -> list[ReaderInfo]:
        """Discover available RFID readers."""
        readers = []

        try:
            # Try to import PC/SC library
            import smartcard.System

            # Get list of PC/SC readers
            reader_list = smartcard.System.readers()

            for reader in reader_list:
                reader_info = ReaderInfo(
                    name=str(reader), reader_type=ReaderType.PCSC, status=ReaderStatus.DISCONNECTED
                )
                readers.append(reader_info)

        except ImportError:
            self.logger.warning("PC/SC library not available, using mock reader")

        # Always add mock reader for testing
        mock_info = ReaderInfo(
            name="Mock Reader", reader_type=ReaderType.MOCK, status=ReaderStatus.DISCONNECTED
        )
        readers.append(mock_info)

        return readers

    def get_reader(self, name: str) -> ReaderInterface | None:
        """Get reader by name."""
        if name in self.readers:
            return self.readers[name]

        # Try to create new reader
        if name == "Mock Reader":
            reader = MockReader(name)
            self.readers[name] = reader
            return reader

        # Try PC/SC reader
        try:
            from .pcsc_reader import PCSCReader

            reader = PCSCReader(name)
            self.readers[name] = reader
        except ImportError:
            self.logger.exception("PC/SC reader not available")
            return None
        else:
            return reader

    def connect_reader(self, name: str) -> bool:
        """Connect to a specific reader."""
        reader = self.get_reader(name)
        if reader is None:
            return False

        return reader.connect()

    def disconnect_all(self) -> None:
        """Disconnect all readers."""
        for reader in self.readers.values():
            if reader.is_connected():
                reader.disconnect()
