"""
Real NFC Transport Implementation for ISO/IEC 18013-5

This module implements a production-ready NFC transport layer using the pyscard library
for actual NFC/smart card communications with mDL holder devices.
"""

from __future__ import annotations

import logging
import struct
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from smartcard.CardConnection import CardConnection
    from smartcard.CardMonitoring import CardMonitor, CardObserver
    from smartcard.CardRequest import CardRequest
    from smartcard.CardType import AnyCardType
    from smartcard.Exceptions import CardConnectionException, CardRequestTimeoutException
    from smartcard.System import readers
    from smartcard.util import toBytes, toHexString

    PYSCARD_AVAILABLE = True
except ImportError:
    PYSCARD_AVAILABLE = False
    CardConnection = None
    CardMonitor = None
    CardObserver = None
    CardRequest = None
    AnyCardType = None
    readers = None

from ..transport import NFCError, TransportMessage, TransportState
from ..transport import NFCTransport as BaseNFCTransport

logger = logging.getLogger(__name__)


class RealNFCTransport(BaseNFCTransport):
    """
    Production NFC transport using pyscard library

    Implements the full ISO 18013-5 NFC data retrieval specification:
    - Smart card reader communication
    - ISO 7816 APDU commands
    - mDL application selection and communication
    - Proper fragmentation and reassembly
    """

    def __init__(self, reader_name: str | None = None):
        if not PYSCARD_AVAILABLE:
            raise NFCError("pyscard library not available - install with: pip install pyscard")

        super().__init__(reader_name)
        self.connection: CardConnection | None = None
        self.selected_reader = None
        self.card_present = False

        # ISO 7816 status words
        self.SW_SUCCESS = [0x90, 0x00]
        self.SW_MORE_DATA = [0x61]  # More data available
        self.SW_WRONG_LENGTH = [0x6C]  # Wrong length

    async def connect(self) -> bool:
        """Connect to NFC reader and wait for card"""
        try:
            self.state = TransportState.CONNECTING

            # Get available readers
            reader_list = readers()
            if not reader_list:
                raise NFCError("No smart card readers found")

            # Select reader
            if self.reader_id:
                # Find specific reader
                selected_reader = None
                for reader in reader_list:
                    if self.reader_id in str(reader):
                        selected_reader = reader
                        break

                if not selected_reader:
                    raise NFCError(f"Reader '{self.reader_id}' not found")
            else:
                # Use first available reader
                selected_reader = reader_list[0]

            self.selected_reader = selected_reader
            logger.info(f"Using NFC reader: {selected_reader}")

            # Wait for card insertion
            logger.info("Waiting for card insertion...")
            card_request = CardRequest(timeout=30, cardType=AnyCardType())
            card_service = card_request.waitforcard()

            # Connect to card
            self.connection = card_service.connection
            self.connection.connect()

            # Get ATR
            atr = self.connection.getATR()
            logger.info(f"Card ATR: {toHexString(atr)}")

            self.card_present = True
            self.state = TransportState.CONNECTED
            logger.info("NFC connection established")
            return True

        except CardRequestTimeoutException:
            logger.error("Card insertion timeout")
            self.state = TransportState.ERROR
            raise NFCError("Card insertion timeout")
        except Exception as e:
            logger.error(f"NFC connection failed: {e}")
            self.state = TransportState.ERROR
            raise NFCError(f"Connection failed: {e}")

    async def disconnect(self) -> None:
        """Disconnect from NFC card and reader"""
        try:
            if self.connection:
                self.connection.disconnect()
                self.connection = None

            self.card_present = False
            self.state = TransportState.DISCONNECTED
            logger.info("NFC disconnected")

        except Exception as e:
            logger.error(f"NFC disconnection error: {e}")

    async def send_message(self, message: bytes, message_type: str = "data") -> bool:
        """Send message via NFC using ISO 7816 APDUs"""
        try:
            if not self.connection:
                raise NFCError("Not connected")

            # Select mDL application first if not already done
            if not await self.select_mdl_application():
                raise NFCError("Failed to select mDL application")

            # Fragment message if necessary
            fragments = self._fragment_message(message)

            for i, fragment in enumerate(fragments):
                # Create APDU command
                # CLA=0x00, INS=0xA4 (SELECT/PROCESS), P1=0x04, P2=0x00
                cla = 0x00
                ins = 0xCB  # Custom instruction for mDL data
                p1 = 0x00 if i == 0 else 0x01  # First fragment vs continuation
                p2 = 0x00 if i < len(fragments) - 1 else 0x01  # More fragments vs last

                # Create APDU
                apdu = [cla, ins, p1, p2, len(fragment)] + list(fragment)

                # Send APDU
                response, sw1, sw2 = self.connection.transmit(apdu)

                # Check response
                if [sw1, sw2] != self.SW_SUCCESS:
                    raise NFCError(f"APDU failed: SW={sw1:02X}{sw2:02X}")

                logger.debug(f"Sent NFC fragment {i+1}/{len(fragments)}: {len(fragment)} bytes")

            logger.info(f"Sent NFC message: {len(message)} bytes in {len(fragments)} fragments")
            return True

        except Exception as e:
            logger.error(f"NFC send error: {e}")
            raise NFCError(f"Send failed: {e}")

    async def receive_message(self, timeout: float = 30.0) -> TransportMessage | None:
        """Receive message via NFC APDUs"""
        try:
            if not self.connection:
                return None

            # Send GET RESPONSE command to retrieve data
            response_data = bytearray()

            while True:
                # GET RESPONSE APDU
                apdu = [0x00, 0xC0, 0x00, 0x00, 0x00]  # Le=0 means get all available

                response, sw1, sw2 = self.connection.transmit(apdu)

                if [sw1, sw2] == self.SW_SUCCESS:
                    response_data.extend(response)
                    break
                elif sw1 == 0x61:  # More data available
                    response_data.extend(response)
                    # Continue reading
                elif [sw1, sw2] == [0x6F, 0x00]:  # No data available
                    break
                else:
                    logger.warning(f"Unexpected response: SW={sw1:02X}{sw2:02X}")
                    break

            if response_data:
                return TransportMessage(
                    data=bytes(response_data),
                    message_type="mdl_response",
                    timestamp=time.time(),
                    source=f"nfc_card_{self.selected_reader}",
                )

            return None

        except Exception as e:
            logger.error(f"NFC receive error: {e}")
            return None

    async def select_mdl_application(self) -> bool:
        """Select the mDL application on the NFC card"""
        try:
            if not self.connection:
                return False

            # SELECT command for mDL AID
            # CLA=0x00, INS=0xA4, P1=0x04 (select by DF name), P2=0x00
            aid_bytes = list(self.MDL_AID)
            apdu = [0x00, 0xA4, 0x04, 0x00, len(aid_bytes)] + aid_bytes

            response, sw1, sw2 = self.connection.transmit(apdu)

            if [sw1, sw2] == self.SW_SUCCESS:
                logger.info("mDL application selected successfully")
                if response:
                    logger.debug(f"SELECT response: {toHexString(response)}")
                return True
            else:
                logger.error(f"mDL application selection failed: SW={sw1:02X}{sw2:02X}")
                return False

        except Exception as e:
            logger.error(f"mDL application selection error: {e}")
            return False

    async def send_apdu(
        self,
        cla: int,
        ins: int,
        p1: int,
        p2: int,
        data: bytes | None = None,
        le: int | None = None,
    ) -> tuple[bytes, int, int]:
        """
        Send raw APDU command

        Args:
            cla: Class byte
            ins: Instruction byte
            p1: Parameter 1
            p2: Parameter 2
            data: Command data
            le: Expected response length

        Returns:
            Tuple of (response_data, sw1, sw2)
        """
        try:
            if not self.connection:
                raise NFCError("Not connected")

            # Build APDU
            apdu = [cla, ins, p1, p2]

            if data:
                apdu.extend([len(data)] + list(data))

            if le is not None:
                apdu.append(le)

            # Send APDU
            response, sw1, sw2 = self.connection.transmit(apdu)

            logger.debug(f"APDU sent: {toHexString(apdu)}")
            logger.debug(f"APDU response: {toHexString(response)} SW={sw1:02X}{sw2:02X}")

            return bytes(response), sw1, sw2

        except Exception as e:
            logger.error(f"APDU send error: {e}")
            raise NFCError(f"APDU send failed: {e}")

    async def get_card_info(self) -> dict[str, Any]:
        """Get information about the connected card"""
        try:
            if not self.connection:
                return {}

            info = {
                "atr": toHexString(self.connection.getATR()),
                "reader": str(self.selected_reader),
                "protocol": self.connection.getProtocol(),
                "present": self.card_present,
            }

            # Try to get additional card information
            try:
                # GET DATA for card capabilities
                response, sw1, sw2 = await self.send_apdu(0x00, 0xCA, 0x00, 0x65, le=0)
                if [sw1, sw2] == self.SW_SUCCESS:
                    info["capabilities"] = toHexString(response)
            except:
                pass

            return info

        except Exception as e:
            logger.error(f"Card info retrieval error: {e}")
            return {}

    @staticmethod
    def list_readers() -> list[str]:
        """List available smart card readers"""
        try:
            if not PYSCARD_AVAILABLE:
                return []

            reader_list = readers()
            return [str(reader) for reader in reader_list]

        except Exception as e:
            logger.error(f"Reader listing error: {e}")
            return []


class NFCCardObserver(CardObserver):
    """
    Card observer for monitoring card insertion/removal events
    """

    def __init__(self, callback=None):
        self.callback = callback

    def update(self, observable, actions):
        """Handle card events"""
        for action in actions:
            if hasattr(action, "card"):
                if str(action).startswith("Inserted"):
                    logger.info(f"Card inserted: {toHexString(action.card.atr)}")
                    if self.callback:
                        self.callback("inserted", action.card)
                elif str(action).startswith("Removed"):
                    logger.info("Card removed")
                    if self.callback:
                        self.callback("removed", None)


class NFCReaderManager:
    """
    Manager for NFC reader operations and card monitoring
    """

    def __init__(self):
        if not PYSCARD_AVAILABLE:
            raise NFCError("pyscard library not available")

        self.card_monitor = None
        self.card_observer = None
        self.active_connections = {}

    def start_monitoring(self, callback=None) -> None:
        """Start monitoring for card insertion/removal"""
        try:
            self.card_observer = NFCCardObserver(callback)
            self.card_monitor = CardMonitor()
            self.card_monitor.addObserver(self.card_observer)

            logger.info("NFC card monitoring started")

        except Exception as e:
            logger.error(f"Card monitoring start error: {e}")
            raise NFCError(f"Monitoring start failed: {e}")

    def stop_monitoring(self) -> None:
        """Stop monitoring for card events"""
        try:
            if self.card_monitor and self.card_observer:
                self.card_monitor.deleteObserver(self.card_observer)
                self.card_monitor = None
                self.card_observer = None

            logger.info("NFC card monitoring stopped")

        except Exception as e:
            logger.error(f"Card monitoring stop error: {e}")

    async def create_connection(self, reader_name: str | None = None) -> RealNFCTransport:
        """Create NFC transport connection"""
        transport = RealNFCTransport(reader_name)
        await transport.connect()

        connection_id = f"{reader_name or 'default'}_{int(time.time())}"
        self.active_connections[connection_id] = transport

        return transport

    async def close_connection(self, transport: RealNFCTransport) -> None:
        """Close NFC transport connection"""
        await transport.disconnect()

        # Remove from active connections
        for conn_id, conn in list(self.active_connections.items()):
            if conn is transport:
                del self.active_connections[conn_id]
                break

    def get_reader_status(self) -> dict[str, Any]:
        """Get status of all readers"""
        reader_list = RealNFCTransport.list_readers()

        status = {
            "readers_available": len(reader_list),
            "readers": reader_list,
            "active_connections": len(self.active_connections),
            "monitoring_active": self.card_monitor is not None,
        }

        return status


async def discover_nfc_readers() -> list[dict[str, Any]]:
    """
    Discover available NFC readers

    Returns:
        List of reader information
    """
    try:
        reader_list = RealNFCTransport.list_readers()

        readers_info = []
        for reader_name in reader_list:
            readers_info.append(
                {
                    "name": reader_name,
                    "type": "PC/SC Compatible",
                    "status": "available",
                    "capabilities": ["ISO14443", "ISO15693"],
                }
            )

        logger.info(f"Discovered {len(readers_info)} NFC readers")
        return readers_info

    except Exception as e:
        logger.error(f"NFC reader discovery error: {e}")
        return []


async def wait_for_mdl_card(timeout: float = 30.0) -> RealNFCTransport | None:
    """
    Wait for mDL-capable card and create transport

    Args:
        timeout: Wait timeout in seconds

    Returns:
        Connected NFC transport or None
    """
    try:
        transport = RealNFCTransport()

        # Try to connect (this waits for card)
        if await transport.connect():
            # Verify it's an mDL card
            if await transport.select_mdl_application():
                logger.info("mDL card detected and connected")
                return transport
            else:
                logger.warning("Card present but not mDL-capable")
                await transport.disconnect()

        return None

    except Exception as e:
        logger.error(f"mDL card wait error: {e}")
        return None
