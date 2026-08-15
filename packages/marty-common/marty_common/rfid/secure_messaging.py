"""Secure messaging primitives for ICAO Doc 9303 communication."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

# Use crypto_bridge for Rust-backed cryptographic operations
from marty_common.crypto_bridge import (
    p256_agree,
    p256_generate,
    tdes_cbc_decrypt,
)
from marty_common.native_backends import load_native_backend
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
        backend = load_native_backend("marty_verification", ("NativeBacSession",))
        self._native_bac = backend.NativeBacSession()
        self._pace_state: _PACEState | None = None
        self.logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # BAC key derivation and mutual authentication
    # ------------------------------------------------------------------
    def derive_bac_keys(
        self, passport_number: str, date_of_birth: str, date_of_expiry: str
    ) -> BACKeys:
        """Derive BAC master keys from MRZ data (ICAO Doc 9303 6.1.1)."""

        keys = self._call_native(
            self._native_bac.derive_bac_keys,
            passport_number,
            date_of_birth,
            date_of_expiry,
        )
        return BACKeys(k_enc=keys["k_enc"], k_mac=keys["k_mac"], k_seed=keys["k_seed"])

    def perform_basic_access_control(self, bac_keys: BACKeys, challenge: bytes) -> bytes:
        """Create mutual authentication command for BAC (ICAO Doc 9303 6.2)."""

        return self._call_native(
            self._native_bac.start_bac_with_keys,
            bac_keys.k_enc,
            bac_keys.k_mac,
            bac_keys.k_seed,
            challenge,
        )

    def complete_basic_access_control(self, bac_keys: BACKeys, response: bytes) -> SessionKeys:
        """Validate chip response and derive BAC session keys."""

        del bac_keys
        return self._set_session_keys(self._call_native(self._native_bac.finish_bac, response))

    def derive_session_keys(
        self, k_ifd: bytes, k_ic: bytes, rnd_ic: bytes, rnd_ifd: bytes
    ) -> SessionKeys:
        """Derive secure messaging keys from BAC shared secrets."""

        return self._set_session_keys(
            self._call_native(self._native_bac.derive_session_keys, k_ifd, k_ic, rnd_ic, rnd_ifd)
        )

    # ------------------------------------------------------------------
    # Secure messaging APDU protection (ISO 7816-4 + ICAO Doc 9303 6.3)
    # ------------------------------------------------------------------
    def encrypt_command(self, apdu: bytes) -> bytes:
        """Protect command APDU using current session keys."""

        self._sync_native_session()
        protected = self._call_native(self._native_bac.protect_command, apdu)
        self._refresh_session_keys()
        return protected

    def decrypt_response(self, response: bytes) -> bytes:
        """Verify and decrypt protected response APDU."""

        self._sync_native_session()
        plaintext = self._call_native(self._native_bac.unprotect_response, response)
        self._refresh_session_keys()
        return plaintext

    def _set_session_keys(self, native_keys: dict) -> SessionKeys:
        self.session_keys = SessionKeys(
            k_s_enc=native_keys["k_s_enc"],
            k_s_mac=native_keys["k_s_mac"],
            ssc=native_keys["ssc"],
        )
        return self.session_keys

    @staticmethod
    def _call_native(operation, *args):
        try:
            return operation(*args)
        except (RuntimeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc

    def _sync_native_session(self) -> None:
        if not self.session_keys:
            msg = "Session keys not established"
            raise ValueError(msg)
        self._call_native(
            self._native_bac.set_session_keys,
            self.session_keys.k_s_enc,
            self.session_keys.k_s_mac,
            self.session_keys.ssc,
        )

    def _refresh_session_keys(self) -> None:
        self._set_session_keys(self._call_native(self._native_bac.session_keys))

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

    def _decrypt_3des_cbc(self, data: bytes, key: bytes, iv: bytes | None = None) -> bytes:
        iv = iv or b"\x00" * 8
        # Use Rust-backed 3DES-CBC decryption via crypto_bridge
        return tdes_cbc_decrypt(self._expand_3des_key(key), data, iv)

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
