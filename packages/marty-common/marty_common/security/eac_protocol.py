"""Compatibility orchestration for native eMRTD Extended Access Control.

Cryptographic key generation, terminal signatures, certificate-signature
checks, ECDH, KDFs, encryption, and MAC validation are implemented by the
canonical ``marty_verification`` Rust extension. Python retains public models,
transport-facing orchestration, audit logging, and key serialization adapters.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, IntEnum
from typing import TYPE_CHECKING, Any

from marty_common.native_backends import NativeBackendError, load_native_backend

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric import ec, rsa

logger = logging.getLogger(__name__)


def _native():
    return load_native_backend(
        "marty_verification",
        (
            "NativeEacChipAuthentication",
            "NativeEacSecureMessaging",
            "eac_calculate_mac",
            "eac_certificate_fingerprint",
            "eac_serialize_certificate",
            "eac_sign_terminal_challenge",
            "eac_verify_certificate_signature",
            "rsa_generate",
        ),
    )


def _private_key_der(private_key: Any) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _public_key_der(public_key: Any) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


class EACError(Exception):
    """Base exception for EAC protocol errors."""


class TerminalAuthenticationError(EACError):
    """Terminal Authentication specific errors."""


class ChipAuthenticationError(EACError):
    """Chip Authentication specific errors."""


class CertificateValidationError(EACError):
    """Certificate-chain validation errors."""


class EACCryptoAlgorithm(Enum):
    ECDH_P256_SHA256 = "ecdh_p256_sha256"
    ECDH_P384_SHA384 = "ecdh_p384_sha384"
    ECDH_BRAINPOOL_P256R1_SHA256 = "ecdh_brainpool_p256r1_sha256"
    RSA_2048_SHA256 = "rsa_2048_sha256"
    RSA_3072_SHA256 = "rsa_3072_sha256"


class EACProtocolStep(IntEnum):
    INITIAL = 0
    TERMINAL_AUTHENTICATION = 1
    CHIP_AUTHENTICATION = 2
    SECURE_MESSAGING = 3
    COMPLETE = 4


@dataclass
class EACCertificate:
    certificate_holder_reference: str
    certificate_authority_reference: str
    certificate_holder_authorization: int
    public_key: ec.EllipticCurvePublicKey | rsa.RSAPublicKey
    certificate_effective_date: datetime
    certificate_expiration_date: datetime
    signature: bytes
    algorithm: EACCryptoAlgorithm
    raw_data: bytes = field(default=b"")

    def __post_init__(self) -> None:
        if self.certificate_expiration_date <= self.certificate_effective_date:
            raise CertificateValidationError(
                "Certificate expiration date must be after effective date"
            )

    def is_valid_at(self, check_date: datetime | None = None) -> bool:
        check_date = check_date or datetime.utcnow()
        return self.certificate_effective_date <= check_date <= self.certificate_expiration_date

    def get_certificate_fingerprint(self) -> str:
        source = self.raw_data or (
            self.certificate_holder_reference + self.certificate_authority_reference
        ).encode()
        return str(_native().eac_certificate_fingerprint(source))


@dataclass
class EACSecureChannel:
    session_keys: dict[str, bytes] = field(default_factory=dict)
    mac_key: bytes | None = None
    encryption_key: bytes | None = None
    send_sequence_counter: int = 0
    receive_sequence_counter: int = 0
    algorithm: EACCryptoAlgorithm | None = None
    established_at: datetime | None = None

    def increment_ssc(self, direction: str = "send") -> int:
        if direction == "send":
            self.send_sequence_counter += 1
            return self.send_sequence_counter
        self.receive_sequence_counter += 1
        return self.receive_sequence_counter

    def is_established(self) -> bool:
        return (
            self.mac_key is not None
            and self.encryption_key is not None
            and self.established_at is not None
        )


class EACTerminalAuthentication:
    def __init__(self, terminal_certificate: EACCertificate, terminal_private_key: Any) -> None:
        self.terminal_certificate = terminal_certificate
        self.terminal_private_key = terminal_private_key
        self.certificate_chain: list[EACCertificate] = []
        self.challenge_response_pairs: list[tuple[bytes, bytes]] = []

    def set_certificate_chain(self, chain: list[EACCertificate]) -> None:
        if not chain:
            raise CertificateValidationError("Certificate chain cannot be empty")
        now = datetime.utcnow()
        if any(not certificate.is_valid_at(now) for certificate in chain):
            raise CertificateValidationError("Certificate chain contains an invalid date")
        for index, (signer, subject) in enumerate(zip(chain, chain[1:], strict=False)):
            if not self._verify_certificate_signature(signer, subject):
                raise CertificateValidationError(
                    f"Invalid signature in certificate chain at position {index}"
                )
        self.certificate_chain = chain

    def _verify_certificate_signature(
        self, signer_cert: EACCertificate, subject_cert: EACCertificate
    ) -> bool:
        if not subject_cert.raw_data:
            return False
        return bool(
            _native().eac_verify_certificate_signature(
                signer_cert.algorithm.value,
                _public_key_der(signer_cert.public_key),
                subject_cert.raw_data,
                subject_cert.signature,
            )
        )

    def perform_terminal_authentication(self, chip_challenge: bytes) -> bytes:
        if not self.certificate_chain:
            raise TerminalAuthenticationError("Certificate chain not set")
        try:
            signature = bytes(
                _native().eac_sign_terminal_challenge(
                    self.terminal_certificate.algorithm.value,
                    _private_key_der(self.terminal_private_key),
                    chip_challenge,
                )
            )
        except NativeBackendError:
            raise
        except (RuntimeError, TypeError, ValueError) as exc:
            raise TerminalAuthenticationError(f"Failed to sign challenge: {exc}") from exc
        self.challenge_response_pairs.append((chip_challenge, signature))
        return signature

    def _sign_ecdsa_challenge(self, challenge: bytes) -> bytes:
        return self.perform_terminal_authentication(challenge)

    def _sign_rsa_challenge(self, challenge: bytes) -> bytes:
        return self.perform_terminal_authentication(challenge)

    def get_terminal_certificate_data(self) -> bytes:
        return self.terminal_certificate.raw_data or self._serialize_certificate(
            self.terminal_certificate
        )

    def _serialize_certificate(self, cert: EACCertificate) -> bytes:
        return bytes(
            _native().eac_serialize_certificate(
                cert.certificate_holder_reference,
                cert.certificate_authority_reference,
                cert.certificate_holder_authorization,
                cert.certificate_effective_date.isoformat(),
                cert.certificate_expiration_date.isoformat(),
            )
        )


class EACChipAuthentication:
    def __init__(
        self,
        chip_public_key: ec.EllipticCurvePublicKey | rsa.RSAPublicKey,
        algorithm: EACCryptoAlgorithm = EACCryptoAlgorithm.ECDH_P256_SHA256,
    ) -> None:
        self.chip_public_key = chip_public_key
        self.algorithm = algorithm
        self.ephemeral_key_pair: tuple[Any, Any] | None = None
        self.shared_secret: bytes | None = None
        self._native = _native().NativeEacChipAuthentication(algorithm.value)

    def generate_ephemeral_keypair(self) -> tuple[bytes, Any]:
        try:
            public_key, private_key_der = self._native.generate_ephemeral_keypair()
            from cryptography.hazmat.primitives import serialization

            private_key = serialization.load_der_private_key(bytes(private_key_der), password=None)
        except NativeBackendError:
            raise
        except (RuntimeError, TypeError, ValueError) as exc:
            raise ChipAuthenticationError(f"Failed to generate ephemeral keypair: {exc}") from exc
        public_key = bytes(public_key)
        self.ephemeral_key_pair = (public_key, private_key)
        return public_key[1:], private_key

    def _generate_ecdh_keypair(self) -> tuple[bytes, Any]:
        return self.generate_ephemeral_keypair()

    def _generate_rsa_keypair(self) -> tuple[bytes, Any]:
        return self.generate_ephemeral_keypair()

    def perform_chip_authentication(self, chip_ephemeral_public_key: bytes) -> bytes:
        if not self.ephemeral_key_pair:
            raise ChipAuthenticationError("Ephemeral keypair not generated")
        try:
            shared_secret = bytes(
                self._native.perform_chip_authentication(chip_ephemeral_public_key)
            )
        except NativeBackendError:
            raise
        except (RuntimeError, TypeError, ValueError) as exc:
            raise ChipAuthenticationError(f"Failed to perform chip authentication: {exc}") from exc
        self.shared_secret = shared_secret
        return shared_secret

    def _perform_ecdh(self, peer_public_key_bytes: bytes) -> bytes:
        return self.perform_chip_authentication(peer_public_key_bytes)

    def _perform_rsa_key_agreement(self, peer_public_key_bytes: bytes) -> bytes:
        return self.perform_chip_authentication(peer_public_key_bytes)


class EACSecureMessaging:
    def __init__(self, shared_secret: bytes, algorithm: EACCryptoAlgorithm) -> None:
        self.shared_secret = shared_secret
        self.algorithm = algorithm
        self._native = _native().NativeEacSecureMessaging(shared_secret, algorithm.value)
        self.secure_channel = EACSecureChannel()
        self._sync_state(established=True)

    def _derive_session_keys(self) -> None:
        self._sync_state(established=True)

    def _sync_state(self, *, established: bool = False) -> None:
        state = self._native.state()
        self.secure_channel.mac_key = bytes(state["mac_key"])
        self.secure_channel.encryption_key = bytes(state["encryption_key"])
        self.secure_channel.send_sequence_counter = int(state["send_sequence_counter"])
        self.secure_channel.receive_sequence_counter = int(state["receive_sequence_counter"])
        self.secure_channel.algorithm = self.algorithm
        if established and self.secure_channel.established_at is None:
            self.secure_channel.established_at = datetime.utcnow()

    def encrypt_apdu(self, apdu_data: bytes) -> bytes:
        try:
            protected = bytes(self._native.encrypt_apdu(apdu_data))
        except NativeBackendError:
            raise
        except (RuntimeError, TypeError, ValueError) as exc:
            raise EACError(f"Failed to encrypt APDU: {exc}") from exc
        self._sync_state()
        return protected

    def decrypt_apdu(self, encrypted_apdu: bytes) -> bytes:
        try:
            plaintext = bytes(self._native.decrypt_apdu(encrypted_apdu))
        except NativeBackendError:
            raise
        except (RuntimeError, TypeError, ValueError) as exc:
            raise EACError(f"Failed to decrypt APDU: {exc}") from exc
        self._sync_state()
        return plaintext

    def _calculate_mac(self, data: bytes) -> bytes:
        if not self.secure_channel.mac_key:
            raise EACError("MAC key not available")
        return bytes(_native().eac_calculate_mac(self.secure_channel.mac_key, data))


class EACProtocol:
    def __init__(
        self,
        terminal_cert: EACCertificate,
        terminal_private_key: Any,
        chip_public_key: Any,
        algorithm: EACCryptoAlgorithm = EACCryptoAlgorithm.ECDH_P256_SHA256,
    ) -> None:
        self.terminal_auth = EACTerminalAuthentication(terminal_cert, terminal_private_key)
        self.chip_auth = EACChipAuthentication(chip_public_key, algorithm)
        self.secure_messaging: EACSecureMessaging | None = None
        self.protocol_step = EACProtocolStep.INITIAL
        self.session_log: list[dict[str, Any]] = []

    def execute_eac_protocol(
        self, chip_challenge: bytes, chip_ephemeral_public_key: bytes
    ) -> EACSecureMessaging:
        try:
            self._log_protocol_step("Starting EAC Protocol")
            self.protocol_step = EACProtocolStep.TERMINAL_AUTHENTICATION
            self._log_protocol_step("Performing Terminal Authentication")
            self.terminal_auth.perform_terminal_authentication(chip_challenge)
            self.protocol_step = EACProtocolStep.CHIP_AUTHENTICATION
            self._log_protocol_step("Performing Chip Authentication")
            self.chip_auth.generate_ephemeral_keypair()
            shared_secret = self.chip_auth.perform_chip_authentication(
                chip_ephemeral_public_key
            )
            self.protocol_step = EACProtocolStep.SECURE_MESSAGING
            self._log_protocol_step("Establishing Secure Messaging")
            self.secure_messaging = EACSecureMessaging(shared_secret, self.chip_auth.algorithm)
            self.protocol_step = EACProtocolStep.COMPLETE
            self._log_protocol_step("EAC Protocol completed successfully")
            return self.secure_messaging
        except NativeBackendError:
            raise
        except Exception as exc:
            self._log_protocol_step(f"EAC Protocol failed: {exc}", level="error")
            raise EACError(f"EAC Protocol execution failed: {exc}") from exc

    def _log_protocol_step(self, message: str, level: str = "info") -> None:
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "step": self.protocol_step.name,
            "message": message,
            "level": level,
        }
        self.session_log.append(entry)
        getattr(logger, "error" if level == "error" else "info")(message)

    def get_protocol_status(self) -> dict[str, Any]:
        return {
            "current_step": self.protocol_step.name,
            "terminal_certificate": self.terminal_auth.terminal_certificate.get_certificate_fingerprint(),
            "secure_channel_established": bool(
                self.secure_messaging and self.secure_messaging.secure_channel.is_established()
            ),
            "session_log_entries": len(self.session_log),
            "algorithm": self.chip_auth.algorithm.value,
            "last_activity": self.session_log[-1]["timestamp"] if self.session_log else None,
        }


class MockEACCertificate:
    """Native-backed key fixtures retained for compatibility tests."""

    @staticmethod
    def create_mock_terminal_certificate() -> tuple[EACCertificate, Any]:
        from cryptography.hazmat.primitives import serialization

        private_der, public_der = _native().rsa_generate(2048)
        private_key = serialization.load_der_private_key(bytes(private_der), password=None)
        public_key = serialization.load_der_public_key(bytes(public_der))
        certificate = EACCertificate(
            certificate_holder_reference="TESTTERM001",
            certificate_authority_reference="TESTDV001",
            certificate_holder_authorization=0x7F,
            public_key=public_key,
            certificate_effective_date=datetime.utcnow() - timedelta(days=30),
            certificate_expiration_date=datetime.utcnow() + timedelta(days=365),
            signature=b"mock_signature_data",
            algorithm=EACCryptoAlgorithm.RSA_2048_SHA256,
            raw_data=b"mock_certificate_data",
        )
        return certificate, private_key

    @staticmethod
    def create_mock_chip_key() -> ec.EllipticCurvePublicKey:
        from cryptography.hazmat.primitives.asymmetric import ec

        native = _native().NativeEacChipAuthentication(
            EACCryptoAlgorithm.ECDH_P256_SHA256.value
        )
        public_key, _ = native.generate_ephemeral_keypair()
        return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes(public_key))
