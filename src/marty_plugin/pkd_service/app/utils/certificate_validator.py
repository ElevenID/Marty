"""Fail-closed certificate validation backed by ``marty_verification``."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from marty_plugin.native_backends import NativeBackendUnavailable, require_backend


class CertificateValidator:
    """Compatibility adapter for the native X.509 chain validator."""

    def __init__(
        self,
        trust_roots: list[Any] | None = None,
        other_certs: list[Any] | None = None,
        logger=None,
        revocation_mode: str = "soft_fail",
    ) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.trust_roots = list(trust_roots or [])
        self.other_certs = list(other_certs or [])
        self.revocation_mode = revocation_mode

    def validate(
        self,
        certificate_to_validate: Any,
        usage: str = "digital_signature",
        moment: datetime | None = None,
    ) -> bool:
        """Validate one certificate using the configured native trust store."""
        del usage, moment  # Retained for service-level API compatibility.
        return self._validate_native([certificate_to_validate])

    def validate_chain(
        self,
        certificate_chain: list[Any],
        usage: str = "digital_signature",
        moment: datetime | None = None,
    ) -> bool:
        """Validate an end-entity-first chain using the native validator."""
        del usage, moment  # Retained for service-level API compatibility.
        return self._validate_native(certificate_chain)

    def _validate_native(self, certificate_chain: list[Any]) -> bool:
        if not certificate_chain:
            return False

        native = require_backend("marty_verification")
        try:
            validator = native.ChainValidator()
            for root in self.trust_roots:
                validator.add_trust_anchor_der(self._certificate_der(native, root))
            for intermediate in self.other_certs:
                validator.add_intermediate_der(
                    self._certificate_der(native, intermediate)
                )

            chain_pem = [
                native.certificate_der_to_pem(
                    self._certificate_der(native, certificate)
                )
                for certificate in certificate_chain
            ]
            return bool(validator.validate_chain(chain_pem).valid)
        except NativeBackendUnavailable:
            raise
        except Exception as exc:
            self.logger.error("Native certificate validation failed closed: %s", exc)
            return False

    @staticmethod
    def _certificate_der(native: Any, certificate: Any) -> bytes:
        """Normalize supported compatibility inputs without parsing in Python."""
        if isinstance(certificate, str):
            return bytes(native.certificate_pem_to_der(certificate))
        if isinstance(certificate, (bytes, bytearray, memoryview)):
            value = bytes(certificate)
            if value.lstrip().startswith(b"-----BEGIN"):
                return bytes(native.certificate_pem_to_der(value.decode("ascii")))
            return bytes(native.load_certificate_der(value))

        certificate_data = getattr(certificate, "certificate_data", None)
        if certificate_data is not None:
            return CertificateValidator._certificate_der(native, certificate_data)

        for method_name in ("to_der", "as_der"):
            method = getattr(certificate, method_name, None)
            if callable(method):
                return CertificateValidator._certificate_der(native, method())

        for method_name in ("to_pem", "as_pem"):
            method = getattr(certificate, method_name, None)
            if callable(method):
                return CertificateValidator._certificate_der(native, method())

        raise TypeError(
            f"Unsupported certificate data type: {type(certificate).__name__}"
        )
