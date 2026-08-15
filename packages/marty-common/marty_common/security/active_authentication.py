"""Compatibility adapters for native ICAO Active Authentication.

Protocol validation, APDU framing, challenge generation, RSA recovery, and
simulator signing are implemented by ``marty_verification``. Python retains
reader orchestration and the established service models.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from marty_common.native_backends import NativeBackendError, load_native_backend

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric import rsa

logger = logging.getLogger(__name__)


def _native():
    return load_native_backend(
        "marty_verification",
        (
            "active_authentication_build_apdu",
            "active_authentication_generate_challenge",
            "active_authentication_parse_response",
            "active_authentication_verify",
            "hash_data",
            "iso9796_scheme1_sign",
        ),
    )


def _public_key_der(public_key: rsa.RSAPublicKey) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _private_key_der(private_key: rsa.RSAPrivateKey) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


@dataclass
class ActiveAuthenticationChallenge:
    challenge: bytes
    hash_algorithm: str
    key_size: int
    timestamp: int | None = None


@dataclass
class ActiveAuthenticationResponse:
    signature: bytes
    recovered_message: bytes | None = None
    trailer: bytes | None = None
    is_valid: bool = False


class ActiveAuthenticationProtocol:
    """Stable Python surface over the native Active Authentication kernel."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
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
        challenge = bytes(
            _native().active_authentication_generate_challenge(key_size, hash_algorithm)
        )
        return ActiveAuthenticationChallenge(challenge, hash_algorithm, key_size)

    def create_aa_apdu_command(self, challenge: ActiveAuthenticationChallenge) -> bytes:
        return bytes(_native().active_authentication_build_apdu(challenge.challenge))

    def parse_aa_response(
        self, response_data: bytes, challenge: ActiveAuthenticationChallenge
    ) -> ActiveAuthenticationResponse:
        del challenge
        signature = bytes(_native().active_authentication_parse_response(response_data))
        return ActiveAuthenticationResponse(signature=signature)

    def verify_active_authentication(
        self,
        response: ActiveAuthenticationResponse,
        challenge: ActiveAuthenticationChallenge,
        public_key: rsa.RSAPublicKey,
    ) -> bool:
        try:
            result = _native().active_authentication_verify(
                _public_key_der(public_key),
                challenge.challenge,
                response.signature,
                challenge.hash_algorithm,
            )
        except NativeBackendError:
            raise
        except (RuntimeError, TypeError, ValueError):
            self.logger.warning("Active Authentication signature rejected", exc_info=True)
            return False

        response.is_valid = bool(result["is_valid"])
        recovered = result.get("recovered_message")
        response.recovered_message = bytes(recovered) if recovered is not None else None
        response.trailer = b"\xbc" if response.is_valid else None
        return response.is_valid

    def _verify_challenge_in_message(
        self, message: bytes, challenge: ActiveAuthenticationChallenge
    ) -> bool:
        return message == challenge.challenge

    def _parse_iso9796_structure(self, recovered_bytes: bytes) -> bytes | None:
        return bytes(recovered_bytes) if recovered_bytes else None

    def _get_hash_length_from_id(self, hash_id: int) -> int | None:
        return {0x33: 20, 0x38: 28, 0x34: 32, 0x36: 48, 0x35: 64}.get(hash_id)

    def _compute_hash_by_id(self, hash_id: int, data: bytes) -> bytes | None:
        algorithm = {0x33: "sha1", 0x38: "sha224", 0x34: "sha256", 0x36: "sha384", 0x35: "sha512"}.get(hash_id)
        return bytes(_native().hash_data(algorithm, data)) if algorithm else None

    def create_mock_aa_response(
        self, challenge: ActiveAuthenticationChallenge, private_key: rsa.RSAPrivateKey
    ) -> bytes:
        try:
            signature = _native().iso9796_scheme1_sign(
                _private_key_der(private_key), challenge.challenge
            )
            return bytes(signature) + b"\x90\x00"
        except NativeBackendError:
            raise
        except (RuntimeError, TypeError, ValueError):
            self.logger.warning("Native AA simulator signing failed", exc_info=True)
            return b"\x69\x82"

    def _create_iso9796_message(self, challenge: ActiveAuthenticationChallenge) -> bytes:
        return challenge.challenge

    def _sign_iso9796_message(
        self, message: bytes, private_key: rsa.RSAPrivateKey
    ) -> bytes:
        return bytes(_native().iso9796_scheme1_sign(_private_key_der(private_key), message))


class ActiveAuthenticationManager:
    """Orchestrates native AA operations with an application-provided reader."""

    def __init__(self) -> None:
        self.protocol = ActiveAuthenticationProtocol()
        self.logger = logging.getLogger(__name__)

    def perform_active_authentication(self, reader, public_key: rsa.RSAPublicKey) -> bool:
        try:
            challenge = self.protocol.generate_challenge()
            response_data = reader.transmit_apdu(
                self.protocol.create_aa_apdu_command(challenge)
            )
            response = self.protocol.parse_aa_response(response_data, challenge)
            return self.protocol.verify_active_authentication(response, challenge, public_key)
        except NativeBackendError:
            raise
        except Exception:
            self.logger.exception("Active Authentication error")
            return False

    def verify_chip_authenticity(
        self, reader, public_key: rsa.RSAPublicKey, num_rounds: int = 3
    ) -> bool:
        return all(
            self.perform_active_authentication(reader, public_key) for _ in range(num_rounds)
        )
