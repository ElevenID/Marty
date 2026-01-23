"""PC/SC (Personal Computer/Smart Card) Reader Implementation.

Provides interface to PC/SC compatible smart card readers.
Requires pyscard library for PC/SC communication.
"""

from __future__ import annotations

import logging

from . import ReaderInterface

logger = logging.getLogger(__name__)


class PCSCReader(ReaderInterface):
    """PC/SC compatible smart card reader."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.connection = None
        self.card_service = None
        self.logger = logging.getLogger(__name__)

        try:
            # Import PC/SC dependencies
            from smartcard.CardRequest import CardRequest
            from smartcard.CardService import CardService
            from smartcard.Exceptions import CardRequestTimeoutException
            from smartcard.System import readers

            self.CardService = CardService
            self.CardRequest = CardRequest
            self.CardRequestTimeoutException = CardRequestTimeoutException

            # Find the specific reader
            available_readers = readers()
            self.reader = None

            for reader in available_readers:
                if str(reader) == name:
                    self.reader = reader
                    break

            if self.reader is None:
                msg = f"Reader '{name}' not found"
                raise ValueError(msg)

        except ImportError as e:
            msg = f"PC/SC library not available: {e}"
            self.logger.exception(msg)
            raise ImportError(msg) from e

    def connect(self) -> bool:
        """Connect to the smart card reader."""
        try:
            # Request card from reader
            card_request = self.CardRequest(readers=[self.reader], timeout=10)  # 10 second timeout

            self.card_service = card_request.waitforcard()
            self.card_service.connection.connect()

            self.logger.info("Connected to reader: %s", self.name)

        except self.CardRequestTimeoutException:
            self.logger.warning("No card found in reader: %s", self.name)
            return False
        except Exception:
            self.logger.exception("Failed to connect to reader %s", self.name)
            return False
        else:
            return True

    def disconnect(self) -> None:
        """Disconnect from the reader."""
        try:
            if self.card_service and self.card_service.connection:
                self.card_service.connection.disconnect()
                self.card_service = None
                self.logger.info("Disconnected from reader: %s", self.name)
        except Exception:
            self.logger.exception("Error disconnecting from reader %s", self.name)

    def is_connected(self) -> bool:
        """Check if reader is connected to a card."""
        return self.card_service is not None and self.card_service.connection is not None

    def send_apdu(self, apdu: bytes) -> bytes:
        """Send APDU command to the card."""
        if not self.is_connected():
            msg = "Reader not connected to card"
            raise RuntimeError(msg)

        try:
            # Convert bytes to list of integers (pyscard format)
            apdu_list = list(apdu)

            # Send APDU and get response
            response, sw1, sw2 = self.card_service.connection.transmit(apdu_list)

            # Convert response back to bytes
            response_bytes = bytes([*response, sw1, sw2])

            self.logger.debug("APDU sent: %s, response: %s", apdu.hex(), response_bytes.hex())

        except Exception:
            self.logger.exception("Failed to send APDU")
            raise
        else:
            return response_bytes

    def get_atr(self) -> bytes | None:
        """Get Answer To Reset from the card."""
        if not self.is_connected():
            return None

        try:
            atr = self.card_service.connection.getATR()
            return bytes(atr)
        except Exception:
            self.logger.exception("Failed to get ATR")
            return None
