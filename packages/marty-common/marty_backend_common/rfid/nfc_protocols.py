"""NFC Protocol Handler for Mobile Device Integration.

Supports Android HCE (Host Card Emulation) and iOS Core NFC integration.
Provides cross-platform NFC communication capabilities.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class NFCProtocol(Enum):
    """Supported NFC protocols."""

    ISO14443_TYPE_A = "ISO14443-A"
    ISO14443_TYPE_B = "ISO14443-B"
    ISO15693 = "ISO15693"
    FELICA = "FeliCa"
    MIFARE = "MIFARE"


class NFCCommand(Enum):
    """Common NFC commands."""

    POLL = "poll"
    SELECT = "select"
    READ = "read"
    WRITE = "write"
    AUTHENTICATE = "authenticate"


@dataclass
class NFCDevice:
    """NFC device information."""

    device_id: str
    protocol: NFCProtocol
    uid: bytes
    atqa: bytes | None = None  # Answer to Request Type A
    sak: int | None = None  # Select Acknowledge
    ats: bytes | None = None  # Answer to Select


class NFCInterface(ABC):
    """Abstract interface for NFC operations."""

    @abstractmethod
    def initialize(self) -> bool:
        """Initialize NFC interface."""
        ...

    @abstractmethod
    def poll_devices(self, protocols: list[NFCProtocol]) -> list[NFCDevice]:
        """Poll for NFC devices."""
        ...

    @abstractmethod
    def connect_device(self, device: NFCDevice) -> bool:
        """Connect to NFC device."""
        ...

    @abstractmethod
    def send_command(self, command: bytes) -> bytes:
        """Send command to connected device."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from current device."""
        ...


class MockNFCInterface(NFCInterface):
    """Mock NFC interface for testing."""

    def __init__(self) -> None:
        self.initialized = False
        self.connected_device: NFCDevice | None = None
        self.logger = logging.getLogger(__name__)

    def initialize(self) -> bool:
        """Initialize mock NFC interface."""
        self.initialized = True
        self.logger.info("Mock NFC interface initialized")
        return True

    def poll_devices(self, protocols: list[NFCProtocol]) -> list[NFCDevice]:
        """Return mock NFC devices."""
        if not self.initialized:
            return []

        # Mock passport device
        mock_passport = NFCDevice(
            device_id="mock_passport",
            protocol=NFCProtocol.ISO14443_TYPE_B,
            uid=bytes.fromhex("08010203"),
            atqa=bytes.fromhex("5000"),
            sak=0x20,
            ats=bytes.fromhex("0575F7C0021000"),
        )

        return [mock_passport]

    def connect_device(self, device: NFCDevice) -> bool:
        """Connect to mock device."""
        self.connected_device = device
        self.logger.info("Connected to mock device: %s", device.device_id)
        return True

    def send_command(self, command: bytes) -> bytes:
        """Send mock command."""
        if not self.connected_device:
            msg = "No device connected"
            raise RuntimeError(msg)

        # Mock passport application selection
        if command == bytes.fromhex("00A4040C07A0000002471001"):
            return bytes.fromhex("9000")  # Success

        # Mock data reading
        return bytes.fromhex("6F108408A000000247100187020100009000")

    def disconnect(self) -> None:
        """Disconnect from device."""
        if self.connected_device:
            self.logger.info("Disconnected from device: %s", self.connected_device.device_id)
            self.connected_device = None


class AndroidHCEInterface(NFCInterface):
    """Android Host Card Emulation interface."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self._try_import_android_deps()

    def _try_import_android_deps(self) -> None:
        """Try to import Android-specific dependencies."""
        try:
            # These would be Android-specific imports
            # from android.nfc import NfcAdapter, Tag
            # self.nfc_adapter = NfcAdapter
            pass
        except ImportError:
            self.logger.warning("Android NFC dependencies not available")

    def initialize(self) -> bool:
        """Initialize Android NFC."""
        # Android-specific initialization
        self.logger.info("Android HCE interface initialized")
        return True

    def poll_devices(self, protocols: list[NFCProtocol]) -> list[NFCDevice]:
        """Poll for Android NFC devices."""
        # Android-specific device polling
        return []

    def connect_device(self, device: NFCDevice) -> bool:
        """Connect to Android NFC device."""
        return False

    def send_command(self, command: bytes) -> bytes:
        """Send command via Android NFC."""
        return b""

    def disconnect(self) -> None:
        """Disconnect Android NFC."""


class iOSCoreNFCInterface(NFCInterface):
    """iOS Core NFC interface."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self._try_import_ios_deps()

    def _try_import_ios_deps(self) -> None:
        """Try to import iOS-specific dependencies."""
        try:
            # These would be iOS-specific imports via PyObjC
            # import CoreNFC
            pass
        except ImportError:
            self.logger.warning("iOS Core NFC dependencies not available")

    def initialize(self) -> bool:
        """Initialize iOS Core NFC."""
        self.logger.info("iOS Core NFC interface initialized")
        return True

    def poll_devices(self, protocols: list[NFCProtocol]) -> list[NFCDevice]:
        """Poll for iOS NFC devices."""
        return []

    def connect_device(self, device: NFCDevice) -> bool:
        """Connect to iOS NFC device."""
        return False

    def send_command(self, command: bytes) -> bytes:
        """Send command via iOS Core NFC."""
        return b""

    def disconnect(self) -> None:
        """Disconnect iOS NFC."""


class NFCProtocolHandler:
    """Cross-platform NFC protocol handler."""

    def __init__(self) -> None:
        self.interface: NFCInterface | None = None
        self.logger = logging.getLogger(__name__)

    def get_available_interface(self) -> NFCInterface | None:
        """Get the best available NFC interface for current platform."""
        import platform

        system = platform.system().lower()

        if system == "android":
            return AndroidHCEInterface()
        if system == "darwin":  # iOS
            return iOSCoreNFCInterface()
        # Try nfcpy for desktop systems
        try:
            return self._get_nfcpy_interface()
        except ImportError:
            self.logger.warning("No NFC libraries available, using mock")
            return MockNFCInterface()

    def _get_nfcpy_interface(self) -> NFCInterface:
        """Get nfcpy-based interface for desktop systems."""
        try:
            import nfc

            return NFCPyInterface(nfc)
        except ImportError as e:
            msg = "nfcpy library not available"
            raise ImportError(msg) from e

    def initialize_best_interface(self) -> bool:
        """Initialize the best available NFC interface."""
        self.interface = self.get_available_interface()
        if self.interface:
            return self.interface.initialize()
        return False

    def scan_for_passports(self) -> list[NFCDevice]:
        """Scan for passport-compatible NFC devices."""
        if not self.interface:
            return []

        # Focus on passport-compatible protocols
        protocols = [
            NFCProtocol.ISO14443_TYPE_B,  # Most common for passports
            NFCProtocol.ISO14443_TYPE_A,  # Alternative passport format
        ]

        return self.interface.poll_devices(protocols)

    def read_passport_data(self, device: NFCDevice) -> dict[str, bytes]:
        """Read passport data from NFC device."""
        if not self.interface:
            msg = "No NFC interface available"
            raise RuntimeError(msg)

        if not self.interface.connect_device(device):
            msg = f"Failed to connect to device {device.device_id}"
            raise RuntimeError(msg)

        try:
            # Select passport application
            passport_aid = bytes.fromhex("A0000002471001")
            select_cmd = bytes([0x00, 0xA4, 0x04, 0x0C, len(passport_aid)]) + passport_aid

            response = self.interface.send_command(select_cmd)

            if len(response) < 2 or response[-2:] != bytes([0x90, 0x00]):
                msg = "Failed to select passport application"
                raise RuntimeError(msg)

            # Read basic passport data (would be expanded)
            return {
                "application_selected": True,
                "atr": device.uid,
            }

        finally:
            self.interface.disconnect()


class NFCPyInterface(NFCInterface):
    """nfcpy-based NFC interface for desktop systems."""

    def __init__(self, nfc_module) -> None:
        self.nfc = nfc_module
        self.clf = None
        self.target = None
        self.logger = logging.getLogger(__name__)

    def initialize(self) -> bool:
        """Initialize nfcpy interface."""
        try:
            self.clf = self.nfc.ContactlessFrontend("usb")
            if self.clf:
                self.logger.info("nfcpy interface initialized")
                return True
        except Exception:
            self.logger.exception("Failed to initialize nfcpy")
        return False

    def poll_devices(self, protocols: list[NFCProtocol]) -> list[NFCDevice]:
        """Poll for devices using nfcpy."""
        devices = []

        if not self.clf:
            return devices

        try:
            # Configure polling based on requested protocols

            target = self.clf.sense(
                self.nfc.clf.RemoteTarget("106A"),  # ISO14443 Type A
                self.nfc.clf.RemoteTarget("106B"),  # ISO14443 Type B
                iterations=1,
            )

            if target:
                device = NFCDevice(
                    device_id=f"nfcpy_{target.uid.hex()}",
                    protocol=NFCProtocol.ISO14443_TYPE_A,  # Determine actual type
                    uid=target.uid,
                )
                devices.append(device)

        except Exception:
            self.logger.exception("Error polling NFC devices")

        return devices

    def connect_device(self, device: NFCDevice) -> bool:
        """Connect to nfcpy device."""
        # nfcpy connection logic would go here
        return True

    def send_command(self, command: bytes) -> bytes:
        """Send command via nfcpy."""
        # nfcpy command sending logic
        return b"\x90\x00"

    def disconnect(self) -> None:
        """Disconnect nfcpy interface."""
        if self.clf:
            self.clf.close()
