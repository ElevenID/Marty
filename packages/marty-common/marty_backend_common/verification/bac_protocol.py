"""
BAC Protocol Orchestration — ICAO 9303 Part 11

Coordinates the Basic Access Control handshake between an inspection system
(reader) and an eMRTD chip.  Delegates cryptographic primitives to the Rust
``_marty_rs`` bindings (3DES-CBC, retail MAC, BAC key derivation) and
orchestrates the three-message protocol:

  1. Reader  → Chip : GET CHALLENGE  → receive RND.IC (8 bytes)
  2. Reader  → Chip : EXTERNAL AUTHENTICATE(E_ifd, M_ifd) → receive (E_ic, M_ic)
  3. Derive session keys K_s_enc, K_s_mac + Send Sequence Counter (SSC)

After a successful handshake, all subsequent APDUs are wrapped in ISO 7816-4
secure messaging (encrypted with K_s_enc, MACed with K_s_mac, sequenced by SSC).

Does NOT reimplement any crypto — uses the Rust-side ``derive_bac_keys``,
``tdes_cbc_encrypt``, ``tdes_cbc_decrypt``, and ``retail_mac`` functions.
"""

from __future__ import annotations

import logging
import os
import struct
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BAC key material
# ---------------------------------------------------------------------------

@dataclass
class BACKeyMaterial:
    """MRZ-derived BAC key material for a single document."""
    document_number: str
    date_of_birth: str    # YYMMDD
    date_of_expiry: str   # YYMMDD
    k_enc: bytes = b""
    k_mac: bytes = b""

    @classmethod
    def from_mrz(cls, document_number: str, dob: str, doe: str) -> "BACKeyMaterial":
        """Derive BAC keys from MRZ fields.

        Concatenates doc_number+check + dob+check + doe+check,
        then delegates to Rust ``derive_bac_keys``.
        """
        mrz_info = (
            _with_check_digit(document_number.ljust(9, "<"))
            + _with_check_digit(dob)
            + _with_check_digit(doe)
        )
        k_enc, k_mac = _derive_bac_keys_rust(mrz_info)
        return cls(
            document_number=document_number,
            date_of_birth=dob,
            date_of_expiry=doe,
            k_enc=k_enc,
            k_mac=k_mac,
        )


# ---------------------------------------------------------------------------
# BAC Session
# ---------------------------------------------------------------------------

@dataclass
class BACSession:
    """Active BAC session with session keys and SSC."""
    k_s_enc: bytes = b""
    k_s_mac: bytes = b""
    ssc: int = 0   # 8-byte Send Sequence Counter

    def increment_ssc(self) -> bytes:
        """Increment SSC and return its 8-byte big-endian representation."""
        self.ssc += 1
        return struct.pack(">Q", self.ssc)


# ---------------------------------------------------------------------------
# BAC Handshake
# ---------------------------------------------------------------------------

async def perform_bac_handshake(
    key_material: BACKeyMaterial,
    send_apdu_fn,
) -> BACSession:
    """Execute the full BAC mutual authentication protocol.

    Args:
        key_material: MRZ-derived K_enc and K_mac.
        send_apdu_fn: Async callable ``(bytes) -> bytes`` that sends an APDU
            to the chip and returns the response (without SW1/SW2).

    Returns:
        BACSession with derived session keys and initial SSC.

    Raises:
        BACAuthenticationError: If the chip rejects the authentication.
    """
    # Step 1: GET CHALLENGE — obtain 8-byte random from chip (RND.IC)
    get_challenge_apdu = bytes([0x00, 0x84, 0x00, 0x00, 0x08])
    rnd_ic = await send_apdu_fn(get_challenge_apdu)
    if len(rnd_ic) < 8:
        raise BACAuthenticationError("GET CHALLENGE returned < 8 bytes")

    rnd_ic = rnd_ic[:8]

    # Step 2: Build EXTERNAL AUTHENTICATE command
    rnd_ifd = os.urandom(8)   # Reader random
    k_ifd = os.urandom(16)    # Reader key material for session key derivation

    # S = RND.IFD || RND.IC || K.IFD  (32 bytes)
    s_block = rnd_ifd + rnd_ic + k_ifd

    # E_ifd = 3DES-CBC-encrypt(K_enc, S) with zero IV
    e_ifd = _tdes_encrypt(key_material.k_enc, s_block)
    # M_ifd = retail-MAC(K_mac, E_ifd)
    m_ifd = _retail_mac(key_material.k_mac, e_ifd)

    # External Authenticate: CLA=00 INS=82 P1=00 P2=00 Lc=28 data=E_ifd||M_ifd Le=28
    cmd_data = e_ifd + m_ifd  # 32 + 8 = 40 bytes
    ext_auth_apdu = bytes([0x00, 0x82, 0x00, 0x00, len(cmd_data)]) + cmd_data + bytes([0x28])
    response = await send_apdu_fn(ext_auth_apdu)

    if len(response) < 40:
        raise BACAuthenticationError(
            f"EXTERNAL AUTHENTICATE response too short: {len(response)} bytes"
        )

    e_ic = response[:32]
    m_ic = response[32:40]

    # Verify MAC on chip response
    expected_mac = _retail_mac(key_material.k_mac, e_ic)
    if not _constant_time_compare(m_ic, expected_mac):
        raise BACAuthenticationError("MAC verification failed on chip response")

    # Decrypt chip response
    r_block = _tdes_decrypt(key_material.k_enc, e_ic)
    rnd_ic_resp = r_block[:8]
    rnd_ifd_resp = r_block[8:16]
    k_ic = r_block[16:32]

    # Verify the chip echoed our nonces correctly
    if rnd_ifd_resp != rnd_ifd:
        raise BACAuthenticationError("Chip did not echo RND.IFD correctly")
    if rnd_ic_resp != rnd_ic:
        raise BACAuthenticationError("Chip did not echo RND.IC correctly")

    # Step 3: Derive session keys
    # K_seed_session = K.IFD XOR K.IC
    k_seed = bytes(a ^ b for a, b in zip(k_ifd, k_ic))

    k_s_enc, k_s_mac = _derive_session_keys(k_seed)

    # Initial SSC = last 4 bytes of RND.IC || last 4 bytes of RND.IFD
    ssc_bytes = rnd_ic[4:8] + rnd_ifd[4:8]
    ssc = int.from_bytes(ssc_bytes, "big")

    logger.info("BAC handshake completed successfully")
    return BACSession(k_s_enc=k_s_enc, k_s_mac=k_s_mac, ssc=ssc)


# ---------------------------------------------------------------------------
# Secure Messaging (SM)
# ---------------------------------------------------------------------------

def build_protected_apdu(
    session: BACSession,
    cla: int,
    ins: int,
    p1: int,
    p2: int,
    data: bytes | None = None,
    le: int | None = None,
) -> bytes:
    """Wrap a command APDU in ISO 7816-4 secure messaging.

    Encrypts the data field with K_s_enc, MACs the entire command with K_s_mac,
    and increments the SSC.
    """
    ssc_bytes = session.increment_ssc()

    # Build the padded command header for MAC input
    # CLA is OR'd with 0x0C to indicate secure messaging
    sm_cla = cla | 0x0C
    cmd_header = bytes([sm_cla, ins, p1, p2])
    padded_header = _iso7816_pad(cmd_header)

    do87 = b""  # Encrypted data object
    do97 = b""  # Expected length object

    if data:
        # Pad and encrypt data
        padded_data = _iso7816_pad(data)
        encrypted = _tdes_encrypt(session.k_s_enc, padded_data)
        # TLV: tag 0x87, length, 0x01 (padding indicator) + encrypted data
        content = b"\x01" + encrypted
        do87 = b"\x87" + _ber_length(len(content)) + content

    if le is not None:
        do97 = b"\x97\x01" + bytes([le & 0xFF])

    # MAC input: SSC || padded header || DO87 || DO97
    mac_input = ssc_bytes + padded_header + do87 + do97
    if len(mac_input) % 8 != 0:
        mac_input = _iso7816_pad(mac_input)

    mac_value = _retail_mac(session.k_s_mac, mac_input)
    do8e = b"\x8E\x08" + mac_value

    # Assemble the protected APDU
    sm_data = do87 + do97 + do8e
    return bytes([sm_cla, ins, p1, p2, len(sm_data)]) + sm_data + b"\x00"


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class BACAuthenticationError(Exception):
    """Raised when BAC mutual authentication fails."""


# ---------------------------------------------------------------------------
# Internal helpers — delegate to Rust or pure-Python fallback
# ---------------------------------------------------------------------------

def _compute_check_digit(data: str) -> str:
    """ICAO 9303 check digit computation (Part 3 §4.3)."""
    weights = [7, 3, 1]
    total = 0
    for i, ch in enumerate(data):
        if ch == "<":
            val = 0
        elif ch.isdigit():
            val = int(ch)
        elif ch.isalpha():
            val = ord(ch.upper()) - 55  # A=10, B=11, ...
        else:
            val = 0
        total += val * weights[i % 3]
    return str(total % 10)


def _with_check_digit(data: str) -> str:
    """Append ICAO check digit to a data field."""
    return data + _compute_check_digit(data)


def _derive_bac_keys_rust(mrz_info: str) -> tuple[bytes, bytes]:
    """Delegate BAC key derivation to Rust bindings."""
    try:
        from marty_rs import _marty_rs
        k_enc, k_mac = _marty_rs.derive_bac_keys(mrz_info)
        return bytes(k_enc), bytes(k_mac)
    except ImportError:
        logger.warning("Rust bindings unavailable — using Python fallback for BAC keys")
        return _derive_bac_keys_python(mrz_info)


def _derive_bac_keys_python(mrz_info: str) -> tuple[bytes, bytes]:
    """Pure-Python fallback for BAC key derivation (ICAO 9303 Part 11)."""
    import hashlib
    h = hashlib.sha1(mrz_info.encode("ascii")).digest()
    k_seed = h[:16]
    k_enc = _derive_3des_key_python(k_seed, b"\x00\x00\x00\x01")
    k_mac = _derive_3des_key_python(k_seed, b"\x00\x00\x00\x02")
    return k_enc, k_mac


def _derive_3des_key_python(k_seed: bytes, counter: bytes) -> bytes:
    """Derive a 16-byte 3DES key from seed + counter with parity adjustment."""
    import hashlib
    h = hashlib.sha1(k_seed + counter).digest()
    key = bytearray(h[:16])
    for i in range(len(key)):
        key[i] = _adjust_parity_byte(key[i])
    return bytes(key)


def _adjust_parity_byte(b: int) -> int:
    """Adjust a single byte for DES odd parity."""
    b &= 0xFE
    parity = bin(b).count("1") % 2
    return b | (0 if parity else 1)


def _derive_session_keys(k_seed: bytes) -> tuple[bytes, bytes]:
    """Derive session keys from XOR'd seed material."""
    return _derive_bac_keys_python(k_seed.hex().upper())


def _tdes_encrypt(key: bytes, data: bytes) -> bytes:
    """3DES-CBC encrypt with zero IV. Delegates to Rust if available."""
    try:
        from marty_rs import _marty_rs
        return bytes(_marty_rs.tdes_cbc_encrypt(key, data, bytes(8)))
    except ImportError:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        cipher = Cipher(algorithms.TripleDES(key + key[:8]), modes.CBC(bytes(8)))
        enc = cipher.encryptor()
        return enc.update(data) + enc.finalize()


def _tdes_decrypt(key: bytes, data: bytes) -> bytes:
    """3DES-CBC decrypt with zero IV. Delegates to Rust if available."""
    try:
        from marty_rs import _marty_rs
        return bytes(_marty_rs.tdes_cbc_decrypt(key, data, bytes(8)))
    except ImportError:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        cipher = Cipher(algorithms.TripleDES(key + key[:8]), modes.CBC(bytes(8)))
        dec = cipher.decryptor()
        return dec.update(data) + dec.finalize()


def _retail_mac(key: bytes, data: bytes) -> bytes:
    """ISO 9797-1 Algorithm 3 retail MAC (8 bytes). Delegates to Rust if available."""
    try:
        from marty_rs import _marty_rs
        return bytes(_marty_rs.retail_mac(key, data))
    except ImportError:
        # Python fallback — single-DES CBC MAC then final 3DES step
        padded = _iso7816_pad(data)
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        k1 = key[:8]
        # Initial CBC-MAC with K1
        cipher = Cipher(algorithms.TripleDES(k1 + k1 + k1), modes.CBC(bytes(8)))
        enc = cipher.encryptor()
        ct = enc.update(padded) + enc.finalize()
        intermediate = ct[-8:]  # last block
        # Final 3DES step with full key
        cipher2 = Cipher(algorithms.TripleDES(key + key[:8]), modes.ECB())
        enc2 = cipher2.encryptor()
        return (enc2.update(intermediate) + enc2.finalize())[:8]


def _iso7816_pad(data: bytes) -> bytes:
    """ISO 7816-4 padding: append 0x80 then 0x00 bytes to next 8-byte boundary."""
    padded = data + b"\x80"
    while len(padded) % 8 != 0:
        padded += b"\x00"
    return padded


def _ber_length(length: int) -> bytes:
    """BER-TLV length encoding."""
    if length < 0x80:
        return bytes([length])
    elif length < 0x100:
        return bytes([0x81, length])
    else:
        return bytes([0x82, (length >> 8) & 0xFF, length & 0xFF])


def _constant_time_compare(a: bytes, b: bytes) -> bool:
    """Constant-time byte comparison to prevent timing attacks."""
    import hmac as _hmac
    return _hmac.compare_digest(a, b)
