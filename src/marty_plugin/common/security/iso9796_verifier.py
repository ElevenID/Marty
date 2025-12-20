"""ISO 9796-2 Digital Signature Verification.

Implements ISO/IEC 9796-2 digital signature schemes with message recovery
for verifying Active Authentication responses from passport chips.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from cryptography.hazmat.primitives.asymmetric import rsa

logger = logging.getLogger(__name__)


class ISO9796Scheme(Enum):
    """ISO 9796-2 signature schemes."""

    SCHEME_1 = 1  # Signature scheme giving message recovery
    SCHEME_2 = 2  # Signature scheme with appendix
    SCHEME_3 = 3  # Certificate recovery scheme


class HashFunction(Enum):
    """Supported hash functions for ISO 9796-2."""

    SHA1 = (0x33, hashlib.sha1, 20)
    SHA224 = (0x34, hashlib.sha224, 28)
    SHA256 = (0x31, hashlib.sha256, 32)
    SHA384 = (0x32, hashlib.sha384, 48)
    SHA512 = (0x35, hashlib.sha512, 64)

    def __init__(self, identifier: int, hash_func: Any, digest_length: int) -> None:
        self.identifier = identifier
        self.hash_func = hash_func
        self.digest_length = digest_length


@dataclass
class ISO9796SignatureData:
    """Parsed ISO 9796-2 signature data."""

    scheme: ISO9796Scheme
    hash_function: HashFunction
    recovered_message: bytes
    message_hash: bytes
    is_valid: bool = False
    trailer: bytes | None = None


class ISO9796Verifier:
    """ISO/IEC 9796-2 signature verifier for passport Active Authentication."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.hash_functions = {hf.identifier: hf for hf in HashFunction}

    def verify_signature(
        self,
        signature: bytes,
        message: bytes,
        public_key: rsa.RSAPublicKey,
        scheme: ISO9796Scheme = ISO9796Scheme.SCHEME_1,
    ) -> ISO9796SignatureData:
        """Verify ISO 9796-2 signature with message recovery.

        Args:
            signature: Digital signature bytes
            message: Original message that was signed
            public_key: RSA public key for verification
            scheme: ISO 9796-2 scheme to use

        Returns:
            ISO9796SignatureData with verification results
        """
        try:
            if scheme == ISO9796Scheme.SCHEME_1:
                return self._verify_scheme_1(signature, message, public_key)
            if scheme == ISO9796Scheme.SCHEME_2:
                return self._verify_scheme_2(signature, message, public_key)
            msg = f"ISO 9796-2 scheme {scheme} not implemented"
            raise ValueError(msg)

        except Exception:
            self.logger.exception("ISO 9796-2 signature verification failed")
            return ISO9796SignatureData(
                scheme=scheme,
                hash_function=HashFunction.SHA256,
                recovered_message=b"",
                message_hash=b"",
                is_valid=False,
            )

    def _verify_scheme_1(
        self, signature: bytes, message: bytes, public_key: rsa.RSAPublicKey
    ) -> ISO9796SignatureData:
        """Verify ISO 9796-2 Scheme 1 (signature with message recovery).

        Scheme 1 format after RSA verification:
        Header || M1 || H(M) || M2 || Trailer

        Where:
        - Header: 0x6A (partial recovery) or 0x4A (total recovery)
        - M1: Recovered part of message
        - H(M): Hash of complete message M = M1 || M2
        - M2: Non-recovered part of message (may be empty)
        - Trailer: 0xBC || Hash identifier
        """
        # Step 1: RSA verification to recover the formatted message
        recovered_data = self._rsa_verify_with_recovery(signature, public_key)
        if not recovered_data:
            return self._create_invalid_result(ISO9796Scheme.SCHEME_1)

        # Step 2: Parse the ISO 9796-2 structure
        parsed_data = self._parse_scheme_1_structure(recovered_data)
        if not parsed_data:
            return self._create_invalid_result(ISO9796Scheme.SCHEME_1)

        header, m1, message_hash, hash_function, trailer = parsed_data

        # Step 3: Reconstruct complete message and verify hash
        if header == 0x6A:  # Partial recovery
            # M2 is not recovered, assume it's the remaining part of original message
            if len(message) > len(m1):
                m2 = message[len(m1) :]
                complete_message = m1 + m2
            else:
                complete_message = m1
        else:  # Total recovery (header == 0x4A)
            complete_message = m1
            m2 = b""

        # Step 4: Verify the hash
        computed_hash = hash_function.hash_func(complete_message).digest()
        hash_valid = computed_hash == message_hash

        self.logger.debug("ISO 9796-2 Scheme 1 verification: hash_valid=%s", hash_valid)

        return ISO9796SignatureData(
            scheme=ISO9796Scheme.SCHEME_1,
            hash_function=hash_function,
            recovered_message=complete_message,
            message_hash=message_hash,
            is_valid=hash_valid,
            trailer=trailer,
        )

    def _verify_scheme_2(
        self, signature: bytes, message: bytes, public_key: rsa.RSAPublicKey
    ) -> ISO9796SignatureData:
        """Verify ISO 9796-2 Scheme 2 (signature with appendix).

        Scheme 2 is similar to traditional RSA-PSS but follows ISO 9796-2 format.
        The message is not recovered from the signature.
        """
        # This is a simplified implementation
        # Full Scheme 2 would require more complex padding verification

        try:
            # Use standard RSA verification for Scheme 2
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding

            # Try to verify with PKCS1v15 padding (common for passport chips)
            public_key.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())

            return ISO9796SignatureData(
                scheme=ISO9796Scheme.SCHEME_2,
                hash_function=HashFunction.SHA256,
                recovered_message=message,
                message_hash=hashlib.sha256(message).digest(),
                is_valid=True,
            )

        except Exception:
            self.logger.warning("ISO 9796-2 Scheme 2 verification failed")
            return self._create_invalid_result(ISO9796Scheme.SCHEME_2)

    def _rsa_verify_with_recovery(
        self, signature: bytes, public_key: rsa.RSAPublicKey
    ) -> bytes | None:
        """Perform RSA verification with message recovery."""
        try:
            # Convert signature to integer
            signature_int = int.from_bytes(signature, "big")

            # Get public key components
            public_numbers = public_key.public_numbers()
            n = public_numbers.n
            e = public_numbers.e

            # Perform RSA operation: signature^e mod n
            recovered_int = pow(signature_int, e, n)

            # Convert back to bytes with correct length
            key_size_bytes = (public_key.key_size + 7) // 8
            recovered_bytes = recovered_int.to_bytes(key_size_bytes, "big")

        except Exception as e:
            self.logger.exception("RSA recovery failed: %s", str(e))
            return None
        else:
            return recovered_bytes

    def _parse_scheme_1_structure(
        self, data: bytes
    ) -> tuple[int, bytes, bytes, HashFunction, bytes] | None:
        """Parse ISO 9796-2 Scheme 1 structure from recovered data.

        Returns:
            Tuple of (header, m1, message_hash, hash_function, trailer) or None
        """
        if len(data) < 4:  # Minimum: header + hash + hash_id + trailer
            return None

        # Parse header
        header = data[0]
        if header not in (0x4A, 0x6A):
            self.logger.debug("Invalid ISO 9796-2 header: 0x%02X", header)
            return None

        # Parse trailer (last 2 bytes)
        if data[-1] != 0xBC:
            self.logger.debug("Invalid ISO 9796-2 trailer: 0x%02X", data[-1])
            return None

        hash_id = data[-2]
        hash_function = self.hash_functions.get(hash_id)
        if not hash_function:
            self.logger.debug("Unknown hash function ID: 0x%02X", hash_id)
            return None

        trailer = data[-2:]

        # Calculate positions
        hash_length = hash_function.digest_length
        if len(data) < 1 + hash_length + 2:
            self.logger.debug("Data too short for hash length %d", hash_length)
            return None

        # Extract message hash
        hash_start = len(data) - hash_length - 2
        message_hash = data[hash_start : hash_start + hash_length]

        # Extract M1 (recovered message part)
        m1 = data[1:hash_start]

        return header, m1, message_hash, hash_function, trailer

    def _create_invalid_result(self, scheme: ISO9796Scheme) -> ISO9796SignatureData:
        """Create invalid signature result."""
        return ISO9796SignatureData(
            scheme=scheme,
            hash_function=HashFunction.SHA256,
            recovered_message=b"",
            message_hash=b"",
            is_valid=False,
        )

    def create_test_signature(
        self,
        message: bytes,
        private_key: rsa.RSAPrivateKey,
        hash_function: HashFunction = HashFunction.SHA256,
    ) -> bytes:
        """Create ISO 9796-2 Scheme 1 signature for testing.

        Args:
            message: Message to sign
            private_key: RSA private key
            hash_function: Hash function to use

        Returns:
            ISO 9796-2 formatted signature
        """
        try:
            # Create ISO 9796-2 Scheme 1 structure
            header = 0x6A  # Partial recovery
            message_hash = hash_function.hash_func(message).digest()
            hash_id = hash_function.identifier
            trailer = 0xBC

            # For simplicity, put entire message in M1 (recovered part)
            m1 = message

            # Construct the structure: Header || M1 || H(M) || Hash_ID || Trailer
            structure = bytes([header]) + m1 + message_hash + bytes([hash_id, trailer])

            # Pad to key size if needed
            key_size_bytes = (private_key.key_size + 7) // 8
            if len(structure) < key_size_bytes:
                # Pad with zeros at the beginning
                padding_length = key_size_bytes - len(structure)
                padded_structure = b"\x00" * padding_length + structure
            else:
                padded_structure = structure

            # Convert to integer and sign
            structure_int = int.from_bytes(padded_structure, "big")
            private_numbers = private_key.private_numbers()
            signature_int = pow(
                structure_int, private_numbers.private_exponent, private_numbers.public_numbers.n
            )

            # Convert to bytes
            signature = signature_int.to_bytes(key_size_bytes, "big")

        except Exception as e:
            self.logger.exception("Failed to create test signature: %s", str(e))
            return b""
        else:
            return signature


class PassportActiveAuthenticationVerifier:
    """High-level verifier for passport Active Authentication using ISO 9796-2."""

    def __init__(self) -> None:
        self.iso9796_verifier = ISO9796Verifier()
        self.logger = logging.getLogger(__name__)

    def verify_active_authentication_response(
        self, challenge: bytes, signature: bytes, public_key: rsa.RSAPublicKey
    ) -> bool:
        """Verify Active Authentication response from passport chip.

        Args:
            challenge: Original challenge sent to chip
            signature: Signature response from chip
            public_key: Chip's public key from DG15

        Returns:
            True if verification successful, False otherwise
        """
        try:
            # Verify the signature using ISO 9796-2 Scheme 1
            result = self.iso9796_verifier.verify_signature(
                signature, challenge, public_key, ISO9796Scheme.SCHEME_1
            )

            if not result.is_valid:
                self.logger.warning("ISO 9796-2 signature verification failed")
                return False

            # Check that the recovered message contains our challenge
            if challenge in result.recovered_message:
                self.logger.info("Active Authentication verification successful")
                return True

            self.logger.warning("Challenge not found in recovered message")

        except Exception as e:
            self.logger.exception("Active Authentication verification error: %s", str(e))
            return False
        else:
            return False

    def analyze_signature_structure(
        self, signature: bytes, public_key: rsa.RSAPublicKey
    ) -> dict[str, Any]:
        """Analyze the structure of an ISO 9796-2 signature.

        Args:
            signature: Signature to analyze
            public_key: Public key for verification

        Returns:
            Dictionary with analysis results
        """
        analysis = {
            "signature_length": len(signature),
            "key_size": public_key.key_size,
            "scheme_detected": None,
            "hash_function": None,
            "structure_valid": False,
            "recovery_successful": False,
        }

        try:
            # Try to recover data using RSA
            recovered_data = self.iso9796_verifier._rsa_verify_with_recovery(signature, public_key)

            if recovered_data:
                analysis["recovery_successful"] = True

                # Try to parse as Scheme 1
                parsed = self.iso9796_verifier._parse_scheme_1_structure(recovered_data)
                if parsed:
                    header, m1, message_hash, hash_function, trailer = parsed
                    analysis["scheme_detected"] = "Scheme 1"
                    analysis["hash_function"] = hash_function.name
                    analysis["structure_valid"] = True
                    analysis["recovered_message_length"] = len(m1)
                    analysis["header"] = f"0x{header:02X}"
                    analysis["trailer"] = trailer.hex()

        except Exception as e:
            analysis["error"] = str(e)

        return analysis
