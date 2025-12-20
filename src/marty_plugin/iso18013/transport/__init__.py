"""
Transport Layer Implementation for ISO/IEC 18013-5

This module implements the transport layer protocols for mDL transactions:
- BLE (Bluetooth Low Energy) transport
- NFC (Near Field Communication) transport
- HTTP/HTTPS transport for online flows
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from .core import DeviceEngagement, mDLRequest, mDLResponse

logger = logging.getLogger(__name__)


class TransportState(Enum):
    """Transport connection states"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ENGAGED = "engaged"
    ERROR = "error"


class TransportError(Exception):
    """Base exception for transport errors"""

    pass


class BLEError(TransportError):
    """BLE-specific errors"""

    pass


class NFCError(TransportError):
    """NFC-specific errors"""

    pass


class HTTPError(TransportError):
    """HTTP-specific errors"""

    pass


@dataclass
class TransportMessage:
    """Generic transport message wrapper"""

    data: bytes
    message_type: str
    timestamp: float
    source: str
    destination: str | None = None


class TransportInterface(ABC):
    """Abstract base class for all transport implementations"""

    def __init__(self):
        self.state = TransportState.DISCONNECTED
        self.message_handlers: dict[str, Callable] = {}

    @abstractmethod
    async def connect(self) -> bool:
        """Establish transport connection"""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close transport connection"""
        pass

    @abstractmethod
    async def send_message(self, message: bytes, message_type: str = "data") -> bool:
        """Send a message via this transport"""
        pass

    @abstractmethod
    async def receive_message(self, timeout: float = 30.0) -> TransportMessage | None:
        """Receive a message via this transport"""
        pass

    def register_handler(self, message_type: str, handler: Callable) -> None:
        """Register a message handler for a specific message type"""
        self.message_handlers[message_type] = handler

    async def handle_message(self, message: TransportMessage) -> None:
        """Handle received message using registered handlers"""
        handler = self.message_handlers.get(message.message_type)
        if handler:
            await handler(message)
        else:
            logger.warning(f"No handler for message type: {message.message_type}")


class BLETransport(TransportInterface):
    """
    Bluetooth Low Energy transport implementation

    Implements ISO 18013-5 Section 8.3.3.1 (BLE data retrieval)
    """

    # BLE service UUID for mDL (as defined in ISO 18013-5)
    MDL_SERVICE_UUID = "0000FFF0-0000-1000-8000-00805F9B34FB"

    # Characteristic UUIDs
    STATE_CHARACTERISTIC_UUID = "0000FFF1-0000-1000-8000-00805F9B34FB"
    CLIENT2SERVER_CHARACTERISTIC_UUID = "0000FFF2-0000-1000-8000-00805F9B34FB"
    SERVER2CLIENT_CHARACTERISTIC_UUID = "0000FFF3-0000-1000-8000-00805F9B34FB"
    IDENT_CHARACTERISTIC_UUID = "0000FFF4-0000-1000-8000-00805F9B34FB"
    L2CAP_CHARACTERISTIC_UUID = "0000FFF5-0000-1000-8000-00805F9B34FB"

    def __init__(self, device_address: str | None = None):
        super().__init__()
        self.device_address = device_address
        self.client = None  # BLE client placeholder
        self.characteristics = {}
        self.mtu_size = 512  # Default MTU size

    async def connect(self) -> bool:
        """Connect to BLE device"""
        try:
            self.state = TransportState.CONNECTING
            logger.info(f"Connecting to BLE device: {self.device_address}")

            # TODO: Implement actual BLE connection using bleak or similar
            # For now, simulate successful connection
            await asyncio.sleep(0.1)

            self.state = TransportState.CONNECTED
            logger.info("BLE connection established")
            return True

        except Exception as e:
            logger.error(f"BLE connection failed: {e}")
            self.state = TransportState.ERROR
            raise BLEError(f"Connection failed: {e}")

    async def disconnect(self) -> None:
        """Disconnect from BLE device"""
        try:
            if self.client:
                # TODO: Implement actual BLE disconnection
                pass

            self.state = TransportState.DISCONNECTED
            logger.info("BLE disconnected")

        except Exception as e:
            logger.error(f"BLE disconnection error: {e}")

    async def send_message(self, message: bytes, message_type: str = "data") -> bool:
        """Send message via BLE"""
        try:
            if self.state != TransportState.CONNECTED:
                raise BLEError("Not connected")

            # Fragment message if larger than MTU
            fragments = self._fragment_message(message)

            for fragment in fragments:
                # TODO: Send fragment via CLIENT2SERVER characteristic
                logger.debug(f"Sending BLE fragment: {len(fragment)} bytes")
                await asyncio.sleep(0.01)  # Simulate transmission delay

            logger.info(f"Sent BLE message: {len(message)} bytes in {len(fragments)} fragments")
            return True

        except Exception as e:
            logger.error(f"BLE send error: {e}")
            raise BLEError(f"Send failed: {e}")

    async def receive_message(self, timeout: float = 30.0) -> TransportMessage | None:
        """Receive message via BLE"""
        try:
            if self.state != TransportState.CONNECTED:
                return None

            # TODO: Implement actual BLE message reception
            # For now, simulate message reception
            await asyncio.sleep(0.1)

            # Simulate received message
            import time

            simulated_data = b"simulated BLE response"

            return TransportMessage(
                data=simulated_data,
                message_type="mdl_response",
                timestamp=time.time(),
                source="ble_device",
            )

        except Exception as e:
            logger.error(f"BLE receive error: {e}")
            return None

    def _fragment_message(self, message: bytes) -> list[bytes]:
        """Fragment message according to BLE MTU size"""
        max_payload = self.mtu_size - 3  # Account for BLE headers
        fragments = []

        for i in range(0, len(message), max_payload):
            fragment = message[i : i + max_payload]
            fragments.append(fragment)

        return fragments

    async def scan_for_devices(self, timeout: float = 10.0) -> list[dict[str, Any]]:
        """Scan for mDL-capable BLE devices"""
        try:
            logger.info("Scanning for mDL BLE devices...")

            # TODO: Implement actual BLE scanning
            # For now, return simulated devices
            await asyncio.sleep(1.0)

            return [
                {
                    "address": "AA:BB:CC:DD:EE:FF",
                    "name": "mDL Holder Device",
                    "rssi": -65,
                    "services": [self.MDL_SERVICE_UUID],
                }
            ]

        except Exception as e:
            logger.error(f"BLE scan error: {e}")
            return []


class NFCTransport(TransportInterface):
    """
    Near Field Communication transport implementation

    Implements ISO 18013-5 Section 8.3.3.2 (NFC data retrieval)
    """

    # NFC application identifier for mDL
    MDL_AID = bytes.fromhex("A0000002480400")

    def __init__(self, reader_id: str | None = None):
        super().__init__()
        self.reader_id = reader_id
        self.reader = None  # NFC reader placeholder
        self.max_command_length = 255
        self.max_response_length = 255

    async def connect(self) -> bool:
        """Connect to NFC reader"""
        try:
            self.state = TransportState.CONNECTING
            logger.info(f"Connecting to NFC reader: {self.reader_id}")

            # TODO: Implement actual NFC reader connection
            await asyncio.sleep(0.1)

            self.state = TransportState.CONNECTED
            logger.info("NFC reader connected")
            return True

        except Exception as e:
            logger.error(f"NFC connection failed: {e}")
            self.state = TransportState.ERROR
            raise NFCError(f"Connection failed: {e}")

    async def disconnect(self) -> None:
        """Disconnect from NFC reader"""
        try:
            if self.reader:
                # TODO: Implement actual NFC disconnection
                pass

            self.state = TransportState.DISCONNECTED
            logger.info("NFC disconnected")

        except Exception as e:
            logger.error(f"NFC disconnection error: {e}")

    async def send_message(self, message: bytes, message_type: str = "data") -> bool:
        """Send message via NFC"""
        try:
            if self.state != TransportState.CONNECTED:
                raise NFCError("Not connected")

            # Fragment message if needed
            fragments = self._fragment_message(message)

            for fragment in fragments:
                # TODO: Send APDU command
                logger.debug(f"Sending NFC APDU: {len(fragment)} bytes")
                await asyncio.sleep(0.01)

            logger.info(f"Sent NFC message: {len(message)} bytes")
            return True

        except Exception as e:
            logger.error(f"NFC send error: {e}")
            raise NFCError(f"Send failed: {e}")

    async def receive_message(self, timeout: float = 30.0) -> TransportMessage | None:
        """Receive message via NFC"""
        try:
            if self.state != TransportState.CONNECTED:
                return None

            # TODO: Implement actual NFC message reception
            await asyncio.sleep(0.1)

            # Simulate received message
            import time

            simulated_data = b"simulated NFC response"

            return TransportMessage(
                data=simulated_data,
                message_type="mdl_response",
                timestamp=time.time(),
                source="nfc_card",
            )

        except Exception as e:
            logger.error(f"NFC receive error: {e}")
            return None

    def _fragment_message(self, message: bytes) -> list[bytes]:
        """Fragment message according to NFC constraints"""
        max_payload = min(self.max_command_length - 5, 250)  # Account for APDU headers
        fragments = []

        for i in range(0, len(message), max_payload):
            fragment = message[i : i + max_payload]
            fragments.append(fragment)

        return fragments

    async def select_mdl_application(self) -> bool:
        """Select the mDL application on the NFC card"""
        try:
            # TODO: Send SELECT command with mDL AID
            logger.info("Selecting mDL application")
            await asyncio.sleep(0.1)
            return True

        except Exception as e:
            logger.error(f"mDL application selection failed: {e}")
            return False


class HTTPSTransport(TransportInterface):
    """
    HTTPS transport implementation for ISO 18013-7 online flows

    Implements ISO/IEC 18013-7 relying party interactions
    """

    def __init__(self, base_url: str, verify_ssl: bool = True):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl
        self.session = None  # HTTP session placeholder
        self.access_token: str | None = None

    async def connect(self) -> bool:
        """Establish HTTPS connection"""
        try:
            self.state = TransportState.CONNECTING
            logger.info(f"Connecting to HTTPS endpoint: {self.base_url}")

            # TODO: Implement actual HTTPS session establishment
            await asyncio.sleep(0.1)

            self.state = TransportState.CONNECTED
            logger.info("HTTPS connection established")
            return True

        except Exception as e:
            logger.error(f"HTTPS connection failed: {e}")
            self.state = TransportState.ERROR
            raise HTTPError(f"Connection failed: {e}")

    async def disconnect(self) -> None:
        """Close HTTPS connection"""
        try:
            if self.session:
                # TODO: Close HTTP session
                pass

            self.state = TransportState.DISCONNECTED
            logger.info("HTTPS disconnected")

        except Exception as e:
            logger.error(f"HTTPS disconnection error: {e}")

    async def send_message(self, message: bytes, message_type: str = "data") -> bool:
        """Send message via HTTPS"""
        try:
            if self.state != TransportState.CONNECTED:
                raise HTTPError("Not connected")

            # TODO: Send HTTP POST request
            logger.info(f"Sending HTTPS message: {len(message)} bytes")
            await asyncio.sleep(0.1)

            return True

        except Exception as e:
            logger.error(f"HTTPS send error: {e}")
            raise HTTPError(f"Send failed: {e}")

    async def receive_message(self, timeout: float = 30.0) -> TransportMessage | None:
        """Receive message via HTTPS"""
        try:
            if self.state != TransportState.CONNECTED:
                return None

            # TODO: Receive HTTP response
            await asyncio.sleep(0.1)

            # Simulate received message
            import time

            simulated_data = b"simulated HTTPS response"

            return TransportMessage(
                data=simulated_data,
                message_type="mdl_response",
                timestamp=time.time(),
                source="https_server",
            )

        except Exception as e:
            logger.error(f"HTTPS receive error: {e}")
            return None

    async def authenticate(self, credentials: dict[str, Any]) -> bool:
        """Authenticate with the relying party"""
        try:
            logger.info("Authenticating with relying party")

            # TODO: Implement OAuth 2.0 or similar authentication
            await asyncio.sleep(0.1)

            self.access_token = "simulated_access_token"
            return True

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    async def initiate_presentation_request(self, presentation_definition: dict[str, Any]) -> str:
        """Initiate a presentation request according to ISO 18013-7"""
        try:
            logger.info("Initiating presentation request")

            # TODO: Send presentation request to holder's wallet
            await asyncio.sleep(0.1)

            # Return session ID for tracking the presentation
            return "presentation_session_123"

        except Exception as e:
            logger.error(f"Presentation request failed: {e}")
            raise HTTPError(f"Presentation request failed: {e}")


def create_transport(transport_type: str, **kwargs) -> TransportInterface:
    """
    Factory function to create transport instances

    Args:
        transport_type: Type of transport ("ble", "nfc", "https")
        **kwargs: Transport-specific configuration

    Returns:
        Transport instance
    """
    transport_type = transport_type.lower()

    if transport_type == "ble":
        return BLETransport(device_address=kwargs.get("device_address"))
    elif transport_type == "nfc":
        return NFCTransport(reader_id=kwargs.get("reader_id"))
    elif transport_type == "https":
        return HTTPSTransport(
            base_url=kwargs["base_url"], verify_ssl=kwargs.get("verify_ssl", True)
        )
    else:
        raise ValueError(f"Unsupported transport type: {transport_type}")


async def discover_devices(transport_types: list[str] = None) -> dict[str, list[dict[str, Any]]]:
    """
    Discover mDL-capable devices across multiple transport types

    Args:
        transport_types: List of transport types to scan ("ble", "nfc")

    Returns:
        Dictionary mapping transport type to list of discovered devices
    """
    if transport_types is None:
        transport_types = ["ble", "nfc"]

    devices = {}

    for transport_type in transport_types:
        try:
            if transport_type == "ble":
                ble_transport = BLETransport()
                devices["ble"] = await ble_transport.scan_for_devices()
            elif transport_type == "nfc":
                # NFC discovery would be event-driven when card is presented
                devices["nfc"] = []

        except Exception as e:
            logger.error(f"Device discovery failed for {transport_type}: {e}")
            devices[transport_type] = []

    return devices
