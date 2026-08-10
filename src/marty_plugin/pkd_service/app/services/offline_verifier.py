"""Offline certificate verification backed exclusively by Rust."""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import settings
from app.db.database import DatabaseManager
from app.models.pkd_models import CertificateStatus, VerificationResult

from marty_plugin.native_backends import require_backend

logger = logging.getLogger(__name__)


class OfflineVerifier:
    """Verify certificate chains and revocation against local PKD material."""

    def __init__(self) -> None:
        self.trust_store_path = Path(settings.LOCAL_TRUST_STORE_PATH)
        self.crl_path = Path(settings.LOCAL_CRL_PATH)
        self.native = require_backend("marty_verification")

    async def verify_certificate(self, certificate_data: bytes) -> VerificationResult:
        """Validate a DER/PEM certificate and require current local CRL evidence."""
        try:
            certificate_der = self._certificate_der(certificate_data)
            certificate_info = self.native.get_certificate_info(certificate_der)
            trust_anchors = await self._load_trust_anchors()
            if not trust_anchors:
                return self._result(
                    False, "UNTRUSTED", "No local CSCA trust anchors configured"
                )

            validator = self.native.ChainValidator()
            for anchor_der in trust_anchors:
                validator.add_trust_anchor_der(anchor_der)
            chain_result = validator.validate_chain(
                [self.native.certificate_der_to_pem(certificate_der)]
            )
            if not chain_result.valid:
                details = "; ".join(
                    chain_result.errors or ["Certificate chain is invalid"]
                )
                return self._result(False, "UNTRUSTED", details)

            revocation = self._check_local_crls(
                certificate_der,
                certificate_info,
                trust_anchors,
            )
            if revocation is None:
                return self._result(
                    False,
                    "REVOCATION_UNKNOWN",
                    "No current issuer-signed CRL is available",
                )
            revoked, reason = revocation
            if revoked:
                suffix = f" ({reason})" if reason else ""
                return self._result(
                    False, "REVOKED", f"Certificate has been revoked{suffix}"
                )

            return self._result(
                True, "VALID", "Certificate is valid, trusted, and not revoked"
            )
        except Exception as exc:
            logger.exception("Offline native certificate verification failed")
            return self._result(False, "ERROR", f"Error during verification: {exc}")

    async def _load_trust_anchors(self) -> list[bytes]:
        anchors: dict[str, bytes] = {}
        trusted = await DatabaseManager.get_certificates(
            cert_type="CSCA", status=CertificateStatus.ACTIVE
        )
        for item in trusted:
            value = item.get("certificate_data")
            if value:
                der = self._certificate_der(value)
                fingerprint = self.native.get_certificate_info(der)[
                    "fingerprint_sha256"
                ]
                anchors[fingerprint] = der

        if self.trust_store_path.exists():
            for path in self.trust_store_path.iterdir():
                if path.is_file() and path.suffix.lower() in {
                    ".cer",
                    ".crt",
                    ".der",
                    ".pem",
                }:
                    try:
                        der = self._certificate_der(path.read_bytes())
                        fingerprint = self.native.get_certificate_info(der)[
                            "fingerprint_sha256"
                        ]
                        anchors[fingerprint] = der
                    except Exception as exc:
                        logger.warning(
                            "Ignoring malformed trust anchor %s: %s", path, exc
                        )
        return list(anchors.values())

    def _check_local_crls(
        self,
        certificate_der: bytes,
        certificate_info: dict,
        trust_anchors: list[bytes],
    ) -> tuple[bool, str | None] | None:
        if not self.crl_path.exists():
            return None

        issuer = certificate_info["issuer"]
        issuer_certificates = [
            der
            for der in trust_anchors
            if self._normalize_dn(self.native.get_certificate_info(der)["subject"])
            == self._normalize_dn(issuer)
        ]
        if not issuer_certificates:
            return None

        valid_evidence = False
        for path in self.crl_path.iterdir():
            if not path.is_file() or path.suffix.lower() not in {
                ".crl",
                ".der",
                ".pem",
            }:
                continue
            try:
                crl_der = self._crl_der(path.read_bytes())
                crl = self.native.parse_crl(crl_der)
                if self._normalize_dn(crl.issuer) != self._normalize_dn(issuer):
                    continue
                validated = None
                for issuer_der in issuer_certificates:
                    try:
                        validated = self.native.validate_crl_for_certificate(
                            crl_der, certificate_der, issuer_der
                        )
                        break
                    except Exception:
                        continue
                if validated is None:
                    logger.warning("Ignoring unauthenticated or stale CRL: %s", path)
                    continue
                valid_evidence = True
                if validated["revoked"]:
                    return True, validated.get("reason")
            except Exception as exc:
                logger.warning("Ignoring invalid CRL %s: %s", path, exc)

        return (False, None) if valid_evidence else None

    async def build_trust_store(self) -> int:
        """Export active database CSCAs to the local trust-store directory."""
        self.trust_store_path.mkdir(parents=True, exist_ok=True)
        trusted = await DatabaseManager.get_certificates(
            cert_type="CSCA", status=CertificateStatus.ACTIVE
        )
        count = 0
        for item in trusted:
            cert_data = item.get("certificate_data")
            if not cert_data:
                continue
            try:
                der = self._certificate_der(cert_data)
                country = item.get("country_code", "XX")
                identifier = item.get("id", count)
                (self.trust_store_path / f"{country}_{identifier}.cer").write_bytes(der)
                count += 1
            except Exception as exc:
                logger.warning(
                    "Skipping invalid CSCA record (%s)", type(exc).__name__
                )
        return count

    async def update_local_crls(self) -> int:
        """Leave CRL synchronization to the configured persistence adapter."""
        self.crl_path.mkdir(parents=True, exist_ok=True)
        logger.warning("No CRL persistence adapter is configured")
        return 0

    def _certificate_der(self, value: bytes | str) -> bytes:
        if isinstance(value, str):
            return bytes(self.native.certificate_pem_to_der(value))
        raw = bytes(value)
        if raw.lstrip().startswith(b"-----BEGIN"):
            return bytes(self.native.certificate_pem_to_der(raw.decode("ascii")))
        return bytes(self.native.load_certificate_der(raw))

    def _crl_der(self, value: bytes) -> bytes:
        if value.lstrip().startswith(b"-----BEGIN"):
            return bytes(self.native.crl_pem_to_der(value.decode("ascii")))
        return value

    @staticmethod
    def _normalize_dn(value: str) -> str:
        return value.upper().replace(" ", "").replace(",", "")

    @staticmethod
    def _result(valid: bool, status: str, details: str) -> VerificationResult:
        return VerificationResult(is_valid=valid, status=status, details=details)
