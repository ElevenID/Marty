"""Active Authentication Protocol Implementation.

Implements ICAO Doc 9303 Active Authentication for preventing passport chip cloning
and replay attacks. Uses challenge-response protocol with chip's private key.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

# Use crypto_bridge for ISO 9796-2 operations (Rust implementation - required)
from marty_common.crypto_bridge import iso9796_recover

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric import rsa

logger = logging.getLogger(__name__)


@dataclass
class ActiveAuthenticationChallenge:
    """Active Authentication challenge data."""

    challenge: bytes
    hash_algorithm: str
    key_size: int
    timestamp: int | None = None


@dataclass
class ActiveAuthenticationResponse:
    """Active Authentication response from chip."""

    signature: bytes
    recovered_message: bytes | None = None
    trailer: bytes | None = None
    is_valid: bool = False


class ActiveAuthenticationProtocol:
    """Implements ICAO Active Authentication protocol."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        # Supported hash algorithms mapped to crypto_bridge names
        self.supported_hash_algorithms = {
            "SHA-1": "sha1",
            "SHA-224": "sha224",
            "SHA-256": "sha256",
            "SHA-384": "sha384",
            "SHA-512": "sha512",
        }

    def generate_challenge(
        self, key_size: int = 128, hash_algorithm: str = "SHA-256"
    ) -> ActiveAuthenticationChallenge:
        """Generate random challenge for Active Authentication.

        Args:
            key_size: Size of challenge in bits (default 128)
            hash_algorithm: Hash algorithm to use (default SHA-256)

        Returns:
            ActiveAuthenticationChallenge containing random data
        """
        if hash_algorithm not in self.supported_hash_algorithms:
            msg = f"Unsupported hash algorithm: {hash_algorithm}"
            raise ValueError(msg)

        challenge_bytes = key_size // 8
        challenge = os.urandom(challenge_bytes)

        self.logger.debug("Generated %d-bit AA challenge", key_size)

        return ActiveAuthenticationChallenge(
            challenge=challenge, hash_algorithm=hash_algorithm, key_size=key_size
        )

    def create_aa_apdu_command(self, challenge: ActiveAuthenticationChallenge) -> bytes:
        """Create APDU command for Active Authentication.

        Args:
            challenge: Challenge data to send to chip

        Returns:
            APDU command bytes for Internal Authenticate
        """
        # INTERNAL AUTHENTICATE command (ISO 7816-4)
        cla = 0x00  # Class byte
        ins = 0x88  # Internal Authenticate instruction
        p1 = 0x00  # Algorithm reference (placeholder)
        p2 = 0x00  # Reference control parameter

        # Data field contains challenge
        lc = len(challenge.challenge)
        le = 0x00  # Maximum expected response length

        apdu = bytes([cla, ins, p1, p2, lc]) + challenge.challenge + bytes([le])

        self.logger.debug("Created AA APDU command: %s", apdu.hex())
        return apdu

    def parse_aa_response(
        self, response_data: bytes, challenge: ActiveAuthenticationChallenge
    ) -> ActiveAuthenticationResponse:
        """Parse Active Authentication response from chip.

        Args:
            response_data: Raw APDU response from chip
            challenge: Original challenge sent to chip

        Returns:
            ActiveAuthenticationResponse with parsed signature data
        """
        if len(response_data) < 2:
            msg = "AA response too short"
            raise ValueError(msg)

        # Check status word (last 2 bytes)
        status_word = response_data[-2:]
        if status_word != b"\x90\x00":
            msg = f"AA command failed with status: {status_word.hex()}"
            raise ValueError(msg)

        # Extract signature (all but last 2 bytes)
        signature = response_data[:-2]

        if len(signature) == 0:
            msg = "No signature data in AA response"
            raise ValueError(msg)

        self.logger.debug("Parsed AA response: %d bytes signature", len(signature))

        return ActiveAuthenticationResponse(
            signature=signature,
            is_valid=False,  # Will be validated separately
        )

    def verify_active_authentication(
        self,
        response: ActiveAuthenticationResponse,
        challenge: ActiveAuthenticationChallenge,
        public_key: "rsa.RSAPublicKey",
    ) -> bool:
        """Verify Active Authentication response using ISO 9796-2 scheme.

        Args:
            response: AA response from chip
            challenge: Original challenge
            public_key: Chip's public key from DG15

        Returns:
            True if verification successful, False otherwise
        """
        try:
            # Get the hash algorithm name for crypto_bridge
            hash_algo = self.supported_hash_algorithms.get(challenge.hash_algorithm, "sha256")
            
            # Convert public key to DER format for crypto_bridge
            from cryptography.hazmat.primitives import serialization
            public_key_der = public_key.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            
            # Recover message using Rust ISO 9796-2 implementation
            try:
                recovered_message = iso9796_recover(
                    public_key_der=public_key_der,
                    signature=response.signature,
                    scheme=1,  # ISO 9796-2 scheme 1 for Active Authentication
                    hash_algorithm=hash_algo,
                )
            except ValueError as e:
                self.logger.warning("ISO 9796-2 recovery failed: %s", e)
                recovered_message = None

            if not recovered_message:
                self.logger.warning("Failed to recover message from AA signature")
                return False

            # Verify the recovered message contains our challenge
            is_valid = self._verify_challenge_in_message(recovered_message, challenge)

            if is_valid:
                response.recovered_message = recovered_message
                response.is_valid = True
                self.logger.info("Active Authentication verification successful")
            else:
                self.logger.warning("Challenge verification failed in AA response")

        except Exception as e:
            self.logger.exception("AA verification failed: %s", str(e))
            return False
        else:
            return is_valid

    def _verify_challenge_in_message(
        self, message: bytes, challenge: ActiveAuthenticationChallenge
    ) -> bool:
        """Verify that the recovered message contains our challenge."""
        # In Active Authentication, the message should contain:
        # 1. The challenge we sent
        # 2. Possibly additional data (M1 + M2 in ISO 9796-2 terms)

        # Simple verification: challenge should be present in message
        if challenge.challenge in message:
            return True

        # More sophisticated verification would check the exact format
        # required by ICAO Doc 9303 and ISO 9796-2

        return False

    def _parse_iso9796_structure(self, recovered_bytes: bytes) -> bytes | None:
        """Parse ISO 9796-2 message structure.

        ISO 9796-2 format:
        - Header: 0x6A (partial recovery) or 0x4A (total recovery)
        - Message: Variable length
        - Hash: Hash of complete message
        - Trailer: 0xBC, hash function identifier
        """
        if len(recovered_bytes) < 3:
            return None

        # Check for valid header
        header = recovered_bytes[0]
        if header not in (0x6A, 0x4A):
            self.logger.debug("Invalid ISO 9796-2 header: 0x%02X", header)
            return None

        # Check for valid trailer
        if recovered_bytes[-1] != 0xBC:
            self.logger.debug("Invalid ISO 9796-2 trailer: 0x%02X", recovered_bytes[-1])
            return None

        # Hash function identifier (second-to-last byte)
        hash_id = recovered_bytes[-2]

        # Extract message (between header and hash+trailer)
        # This is simplified - real implementation needs to handle
        # hash length based on hash_id
        hash_length = self._get_hash_length_from_id(hash_id)
        if hash_length is None:
            return None

        message_end = len(recovered_bytes) - hash_length - 2
        if message_end <= 1:
            return None

        message = recovered_bytes[1:message_end]
        message_hash = recovered_bytes[message_end : message_end + hash_length]

        # Verify hash (simplified)
        computed_hash = self._compute_hash_by_id(hash_id, message)
        if computed_hash and computed_hash == message_hash:
            return message

        return None

    def _get_hash_length_from_id(self, hash_id: int) -> int | None:
        """Get hash length from ISO 9796-2 hash identifier."""
        hash_lengths = {
            0x33: 20,  # SHA-1
            0x34: 28,  # SHA-224
            0x31: 32,  # SHA-256
            0x32: 48,  # SHA-384
            0x35: 64,  # SHA-512
        }
        return hash_lengths.get(hash_id)

    def _compute_hash_by_id(self, hash_id: int, data: bytes) -> bytes | None:
        """Compute hash using algorithm specified by ID."""
        hash_algorithms = {
            0x33: hashlib.sha1,
            0x34: hashlib.sha224,
            0x31: hashlib.sha256,
            0x32: hashlib.sha384,
            0x35: hashlib.sha512,
        }

        hash_func = hash_algorithms.get(hash_id)
        if hash_func:
            return hash_func(data).digest()
        return None

    def _verify_challenge_in_message(
        self, message: bytes, challenge: ActiveAuthenticationChallenge
    ) -> bool:
        """Verify that the recovered message contains our challenge."""
        # In Active Authentication, the message should contain:
        # 1. The challenge we sent
        # 2. Possibly additional data (M1 + M2 in ISO 9796-2 terms)

        # Simple verification: challenge should be present in message
        if challenge.challenge in message:
            return True

        # More sophisticated verification would check the exact format
        # required by ICAO Doc 9303 and ISO 9796-2

        return False

    def create_mock_aa_response(
        self, challenge: ActiveAuthenticationChallenge, private_key: "rsa.RSAPrivateKey"
    ) -> bytes:
        """Create mock Active Authentication response for testing.

        Args:
            challenge: Challenge to respond to
            private_key: Mock private key for signing

        Returns:
            APDU response bytes with signature + status word
        """
        try:
            # Create ISO 9796-2 formatted message
            message = self._create_iso9796_message(challenge)

            # Sign with private key
            signature = self._sign_iso9796_message(message, private_key)

            # Return signature + success status word
            return signature + b"\x90\x00"

        except Exception as e:
            self.logger.exception("Failed to create mock AA response: %s", str(e))
            # Return error status
            return b"\x69\x82"  # Security status not satisfied

    def _create_iso9796_message(self, challenge: ActiveAuthenticationChallenge) -> bytes:
        """Create ISO 9796-2 formatted message for signing."""
        # Header for partial recovery
        header = b"\x6a"

        # Message contains the challenge
        message_data = challenge.challenge

        # Hash the message
        hash_func = hashlib.sha256  # Use SHA-256
        message_hash = hash_func(message_data).digest()

        # Hash function identifier for SHA-256
        hash_id = b"\x31"

        # Trailer
        trailer = b"\xbc"

        return header + message_data + message_hash + hash_id + trailer

    def _sign_iso9796_message(self, message: bytes, private_key: "rsa.RSAPrivateKey") -> bytes:
        """Sign ISO 9796-2 message (simplified implementation)."""
        # Convert message to integer
        message_int = int.from_bytes(message, "big")

        # Pad to key size if necessary
        key_size_bytes = (private_key.key_size + 7) // 8
        if len(message) < key_size_bytes:
            # Pad with zeros on the left
            padding_length = key_size_bytes - len(message)
            padded_message = b"\x00" * padding_length + message
            message_int = int.from_bytes(padded_message, "big")

        # Sign using private key (simplified RSA operation)
        private_numbers = private_key.private_numbers()
        signature_int = pow(
            message_int, private_numbers.private_exponent, private_numbers.public_numbers.n
        )

        # Convert to bytes
        return signature_int.to_bytes(key_size_bytes, "big")


class ActiveAuthenticationManager:
    """Manages Active Authentication operations for passport verification."""

    def __init__(self) -> None:
        self.protocol = ActiveAuthenticationProtocol()
        self.logger = logging.getLogger(__name__)

    def perform_active_authentication(self, reader, public_key: "rsa.RSAPublicKey") -> bool:
        """Perform complete Active Authentication with passport chip.

        Args:
            reader: RFID reader interface
            public_key: Chip's public key from DG15

        Returns:
            True if authentication successful, False otherwise
        """
        try:
            # Generate challenge
            challenge = self.protocol.generate_challenge()

            # Send challenge to chip
            aa_command = self.protocol.create_aa_apdu_command(challenge)
            response_data = reader.transmit_apdu(aa_command)

            # Parse response
            aa_response = self.protocol.parse_aa_response(response_data, challenge)

            # Verify response
            is_valid = self.protocol.verify_active_authentication(
                aa_response, challenge, public_key
            )

            if is_valid:
                self.logger.info("Active Authentication successful")
            else:
                self.logger.warning("Active Authentication failed")

        except Exception as e:
            self.logger.exception("Active Authentication error: %s", str(e))
            return False
        else:
            return is_valid

    def verify_chip_authenticity(
        self, reader, public_key: "rsa.RSAPublicKey", num_rounds: int = 3
    ) -> bool:
        """Verify chip authenticity using multiple AA rounds.

        Args:
            reader: RFID reader interface
            public_key: Chip's public key
            num_rounds: Number of authentication rounds

        Returns:
            True if all rounds successful, False otherwise
        """
        success_count = 0

        for round_num in range(num_rounds):
            self.logger.debug("AA round %d/%d", round_num + 1, num_rounds)

            if self.perform_active_authentication(reader, public_key):
                success_count += 1
            else:
                self.logger.warning("AA round %d failed", round_num + 1)

        # Require all rounds to succeed
        is_authentic = success_count == num_rounds

        self.logger.info(
            "Chip authenticity check: %d/%d rounds successful", success_count, num_rounds
        )

        return is_authentic
