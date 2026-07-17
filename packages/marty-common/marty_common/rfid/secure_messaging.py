"""Secure messaging primitives for ICAO Doc 9303 communication."""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass

# Use crypto_bridge for Rust-backed cryptographic operations
from marty_common.crypto_bridge import (
    tdes_cbc_encrypt,
    tdes_cbc_decrypt,
    p256_generate,
    p256_agree,
)

from marty_common.utils.mrz_utils import MRZException, MRZParser

logger = logging.getLogger(__name__)


@dataclass
class BACKeys:
    """Basic Access Control master keys."""

    k_enc: bytes
    k_mac: bytes
    k_seed: bytes


@dataclass
class SessionKeys:
    """Session keys used for secure messaging (BAC or PACE)."""

    k_s_enc: bytes
    k_s_mac: bytes
    ssc: int


@dataclass
class _BACContext:
    rnd_ifd: bytes
    k_ifd: bytes
    rnd_ic: bytes


@dataclass
class _PACEState:
    """PACE protocol state using raw key bytes."""
    private_key: bytes  # 32-byte P-256 private key
    public_key: bytes   # 65-byte uncompressed P-256 public key
    nonce: bytes
    k_pi: bytes


class SecureMessaging:
    """Implements ICAO-compliant BAC/PACE secure messaging."""

    def __init__(self) -> None:
        self.session_keys: SessionKeys | None = None
        self._bac_state: _BACContext | None = None
        self._pace_state: _PACEState | None = None
        self.logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # BAC key derivation and mutual authentication
    # ------------------------------------------------------------------
    def derive_bac_keys(
        self, passport_number: str, date_of_birth: str, date_of_expiry: str
    ) -> BACKeys:
        """Derive BAC master keys from MRZ data (ICAO Doc 9303 6.1.1)."""

        doc_number = self._normalize_document_number(passport_number)
        doc_cd = MRZParser.calculate_check_digit(doc_number)

        dob_cd = MRZParser.calculate_check_digit(date_of_birth)
        doe_cd = MRZParser.calculate_check_digit(date_of_expiry)

        mrz_info = f"{doc_number}{doc_cd}{date_of_birth}{dob_cd}{date_of_expiry}{doe_cd}"
        mrz_bytes = mrz_info.encode("ascii")

        k_seed = hashlib.sha1(mrz_bytes).digest()[:16]
        k_enc = self._derive_3des_key(k_seed, b"\x00\x00\x00\x01")
        k_mac = self._derive_3des_key(k_seed, b"\x00\x00\x00\x02")

        self.logger.debug("Derived BAC master keys from MRZ data")

        return BACKeys(k_enc=k_enc, k_mac=k_mac, k_seed=k_seed)

    def perform_basic_access_control(self, bac_keys: BACKeys, challenge: bytes) -> bytes:
        """Create mutual authentication command for BAC (ICAO Doc 9303 6.2)."""

        if len(challenge) != 8:
            msg = "Challenge must be 8 bytes"
            raise ValueError(msg)

        rnd_ifd = secrets.token_bytes(8)
        k_ifd = secrets.token_bytes(16)

        s = rnd_ifd + challenge + k_ifd
        e_ifd = self._encrypt_3des_cbc(s, bac_keys.k_enc)
        m_ifd = self._retail_mac(bac_keys.k_mac, e_ifd)

        self._bac_state = _BACContext(rnd_ifd=rnd_ifd, k_ifd=k_ifd, rnd_ic=challenge)
        self.logger.debug("Prepared BAC mutual authentication command")

        return e_ifd + m_ifd

    def complete_basic_access_control(self, bac_keys: BACKeys, response: bytes) -> SessionKeys:
        """Validate chip response and derive BAC session keys."""

        if not self._bac_state:
            msg = "BAC mutual authentication state missing"
            raise ValueError(msg)

        if len(response) < 40:
            msg = "Invalid BAC response length"
            raise ValueError(msg)

        e_ic = response[:-8]
        mac_ic = response[-8:]

        expected_mac = self._retail_mac(bac_keys.k_mac, e_ic)
        if mac_ic != expected_mac:
            msg = "BAC response MAC verification failed"
            raise ValueError(msg)

        s = self._decrypt_3des_cbc(e_ic, bac_keys.k_enc)
        rnd_ic = s[:8]
        rnd_ifd = s[8:16]
        k_ic = s[16:32]

        if rnd_ifd != self._bac_state.rnd_ifd:
            msg = "BAC RND.IFD mismatch"
            raise ValueError(msg)

        session_keys = self.derive_session_keys(
            k_ifd=self._bac_state.k_ifd,
            k_ic=k_ic,
            rnd_ic=rnd_ic,
            rnd_ifd=self._bac_state.rnd_ifd,
        )

        self._bac_state = None
        self.session_keys = session_keys
        self.logger.debug("BAC mutual authentication succeeded")

        return session_keys

    def derive_session_keys(
        self, k_ifd: bytes, k_ic: bytes, rnd_ic: bytes, rnd_ifd: bytes
    ) -> SessionKeys:
        """Derive secure messaging keys from BAC shared secrets."""

        if not (len(k_ifd) == len(k_ic) == 16):
            msg = "K.IFD and K.ICC must be 16-byte values"
            raise ValueError(msg)

        seed_input = bytes(x ^ y for x, y in zip(k_ifd, k_ic))
        k_seed = hashlib.sha1(seed_input).digest()[:16]

        k_s_enc = self._derive_3des_key(k_seed, b"\x00\x00\x00\x01")
        k_s_mac = self._derive_3des_key(k_seed, b"\x00\x00\x00\x02")
        ssc = int.from_bytes(rnd_ic[-4:] + rnd_ifd[-4:], "big")

        return SessionKeys(k_s_enc=k_s_enc, k_s_mac=k_s_mac, ssc=ssc)

    # ------------------------------------------------------------------
    # Secure messaging APDU protection (ISO 7816-4 + ICAO Doc 9303 6.3)
    # ------------------------------------------------------------------
    def encrypt_command(self, apdu: bytes) -> bytes:
        """Protect command APDU using current session keys."""

        if not self.session_keys:
            msg = "Session keys not established"
            raise ValueError(msg)

        cla, ins, p1, p2, data_field, le_field = self._parse_command_apdu(apdu)

        self.session_keys.ssc = (self.session_keys.ssc + 1) & 0xFFFFFFFFFFFFFFFF
        ssc_bytes = self.session_keys.ssc.to_bytes(8, "big")

        protected_header = bytes([cla | 0x0C, ins, p1, p2])

        do87 = b""
        if data_field:
            padded = self._iso_pad(data_field)
            encrypted = self._encrypt_3des_cbc(padded, self.session_keys.k_s_enc)
            do87 = b"\x87" + self._encode_length(len(encrypted) + 1) + b"\x01" + encrypted

        do97 = b""
        if le_field is not None:
            do97 = b"\x97" + self._encode_length(len(le_field)) + le_field

        mac_input = ssc_bytes + protected_header + do87 + do97
        mac = self._retail_mac(self.session_keys.k_s_mac, mac_input)
        do8e = b"\x8e\x08" + mac

        protected_data = do87 + do97 + do8e
        lc = self._encode_length(len(protected_data))

        return protected_header + lc + protected_data

    def decrypt_response(self, response: bytes) -> bytes:
        """Verify and decrypt protected response APDU."""

        if not self.session_keys:
            msg = "Session keys not established"
            raise ValueError(msg)

        self.session_keys.ssc = (self.session_keys.ssc + 1) & 0xFFFFFFFFFFFFFFFF
        ssc_bytes = self.session_keys.ssc.to_bytes(8, "big")

        tlvs, trailing_sw = self._parse_response_tlvs(response)

        do87_bytes = b""
        do99_bytes = b""
        mac_bytes = None
        plaintext = b""
        status = trailing_sw

        for tag, raw, encoded in tlvs:
            if tag == 0x87:
                do87_bytes = encoded
                if not raw:
                    continue
                if raw[0] != 0x01:
                    msg = "Unsupported DO87 format"
                    raise ValueError(msg)
                ciphertext = raw[1:]
                decrypted = self._decrypt_3des_cbc(ciphertext, self.session_keys.k_s_enc)
                plaintext = self._iso_unpad(decrypted)
            elif tag == 0x99:
                if len(raw) != 2:
                    msg = "Invalid DO99 length"
                    raise ValueError(msg)
                do99_bytes = encoded
                status = raw
            elif tag == 0x8E:
                if len(raw) != 8:
                    msg = "Invalid DO8E length"
                    raise ValueError(msg)
                mac_bytes = raw

        if mac_bytes is None:
            # Response was not protected – return as-is with trailing status
            return response

        mac_input = ssc_bytes + do87_bytes + do99_bytes
        expected_mac = self._retail_mac(self.session_keys.k_s_mac, mac_input)
        if mac_bytes != expected_mac:
            msg = "Secure messaging response MAC verification failed"
            raise ValueError(msg)

        return plaintext + status

    # ------------------------------------------------------------------
    # PACE (simplified ECDH implementation for educational purposes)
    # ------------------------------------------------------------------
    def setup_pace_protocol(
        self,
        password: str,
        nonce: bytes,
        curve: str = "p256",  # Currently only P-256 supported
    ) -> bytes:
        """Start PACE handshake and return the reader public key."""

        if not nonce:
            msg = "PACE nonce must not be empty"
            raise ValueError(msg)

        k_pi = self._derive_pace_password_key(password)
        decrypted_nonce = self._iso_unpad(self._decrypt_3des_cbc(nonce, k_pi))

        # Generate P-256 keypair using Rust crypto
        private_key, public_key = p256_generate()

        self._pace_state = _PACEState(
            private_key=private_key,
            public_key=public_key,
            nonce=decrypted_nonce,
            k_pi=k_pi,
        )
        self.logger.debug("PACE reader public key generated")

        return public_key

    def complete_pace_protocol(self, chip_public_key: bytes) -> SessionKeys:
        """Finish PACE handshake using chip public key."""

        if not self._pace_state:
            msg = "PACE state unavailable – call setup_pace_protocol first"
            raise ValueError(msg)

        # Perform ECDH key agreement using Rust crypto
        shared_secret = p256_agree(self._pace_state.private_key, chip_public_key)
        
        digest = hashlib.sha256(shared_secret + self._pace_state.nonce).digest()
        k_seed = digest[:16]

        k_s_enc = self._derive_3des_key(k_seed, b"\x00\x00\x00\x01")
        k_s_mac = self._derive_3des_key(k_seed, b"\x00\x00\x00\x02")
        ssc = int.from_bytes(digest[-8:], "big")

        self.session_keys = SessionKeys(k_s_enc=k_s_enc, k_s_mac=k_s_mac, ssc=ssc)
        self._pace_state = None
        self.logger.debug("PACE key agreement completed")

        return self.session_keys

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_document_number(number: str) -> str:
        cleaned = "".join(char for char in number.upper() if char.isalnum())
        return cleaned[:9].ljust(9, "<")

    @staticmethod
    def _adjust_des_parity(byte_value: int) -> int:
        parity = 0
        for bit in range(7):
            parity ^= (byte_value >> bit) & 1
        return (byte_value & 0xFE) | (parity ^ 1)

    def _derive_3des_key(self, seed: bytes, counter: bytes) -> bytes:
        digest = hashlib.sha1(seed + counter).digest()
        key_bytes = bytearray(digest[:16])
        for idx, value in enumerate(key_bytes):
            key_bytes[idx] = self._adjust_des_parity(value)
        return bytes(key_bytes)

    @staticmethod
    def _expand_3des_key(key: bytes) -> bytes:
        if len(key) == 16:
            return key + key[:8]
        if len(key) == 24:
            return key
        msg = "3DES key must be 16 or 24 bytes"
        raise ValueError(msg)

    def _encrypt_3des_cbc(self, data: bytes, key: bytes, iv: bytes | None = None) -> bytes:
        iv = iv or b"\x00" * 8
        # Use Rust-backed 3DES-CBC encryption via crypto_bridge
        return tdes_cbc_encrypt(self._expand_3des_key(key), data, iv)

    def _decrypt_3des_cbc(self, data: bytes, key: bytes, iv: bytes | None = None) -> bytes:
        iv = iv or b"\x00" * 8
        # Use Rust-backed 3DES-CBC decryption via crypto_bridge
        return tdes_cbc_decrypt(self._expand_3des_key(key), data, iv)

    @staticmethod
    def _iso_pad(data: bytes, block_size: int = 8) -> bytes:
        pad_len = block_size - (len(data) % block_size)
        padding = b"\x80" + b"\x00" * (pad_len - 1)
        return data + padding

    @staticmethod
    def _iso_unpad(data: bytes) -> bytes:
        if not data:
            return data
        idx = len(data) - 1
        while idx >= 0 and data[idx] == 0x00:
            idx -= 1
        if idx < 0 or data[idx] != 0x80:
            msg = "Invalid ISO/IEC 9797-1 padding"
            raise ValueError(msg)
        return data[:idx]

    def _retail_mac(self, key: bytes, data: bytes) -> bytes:
        padded = self._iso_pad(data)
        mac = self._encrypt_3des_cbc(padded, key)
        return mac[-8:]

    @staticmethod
    def _encode_length(length: int) -> bytes:
        if length <= 0x7F:
            return bytes([length])
        if length <= 0xFF:
            return b"\x81" + bytes([length])
        if length <= 0xFFFF:
            return b"\x82" + length.to_bytes(2, "big")
        msg = "Length encoding > 65535 not supported"
        raise ValueError(msg)

    def _encode_tlv(self, tag: int, value: bytes) -> bytes:
        tag_bytes = self._encode_tag(tag)
        length_bytes = self._encode_length(len(value))
        return tag_bytes + length_bytes + value

    @staticmethod
    def _encode_tag(tag: int) -> bytes:
        if tag <= 0xFF:
            return bytes([tag])
        return tag.to_bytes(2, "big")

    @staticmethod
    def _parse_command_apdu(apdu: bytes) -> tuple[int, int, int, int, bytes, bytes | None]:
        if len(apdu) < 4:
            msg = "APDU must contain at least CLA INS P1 P2"
            raise ValueError(msg)

        cla, ins, p1, p2 = apdu[:4]
        idx = 4
        data_field = b""
        le_field: bytes | None = None

        if len(apdu) > idx:
            lc = apdu[idx]
            idx += 1
            if lc:
                data_field = apdu[idx : idx + lc]
                idx += lc

            if len(apdu) > idx:
                le_field = apdu[idx:]

        return cla, ins, p1, p2, data_field, le_field

    def _parse_response_tlvs(self, response: bytes) -> tuple[list[tuple[int, bytes, bytes]], bytes]:
        idx = 0
        elements: list[tuple[int, bytes, bytes]] = []

        while idx < len(response):
            if len(response) - idx == 2:
                return elements, response[idx:]

            tag, tag_len = self._read_tag(response, idx)
            idx += tag_len

            length, length_len = self._read_length(response, idx)
            idx += length_len

            value = response[idx : idx + length]
            idx += length

            encoded = self._encode_tlv(tag, value)
            elements.append((tag, value, encoded))

        return elements, b""

    @staticmethod
    def _read_tag(buffer: bytes, offset: int) -> tuple[int, int]:
        first = buffer[offset]
        if first & 0x1F == 0x1F:
            tag = int.from_bytes(buffer[offset : offset + 2], "big")
            return tag, 2
        return first, 1

    @staticmethod
    def _read_length(buffer: bytes, offset: int) -> tuple[int, int]:
        first = buffer[offset]
        if first & 0x80 == 0:
            return first, 1
        num_bytes = first & 0x7F
        length = int.from_bytes(buffer[offset + 1 : offset + 1 + num_bytes], "big")
        return length, 1 + num_bytes

    def _derive_pace_password_key(self, password: str) -> bytes:
        if password.isdigit() and 6 <= len(password) <= 10:
            digest = hashlib.sha1(password.encode("ascii")).digest()
            k_seed = digest[:16]
        else:
            try:
                mrz = MRZParser.parse_mrz(password)
            except MRZException as exc:  # pragma: no cover - validated by caller tests
                msg = f"Unsupported PACE password format: {exc}"
                raise ValueError(msg) from exc

            doc_number = self._normalize_document_number(mrz.document_number)
            doc_cd = MRZParser.calculate_check_digit(doc_number)
            dob_cd = MRZParser.calculate_check_digit(mrz.date_of_birth)
            doe_cd = MRZParser.calculate_check_digit(mrz.date_of_expiry)
            info = f"{doc_number}{doc_cd}{mrz.date_of_birth}{dob_cd}{mrz.date_of_expiry}{doe_cd}".encode(
                "ascii"
            )
            k_seed = hashlib.sha1(info).digest()[:16]

        key = bytearray(k_seed)
        for idx, value in enumerate(key):
            key[idx] = self._adjust_des_parity(value)
        return bytes(key)
