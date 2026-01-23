"""
Smart card utilities for Marty services.

This module provides utilities for working with smart cards and RFID chips
commonly used in e-passports, leveraging the pyscard library.
"""

from __future__ import annotations

import logging
from typing import Any

from smartcard.CardConnectionObserver import CardConnectionObserver
from smartcard.CardRequest import CardRequest
from smartcard.CardType import AnyCardType

# Import pyscard library components
from smartcard.System import readers
from smartcard.util import toHexString

from marty_plugin.common.models.passport import MRZData
from marty_plugin.common.rfid.secure_messaging import SecureMessaging, SessionKeys
from marty_plugin.common.utils.mrz_utils import MRZException, MRZParser

logger = logging.getLogger(__name__)

# Standard e-passport command constants
SELECT_MF = [0x00, 0xA4, 0x00, 0x0C, 0x02, 0x3F, 0x00]  # Select Master File
SELECT_EF = [0x00, 0xA4, 0x02, 0x0C]  # Select Elementary File (needs file ID)
SELECT_DF = [0x00, 0xA4, 0x01, 0x0C]  # Select Dedicated File (needs file ID)
SELECT_AID = [0x00, 0xA4, 0x04, 0x0C]  # Select by AID (needs AID)
SELECT_EF_COM = [0x00, 0xA4, 0x02, 0x0C, 0x02, 0x01, 0x1E]  # Select EF.COM
SELECT_EF_SOD = [0x00, 0xA4, 0x02, 0x0C, 0x02, 0x01, 0x1D]  # Select EF.SOD
READ_BINARY = [0x00, 0xB0]  # Read Binary (needs offset and length)

# E-passport AIDs
AID_MRTD = [0xA0, 0x00, 0x00, 0x02, 0x47, 0x10, 0x01]  # AID for MRTD application


class APDULogObserver(CardConnectionObserver):
    """Observer for logging APDU commands."""

    def __init__(self) -> None:
        self.commands = []
        self.responses = []

    def update(self, cardconnection, ccevent) -> None:
        if ccevent.type == "command":
            cmd = toHexString(ccevent.args[0])
            logger.debug(f"APDU: {cmd}")
            self.commands.append(ccevent.args[0])
        elif ccevent.type == "response":
            resp = toHexString(ccevent.args[0])
            sw1, sw2 = ccevent.args[0][-2:]
            logger.debug(f"Response: {resp} (SW1=0x{sw1:02X}, SW2=0x{sw2:02X})")
            self.responses.append(ccevent.args[0])


class SmartCardReader:
    """Wrapper for smart card reader operations."""

    def __init__(self, reader_index: int = 0, timeout: int = 20) -> None:
        """
        Initialize the smart card reader.

        Args:
            reader_index: Index of the reader to use (default 0)
            timeout: Timeout in seconds for card connection (default 20)
        """
        self.reader_index = reader_index
        self.timeout = timeout
        self.connection = None
        self.observer = APDULogObserver()

    def list_readers(self) -> list[str]:
        """
        Get a list of available readers.

        Returns:
            List of reader names
        """
        try:
            return [str(reader) for reader in readers()]
        except Exception as e:
            logger.exception(f"Failed to list readers: {e}")
            return []

    def wait_for_card(self) -> bool:
        """
        Wait for a card to be inserted.

        Returns:
            True if a card was detected, False otherwise
        """
        try:
            card_request = CardRequest(timeout=self.timeout, cardType=AnyCardType())
            card_service = card_request.waitforcard()
            self.connection = card_service.connection
            self.connection.addObserver(self.observer)
            self.connection.connect()
        except Exception as e:
            logger.exception(f"Error waiting for card: {e}")
            return False
        else:
            return True

    def disconnect(self) -> None:
        """Disconnect from the card."""
        if self.connection:
            try:
                self.connection.disconnect()
                self.connection = None
            except Exception as e:
                logger.exception(f"Error disconnecting from card: {e}")

    def send_apdu(self, command: list[int]) -> tuple[list[int], int, int]:
        """
        Send an APDU command to the card.

        Args:
            command: APDU command as list of integers

        Returns:
            Tuple of (response_data, sw1, sw2)
        """
        if not self.connection:
            msg = "Not connected to a card"
            raise ValueError(msg)

        try:
            data, sw1, sw2 = self.connection.transmit(command)
        except Exception as e:
            logger.exception(f"Error sending APDU: {e}")
            raise
        else:
            return data, sw1, sw2

    def select_file(self, file_id: list[int], select_type: int = 0x02) -> tuple[bool, bytes]:
        """
        Select a file on the card.

        Args:
            file_id: File ID as list of integers
            select_type: Selection type (default 0x02 for Elementary File)

        Returns:
            Tuple of (success, response_data)
        """
        # Build select command
        command = [0, 164, select_type, 12, len(file_id), *file_id]

        try:
            data, sw1, sw2 = self.send_apdu(command)
            success = sw1 == 0x90 and sw2 == 0x00
            return success, bytes(data)
        except Exception as e:
            logger.exception(f"Error selecting file: {e}")
            return False, b""

    def select_application(self, aid: list[int]) -> bool:
        """
        Select an application by AID.

        Args:
            aid: Application ID as list of integers

        Returns:
            True if successful, False otherwise
        """
        command = [*SELECT_AID, len(aid), *aid]
        try:
            data, sw1, sw2 = self.send_apdu(command)
        except Exception as e:
            logger.exception(f"Error selecting application: {e}")
            return False
        else:
            return sw1 == 0x90 and sw2 == 0x00

    def read_binary(self, offset: int = 0, length: int = 0xFF) -> tuple[bool, bytes]:
        """
        Read binary data from the currently selected file.

        Args:
            offset: Offset in the file (default 0)
            length: Maximum length to read (default 255)

        Returns:
            Tuple of (success, data)
        """
        # Build read binary command
        p1 = (offset >> 8) & 0xFF  # High byte of offset
        p2 = offset & 0xFF  # Low byte of offset
        command = [*READ_BINARY, p1, p2, length]

        try:
            data, sw1, sw2 = self.send_apdu(command)

            # Special case: file larger than requested length
            if sw1 == 0x6C:  # Wrong length, SW2 contains correct length
                command[-1] = sw2  # Update Le with correct length
                data, sw1, sw2 = self.send_apdu(command)

            success = sw1 == 0x90 and sw2 == 0x00
            return success, bytes(data)
        except Exception as e:
            logger.exception(f"Error reading binary: {e}")
            return False, b""

    def read_file(self, file_id: list[int], select_type: int = 0x02) -> bytes:
        """
        Select and read an entire file.

        Args:
            file_id: File ID as list of integers
            select_type: Selection type (default 0x02 for Elementary File)

        Returns:
            File contents as bytes, or empty bytes if failed
        """
        success, _ = self.select_file(file_id, select_type)
        if not success:
            return b""

        # Start reading from beginning
        offset = 0
        file_data = b""

        # Read in chunks
        while True:
            success, chunk = self.read_binary(offset, 0xFF)
            if not success or not chunk:
                break

            file_data += chunk
            offset += len(chunk)

            # If we got less than requested, we're done
            if len(chunk) < 0xFF:
                break

        return file_data


class EPassportReader(SmartCardReader):
    """Reader specialized for e-passport operations."""

    def __init__(self, reader_index: int = 0, timeout: int = 20) -> None:
        """
        Initialize the e-passport reader.

        Args:
            reader_index: Index of the reader to use (default 0)
            timeout: Timeout in seconds for card connection (default 20)
        """
        super().__init__(reader_index, timeout)
        self.data_groups = {}
        self.secure_messaging = SecureMessaging()
        self.session_keys: SessionKeys | None = None

    def connect_to_passport(self) -> bool:
        """
        Connect to an e-passport.

        Returns:
            True if successfully connected to an e-passport, False otherwise
        """
        if not self.wait_for_card():
            return False

        # Select the MRTD application
        return self.select_application(AID_MRTD)

    def perform_bac(self, mrz_data: MRZData | str) -> SessionKeys:
        """Execute Basic Access Control mutual authentication."""

        if isinstance(mrz_data, str):
            try:
                mrz = MRZParser.parse_td3_mrz(mrz_data)
            except MRZException as exc:  # pragma: no cover - defensive
                msg = f"Invalid MRZ data supplied: {exc}"
                raise ValueError(msg) from exc
        else:
            mrz = mrz_data

        # Step 1: obtain challenge from the chip
        challenge_data, sw1, sw2 = self.send_apdu([0x00, 0x84, 0x00, 0x00, 0x08])
        if sw1 != 0x90 or sw2 != 0x00:
            msg = f"GET CHALLENGE failed with status {sw1:02X}{sw2:02X}"
            raise ValueError(msg)
        challenge = bytes(challenge_data)

        # Step 2: derive BAC keys from MRZ information
        bac_keys = self.secure_messaging.derive_bac_keys(
            passport_number=mrz.document_number,
            date_of_birth=mrz.date_of_birth,
            date_of_expiry=mrz.date_of_expiry,
        )

        # Step 3: construct mutual authentication payload
        auth_payload = self.secure_messaging.perform_basic_access_control(bac_keys, challenge)
        auth_apdu = [0x00, 0x82, 0x00, 0x00, len(auth_payload), *auth_payload]

        auth_response, sw1, sw2 = self.send_apdu(auth_apdu)
        if sw1 != 0x90 or sw2 != 0x00:
            msg = f"MUTUAL AUTHENTICATE failed with status {sw1:02X}{sw2:02X}"
            raise ValueError(msg)

        session_keys = self.secure_messaging.complete_basic_access_control(
            bac_keys, bytes(auth_response)
        )
        self.session_keys = session_keys
        return session_keys

    def start_pace(self, password: str, nonce: bytes) -> bytes:
        """Initialise PACE and return the reader public key to send to the chip."""

        return self.secure_messaging.setup_pace_protocol(password=password, nonce=nonce)

    def complete_pace(self, chip_public_key: bytes) -> SessionKeys:
        """Finalize the PACE protocol once the chip's public key is available."""

        session_keys = self.secure_messaging.complete_pace_protocol(chip_public_key)
        self.session_keys = session_keys
        return session_keys

    def read_ef_com(self) -> dict[str, Any]:
        """
        Read and parse the EF.COM file.

        Returns:
            Dictionary with EF.COM data or empty dict if failed
        """
        success, _ = self.select_file([0x01, 0x1E])  # EF.COM
        if not success:
            return {}

        success, data = self.read_binary()
        if not success:
            return {}

        # Basic parsing (would be enhanced in a real implementation)
        # In a real implementation, this would properly parse the ASN.1 structure
        return {"raw_data": data.hex()}

        # For now, just return the raw data
        # In a real implementation, this would parse the LDS version
        # and list of available data groups

    def read_ef_sod(self) -> bytes:
        """
        Read the EF.SOD file (Document Security Object).

        Returns:
            EF.SOD contents as bytes, or empty bytes if failed
        """
        return self.read_file([0x01, 0x1D])  # EF.SOD

    def read_data_group(self, dg_number: int) -> bytes:
        """
        Read a specific data group.

        Args:
            dg_number: Data group number (1-16)

        Returns:
            Data group contents as bytes, or empty bytes if failed
        """
        if not 1 <= dg_number <= 16:
            msg = "Data group number must be between 1 and 16"
            raise ValueError(msg)

        # Data group file IDs
        dg_file_ids = {
            1: [0x01, 0x01],  # EF.DG1 - MRZ
            2: [0x01, 0x02],  # EF.DG2 - Facial biometrics
            3: [0x01, 0x03],  # EF.DG3 - Fingerprint biometrics
            4: [0x01, 0x04],  # EF.DG4 - Iris biometrics
            5: [0x01, 0x05],  # EF.DG5 - Portrait
            6: [0x01, 0x06],  # EF.DG6 - Reserved
            7: [0x01, 0x07],  # EF.DG7 - Signature
            8: [0x01, 0x08],  # EF.DG8 - Data features
            9: [0x01, 0x09],  # EF.DG9 - Structure features
            10: [0x01, 0x0A],  # EF.DG10 - Substance features
            11: [0x01, 0x0B],  # EF.DG11 - Additional personal details
            12: [0x01, 0x0C],  # EF.DG12 - Additional document details
            13: [0x01, 0x0D],  # EF.DG13 - Optional details
            14: [0x01, 0x0E],  # EF.DG14 - Security options
            15: [0x01, 0x0F],  # EF.DG15 - Active Authentication public key info
            16: [0x01, 0x10],  # EF.DG16 - Person(s) to notify
        }

        return self.read_file(dg_file_ids[dg_number])

    def read_passport(self) -> dict[str, Any]:
        """
        Read all the standard files from an e-passport.

        Returns:
            Dictionary containing the passport data
        """
        passport_data = {"ef_com": None, "ef_sod": None, "data_groups": {}}

        # Connect to the passport
        if not self.connect_to_passport():
            logger.error("Failed to connect to passport")
            return passport_data

        # Read EF.COM
        ef_com = self.read_ef_com()
        passport_data["ef_com"] = ef_com

        # Read EF.SOD
        ef_sod = self.read_ef_sod()
        passport_data["ef_sod"] = ef_sod.hex() if ef_sod else None

        # Read common data groups
        for dg_number in [1, 2, 11, 12, 14, 15]:
            try:
                dg_data = self.read_data_group(dg_number)
                if dg_data:
                    passport_data["data_groups"][f"DG{dg_number}"] = dg_data.hex()
            except Exception as e:
                logger.exception(f"Error reading DG{dg_number}: {e}")

        # Disconnect from the passport
        self.disconnect()

        return passport_data
