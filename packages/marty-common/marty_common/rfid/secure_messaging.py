"""Secure messaging primitives for ICAO Doc 9303 communication."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from marty_common.native_backends import load_native_backend

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


class SecureMessaging:
    """Implements ICAO-compliant BAC/PACE secure messaging."""

    def __init__(self) -> None:
        self.session_keys: SessionKeys | None = None
        backend = load_native_backend(
            "marty_verification", ("NativeBacSession", "NativePaceSession")
        )
        self._native_bac = backend.NativeBacSession()
        self._native_pace = backend.NativePaceSession()
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
    # PACE compatibility handshake
    # ------------------------------------------------------------------
    def setup_pace_protocol(
        self,
        password: str,
        nonce: bytes,
        curve: str = "p256",  # Currently only P-256 supported
    ) -> bytes:
        """Start PACE handshake and return the reader public key."""

        return self._call_native(self._native_pace.start_pace, password, nonce, curve)

    def complete_pace_protocol(self, chip_public_key: bytes) -> SessionKeys:
        """Finish PACE handshake using chip public key."""

        return self._set_session_keys(
            self._call_native(self._native_pace.complete_pace, chip_public_key)
        )

    def _derive_pace_password_key(self, password: str) -> bytes:
        return self._call_native(self._native_pace.derive_password_key, password)
