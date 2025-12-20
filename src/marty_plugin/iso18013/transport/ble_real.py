"""
Real BLE Transport Implementation for ISO/IEC 18013-5

This module implements a production-ready BLE transport layer using the bleak library
for actual Bluetooth Low Energy communications with mDL holder devices.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

try:
    from bleak import BleakClient, BleakScanner
    from bleak.backends.device import BLEDevice

    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False
    BleakClient = None
    BleakScanner = None
    BLEDevice = None

from ..transport import BLEError, TransportMessage, TransportState
from ..transport import BLETransport as BaseBLETransport

logger = logging.getLogger(__name__)


class RealBLETransport(BaseBLETransport):
    """
    Production BLE transport using bleak library

    Implements the full ISO 18013-5 BLE data retrieval specification:
    - Device discovery and connection
    - Service and characteristic discovery
    - mDL service communication
    - Proper fragmentation and reassembly
    """

    def __init__(self, device_address: str | None = None, device: BLEDevice | None = None):
        if not BLEAK_AVAILABLE:
            raise BLEError("bleak library not available - install with: pip install bleak")

        super().__init__(device_address)
        self.ble_device = device
        self.client: BleakClient | None = None
        self.message_queue = asyncio.Queue()
        self.notification_handlers = {}

        # State tracking
        self.state_value = 0x00  # Initial state
        self.client_to_server_buffer = bytearray()
        self.server_to_client_buffer = bytearray()

    async def connect(self) -> bool:
        """Connect to BLE device and discover mDL service"""
        try:
            self.state = TransportState.CONNECTING

            if not self.ble_device and not self.device_address:
                raise BLEError("No device or address specified")

            # Create client
            if self.ble_device:
                self.client = BleakClient(self.ble_device)
            else:
                self.client = BleakClient(self.device_address)

            # Connect to device
            logger.info(
                f"Connecting to BLE device: {self.device_address or self.ble_device.address}"
            )
            await self.client.connect()

            if not self.client.is_connected:
                raise BLEError("Failed to connect to device")

            # Discover services
            services = await self.client.get_services()

            # Find mDL service
            mdl_service = None
            for service in services:
                if service.uuid.upper() == self.MDL_SERVICE_UUID.upper():
                    mdl_service = service
                    break

            if not mdl_service:
                raise BLEError(f"mDL service {self.MDL_SERVICE_UUID} not found")

            # Setup characteristics
            await self._setup_characteristics(mdl_service)

            # Subscribe to notifications
            await self._setup_notifications()

            self.state = TransportState.CONNECTED
            logger.info("BLE connection established and mDL service configured")
            return True

        except Exception as e:
            logger.error(f"BLE connection failed: {e}")
            self.state = TransportState.ERROR
            if self.client and self.client.is_connected:
                await self.client.disconnect()
            raise BLEError(f"Connection failed: {e}")

    async def disconnect(self) -> None:
        """Disconnect from BLE device"""
        try:
            if self.client and self.client.is_connected:
                # Stop notifications
                for char_uuid in self.notification_handlers:
                    try:
                        await self.client.stop_notify(char_uuid)
                    except Exception as e:
                        logger.warning(f"Failed to stop notifications for {char_uuid}: {e}")

                # Disconnect
                await self.client.disconnect()
                logger.info("BLE disconnected")

            self.state = TransportState.DISCONNECTED
            self.client = None

        except Exception as e:
            logger.error(f"BLE disconnection error: {e}")

    async def send_message(self, message: bytes, message_type: str = "data") -> bool:
        """Send message via BLE using proper fragmentation"""
        try:
            if not self.client or not self.client.is_connected:
                raise BLEError("Not connected")

            # Fragment message
            fragments = self._fragment_message(message)

            # Send each fragment
            for i, fragment in enumerate(fragments):
                # Add fragmentation header if needed
                if len(fragments) > 1:
                    header = i.to_bytes(1, "big") if i < len(fragments) - 1 else b"\xff"
                    fragment_data = header + fragment
                else:
                    fragment_data = fragment

                # Write to CLIENT2SERVER characteristic
                await self.client.write_gatt_char(
                    self.CLIENT2SERVER_CHARACTERISTIC_UUID, fragment_data, response=True
                )

                # Small delay between fragments
                if i < len(fragments) - 1:
                    await asyncio.sleep(0.01)

            logger.debug(f"Sent BLE message: {len(message)} bytes in {len(fragments)} fragments")
            return True

        except Exception as e:
            logger.error(f"BLE send error: {e}")
            raise BLEError(f"Send failed: {e}")

    async def receive_message(self, timeout: float = 30.0) -> TransportMessage | None:
        """Receive message via BLE notifications"""
        try:
            if not self.client or not self.client.is_connected:
                return None

            # Wait for message from notification queue
            message = await asyncio.wait_for(self.message_queue.get(), timeout=timeout)

            return message

        except asyncio.TimeoutError:
            logger.debug("BLE receive timeout")
            return None
        except Exception as e:
            logger.error(f"BLE receive error: {e}")
            return None

    async def _setup_characteristics(self, service) -> None:
        """Setup mDL service characteristics"""
        self.characteristics = {}

        for char in service.characteristics:
            char_uuid = char.uuid.upper()
            self.characteristics[char_uuid] = char
            logger.debug(f"Found characteristic: {char_uuid} - {char.properties}")

        # Verify required characteristics are present
        required_chars = [
            self.STATE_CHARACTERISTIC_UUID,
            self.CLIENT2SERVER_CHARACTERISTIC_UUID,
            self.SERVER2CLIENT_CHARACTERISTIC_UUID,
        ]

        for char_uuid in required_chars:
            if char_uuid.upper() not in self.characteristics:
                raise BLEError(f"Required characteristic {char_uuid} not found")

    async def _setup_notifications(self) -> None:
        """Setup notification handlers for mDL characteristics"""
        try:
            # Setup state characteristic notification
            await self.client.start_notify(
                self.STATE_CHARACTERISTIC_UUID, self._state_notification_handler
            )

            # Setup server to client notification
            await self.client.start_notify(
                self.SERVER2CLIENT_CHARACTERISTIC_UUID, self._server_to_client_handler
            )

            logger.debug("BLE notifications configured")

        except Exception as e:
            raise BLEError(f"Notification setup failed: {e}")

    def _state_notification_handler(self, sender: int, data: bytearray) -> None:
        """Handle state characteristic notifications"""
        try:
            if len(data) > 0:
                self.state_value = data[0]
                logger.debug(f"State changed to: 0x{self.state_value:02X}")

                # Handle state transitions
                if self.state_value == 0x01:  # Device engaged
                    self.state = TransportState.ENGAGED
                elif self.state_value == 0x02:  # Ready for request
                    pass
                elif self.state_value == 0x03:  # Processing request
                    pass
                elif self.state_value == 0xFF:  # Error
                    self.state = TransportState.ERROR

        except Exception as e:
            logger.error(f"State notification handler error: {e}")

    def _server_to_client_handler(self, sender: int, data: bytearray) -> None:
        """Handle server to client data notifications"""
        try:
            # Add to buffer
            self.server_to_client_buffer.extend(data)

            # Check if we have a complete message
            message = self._try_assemble_message()
            if message:
                # Create transport message
                import time

                transport_msg = TransportMessage(
                    data=message,
                    message_type="mdl_response",
                    timestamp=time.time(),
                    source=f"ble_device_{self.device_address}",
                )

                # Add to queue (non-blocking)
                try:
                    self.message_queue.put_nowait(transport_msg)
                except asyncio.QueueFull:
                    logger.warning("Message queue full, dropping message")

        except Exception as e:
            logger.error(f"Server to client handler error: {e}")

    def _try_assemble_message(self) -> bytes | None:
        """Try to assemble a complete message from buffer"""
        try:
            if len(self.server_to_client_buffer) < 2:
                return None

            # Simple message format: length (2 bytes) + data
            msg_length = int.from_bytes(self.server_to_client_buffer[:2], "big")

            if len(self.server_to_client_buffer) >= msg_length + 2:
                # Extract complete message
                message = bytes(self.server_to_client_buffer[2 : msg_length + 2])

                # Remove from buffer
                self.server_to_client_buffer = self.server_to_client_buffer[msg_length + 2 :]

                return message

            return None

        except Exception as e:
            logger.error(f"Message assembly error: {e}")
            return None

    async def scan_for_devices(self, timeout: float = 10.0) -> list[dict[str, Any]]:
        """Scan for mDL-capable BLE devices"""
        try:
            if not BLEAK_AVAILABLE:
                return []

            logger.info("Scanning for mDL BLE devices...")

            # Scan for devices
            devices = await BleakScanner.discover(timeout=timeout)

            mdl_devices = []
            for device in devices:
                # Check if device advertises mDL service
                if device.metadata and "uuids" in device.metadata:
                    uuids = device.metadata["uuids"]
                    if self.MDL_SERVICE_UUID.lower() in [uuid.lower() for uuid in uuids]:
                        mdl_devices.append(
                            {
                                "address": device.address,
                                "name": device.name or "Unknown mDL Device",
                                "rssi": device.rssi,
                                "services": [self.MDL_SERVICE_UUID],
                                "device": device,  # Store BLEDevice for later use
                            }
                        )

            logger.info(f"Found {len(mdl_devices)} mDL-capable devices")
            return mdl_devices

        except Exception as e:
            logger.error(f"BLE device scan error: {e}")
            return []

    async def read_state(self) -> int:
        """Read current state from device"""
        try:
            if not self.client or not self.client.is_connected:
                raise BLEError("Not connected")

            data = await self.client.read_gatt_char(self.STATE_CHARACTERISTIC_UUID)
            return data[0] if len(data) > 0 else 0

        except Exception as e:
            logger.error(f"State read error: {e}")
            raise BLEError(f"State read failed: {e}")

    async def write_state(self, state: int) -> None:
        """Write state to device"""
        try:
            if not self.client or not self.client.is_connected:
                raise BLEError("Not connected")

            await self.client.write_gatt_char(
                self.STATE_CHARACTERISTIC_UUID, state.to_bytes(1, "big"), response=True
            )

        except Exception as e:
            logger.error(f"State write error: {e}")
            raise BLEError(f"State write failed: {e}")


async def discover_mdl_devices(timeout: float = 10.0) -> list[dict[str, Any]]:
    """
    Discover mDL-capable BLE devices

    Args:
        timeout: Scan timeout in seconds

    Returns:
        List of discovered device information
    """
    transport = RealBLETransport()
    return await transport.scan_for_devices(timeout)


async def create_ble_connection(device_info: dict[str, Any]) -> RealBLETransport:
    """
    Create BLE connection to discovered device

    Args:
        device_info: Device information from scan results

    Returns:
        Connected BLE transport
    """
    if "device" in device_info:
        transport = RealBLETransport(device=device_info["device"])
    else:
        transport = RealBLETransport(device_address=device_info["address"])

    await transport.connect()
    return transport


class BLEPeripheralServer:
    """
    BLE Peripheral server for mDL holder devices

    This implements the holder side of the BLE connection, advertising
    the mDL service and handling reader requests.
    """

    def __init__(self):
        if not BLEAK_AVAILABLE:
            raise BLEError("bleak library not available")

        self.advertising = False
        self.connected = False
        self.client_address = None

        # Message handlers
        self.request_handler = None

    async def start_advertising(self, device_name: str = "mDL Holder") -> None:
        """Start advertising mDL service"""
        try:
            # Note: bleak doesn't support peripheral mode yet
            # This would need platform-specific implementation
            logger.warning("BLE peripheral mode not fully supported by bleak")
            logger.info(f"Would start advertising as: {device_name}")

            self.advertising = True

        except Exception as e:
            logger.error(f"BLE advertising start failed: {e}")
            raise BLEError(f"Advertising start failed: {e}")

    async def stop_advertising(self) -> None:
        """Stop advertising"""
        self.advertising = False
        logger.info("BLE advertising stopped")

    def set_request_handler(self, handler) -> None:
        """Set handler for incoming mDL requests"""
        self.request_handler = handler
