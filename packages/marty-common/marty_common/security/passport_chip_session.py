"""Active Authentication orchestration over BAC/PACE secure messaging.

This module encapsulates the low-level APDU choreography required to open a
secure channel with an ICAO-compliant passport chip (BAC or PACE) and execute
Active Authentication using the DG15 public key material.

The implementation favours composability: transports only need to expose a
``send_apdu`` method compatible with the existing ``ReaderInterface`` contract
used across the project. Secure messaging primitives are delegated to
``SecureMessaging`` so the same code path can be exercised in production and in
unit tests with mock chips.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from marty_common.rfid.apdu_commands import APDUCommand, APDUResponse, PassportAPDU
from marty_common.rfid.secure_messaging import BACKeys, SecureMessaging, SessionKeys
from marty_common.security.active_authentication import (
    ActiveAuthenticationChallenge,
    ActiveAuthenticationProtocol,
    ActiveAuthenticationResponse,
)
from marty_common.security.dg15_parser import ChipAuthenticationInfo, DG15Parser

logger = logging.getLogger(__name__)


class PassportChipTransport(Protocol):
    """Minimal transport abstraction that can exchange APDUs with a chip."""

    def send_apdu(self, apdu: bytes) -> bytes:
        """Transmit a raw APDU to the chip and return the response bytes."""


@dataclass
class ActiveAuthenticationOutcome:
    """Result of a full active authentication round-trip."""

    challenge: ActiveAuthenticationChallenge
    response: ActiveAuthenticationResponse
    is_valid: bool
    chip_info: ChipAuthenticationInfo


class PassportChipSession:
    """Manage BAC/PACE establishment and Active Authentication execution."""

    def __init__(
        self,
        transport: PassportChipTransport,
        secure_messaging: SecureMessaging | None = None,
        aa_protocol: ActiveAuthenticationProtocol | None = None,
    ) -> None:
        self._transport = transport
        self._secure_messaging = secure_messaging or SecureMessaging()
        self._aa_protocol = aa_protocol or ActiveAuthenticationProtocol()
        self._dg15_parser = DG15Parser()
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    # ------------------------------------------------------------------
    # APDU helpers
    # ------------------------------------------------------------------
    def _transmit_apdu(self, command: APDUCommand) -> APDUResponse:
        """Send command and parse the APDU response."""
        apdu_bytes = command.to_bytes()
        response_bytes = self._transport.send_apdu(apdu_bytes)
        response = APDUResponse.from_bytes(response_bytes)
        if not response.is_success:
            msg = f"APDU {command.ins:02X} failed: {response.status_description}"
            raise ValueError(msg)
        return response

    def _transmit_raw(self, apdu: bytes) -> bytes:
        """Send raw APDU bytes (already protected) and return response bytes."""
        return self._transport.send_apdu(apdu)

    # ------------------------------------------------------------------
    # Session establishment helpers
    # ------------------------------------------------------------------
    def select_passport_application(self) -> None:
        """Select the LDS passport application (AID A0000002471001)."""
        response = self._transmit_apdu(PassportAPDU.select_passport_application())
        self._logger.debug("Passport application selected: %s", response.status_description)

    def establish_bac(
        self,
        passport_number: str,
        date_of_birth: str,
        date_of_expiry: str,
    ) -> SessionKeys:
        """Execute Basic Access Control mutual authentication."""
        # Derive BAC keys from MRZ components
        bac_keys: BACKeys = self._secure_messaging.derive_bac_keys(
            passport_number=passport_number,
            date_of_birth=date_of_birth,
            date_of_expiry=date_of_expiry,
        )

        # Step 1 – chip challenge (RND.IC)
        challenge_resp = self._transmit_apdu(APDUCommand.get_challenge(8))
        chip_challenge = challenge_resp.data
        if len(chip_challenge) != 8:
            msg = "Unexpected BAC challenge length"
            raise ValueError(msg)

        # Step 2 – mutual authentication request (RND.IFD || RND.IC || K.IFD)
        auth_payload = self._secure_messaging.perform_basic_access_control(bac_keys, chip_challenge)
        mutual_response = self._transmit_apdu(APDUCommand.mutual_authenticate(auth_payload))

        # Step 3 – derive session keys from response
        session_keys = self._secure_messaging.complete_basic_access_control(
            bac_keys, mutual_response.data
        )
        self._logger.info("BAC session keys established")
        return session_keys

    def establish_pace(self, password: str) -> SessionKeys:
        """Execute a simplified PACE handshake using ISO 7816 general authenticate."""
        # Step 1 – obtain encrypted nonce from chip (GET CHALLENGE 16 bytes)
        challenge_resp = self._transmit_apdu(APDUCommand.get_challenge(16))
        encrypted_nonce = challenge_resp.data
        if len(encrypted_nonce) < 16:
            msg = "PACE nonce response too short"
            raise ValueError(msg)

        # Step 2 – reader generates ephemeral public key
        reader_public = self._secure_messaging.setup_pace_protocol(password, encrypted_nonce)

        # Step 3 – send reader public key via GENERAL AUTHENTICATE (tagged data object 0x81)
        pace_request = self._build_pace_authenticate_payload(reader_public, tag=0x81)
        pace_response_bytes = self._transmit_apdu(
            APDUCommand.general_authenticate(pace_request)
        ).data

        # Step 4 – parse chip public key from GENERAL AUTHENTICATE response (tag 0x82)
        chip_public = self._extract_pace_element(pace_response_bytes, expected_tag=0x82)
        session_keys = self._secure_messaging.complete_pace_protocol(chip_public)
        self._logger.info("PACE session keys established")
        return session_keys

    # ------------------------------------------------------------------
    # Data group access helpers
    # ------------------------------------------------------------------
    def read_data_group(self, dg_number: int) -> bytes:
        """Read raw DG data (with secure messaging if available)."""
        select_cmd = PassportAPDU.select_data_group(dg_number)
        read_cmds = PassportAPDU().build_read_ef(length=2048, offset=0)

        response = self._transmit_apdu(select_cmd)
        self._logger.debug("Selected DG%d: %s", dg_number, response.status_description)

        data_chunks: list[bytes] = []
        for cmd in read_cmds:
            protected_cmd = self._protect_command(cmd)
            raw_response = (
                self._transmit_raw(protected_cmd)
                if isinstance(protected_cmd, bytes)
                else self._transmit_apdu(protected_cmd).data
            )
            chunk = self._unwrap_response(raw_response)
            data_chunks.append(chunk)

            if len(chunk) < cmd.le:
                break

        return b"".join(data_chunks)

    # ------------------------------------------------------------------
    # Active Authentication
    # ------------------------------------------------------------------
    def perform_active_authentication(
        self,
        dg15_data: bytes,
        challenge: ActiveAuthenticationChallenge | None = None,
    ) -> ActiveAuthenticationOutcome:
        """Run Active Authentication using DG15 public key material."""
        challenge = challenge or self._aa_protocol.generate_challenge()
        aa_apdu = self._aa_protocol.create_aa_apdu_command(challenge)
        protected_apdu = self._protect_raw_apdu(aa_apdu)
        raw_response = self._transport.send_apdu(protected_apdu)
        plaintext_response = self._unwrap_response(raw_response, raw=True)
        response = self._aa_protocol.parse_aa_response(plaintext_response, challenge)

        chip_info = self._dg15_parser.parse_dg15(dg15_data)
        public_key = chip_info.public_key

        is_valid = self._aa_protocol.verify_active_authentication(response, challenge, public_key)
        return ActiveAuthenticationOutcome(
            challenge=challenge,
            response=response,
            is_valid=is_valid,
            chip_info=chip_info,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _protect_command(self, command: APDUCommand) -> APDUCommand | bytes:
        if not self._secure_messaging.session_keys:
            return command
        return self._secure_messaging.encrypt_command(command.to_bytes())

    def _protect_raw_apdu(self, apdu: bytes) -> bytes:
        if not self._secure_messaging.session_keys:
            return apdu
        return self._secure_messaging.encrypt_command(apdu)

    def _unwrap_response(self, response: bytes, raw: bool = False) -> bytes:
        if not self._secure_messaging.session_keys:
            return response if raw else APDUResponse.from_bytes(response).data
        decrypted = self._secure_messaging.decrypt_response(response)
        return decrypted if raw else APDUResponse.from_bytes(decrypted).data

    @staticmethod
    def _build_pace_authenticate_payload(public_key: bytes, tag: int) -> bytes:
        if not public_key:
            msg = "PACE public key must not be empty"
            raise ValueError(msg)

        value = bytes([tag]) + PassportChipSession._encode_length(len(public_key)) + public_key
        # Wrap in dynamic authentication template tag 0x7C
        return b"\x7c" + PassportChipSession._encode_length(len(value)) + value

    @staticmethod
    def _extract_pace_element(payload: bytes, expected_tag: int) -> bytes:
        if not payload:
            msg = "PACE response empty"
            raise ValueError(msg)

        if payload[0] != 0x7C:
            msg = "PACE response missing dynamic authentication template"
            raise ValueError(msg)

        _, offset = PassportChipSession._read_length(payload, 1)
        cursor = 1 + offset
        while cursor < len(payload):
            tag = payload[cursor]
            cursor += 1
            length, consumed = PassportChipSession._read_length(payload, cursor)
            cursor += consumed
            value = payload[cursor : cursor + length]
            cursor += length
            if tag == expected_tag:
                return value
        msg = "Expected PACE element not found in response"
        raise ValueError(msg)

    @staticmethod
    def _encode_length(length: int) -> bytes:
        if length <= 0x7F:
            return bytes([length])
        if length <= 0xFF:
            return b"\x81" + bytes([length])
        if length <= 0xFFFF:
            return b"\x82" + length.to_bytes(2, "big")
        msg = "PACE payload too large"
        raise ValueError(msg)

    @staticmethod
    def _read_length(buffer: bytes, offset: int) -> tuple[int, int]:
        first = buffer[offset]
        if first & 0x80 == 0:
            return first, 1
        num_octets = first & 0x7F
        if num_octets == 0:
            msg = "Indefinite length not supported"
            raise ValueError(msg)
        value = int.from_bytes(buffer[offset + 1 : offset + 1 + num_octets], "big")
        return value, 1 + num_octets


__all__ = [
    "ActiveAuthenticationOutcome",
    "PassportChipSession",
    "PassportChipTransport",
]
