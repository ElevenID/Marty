"""
Certificate Store for PKD Mirror Service

This module provides a simplified interface for storing and retrieving
certificates from the database for the PKD Mirror Service.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.db.database import DatabaseManager
from app.models.pkd_models import CertificateStatus
from app.utils.pkd_payloads import parse_certificate_payload, parse_crl_payload


class CertificateStore:
    """
    Certificate store for PKD Mirror Service.

    This class provides methods to store and retrieve certificates and CRLs.
    It's designed to be used by the PKD Mirror Service to store certificates
    obtained from external sources.
    """

    def __init__(self, logger=None) -> None:
        """
        Initialize the certificate store.

        Args:
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

    def store_csca_certificates(self, cert_data: bytes) -> bool:
        """
        Store CSCA certificates in the database.

        Args:
            cert_data: Binary certificate data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            certificates = self._parse_certificates(cert_data, "CSCA")
            if not certificates:
                self.logger.warning("No CSCA certificates decoded from payload")
                return False

            stored = 0
            for cert in certificates:
                asyncio.run(self._store_certificate(cert, "CSCA"))
                stored += 1

            self.logger.info("Stored %s CSCA certificates", stored)

        except Exception as e:
            self.logger.exception("Failed to store CSCA certificates: %s", e)
            return False
        else:
            return True

    def store_dsc_certificates(self, cert_data: bytes) -> bool:
        """
        Store DSC certificates in the database.

        Args:
            cert_data: Binary certificate data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            certificates = self._parse_certificates(cert_data, "DSC")
            if not certificates:
                self.logger.warning("No DSC certificates decoded from payload")
                return False

            stored = 0
            for cert in certificates:
                asyncio.run(self._store_certificate(cert, "DSC"))
                stored += 1

            self.logger.info("Stored %s DSC certificates", stored)

        except Exception as e:
            self.logger.exception("Failed to store DSC certificates: %s", e)
            return False
        else:
            return True

    def store_crls(self, crl_data: bytes) -> bool:
        """
        Store Certificate Revocation Lists in the database.

        Args:
            crl_data: Binary CRL data

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            crls = self._parse_crls(crl_data)
            if not crls:
                self.logger.warning("No CRLs decoded from payload")
                return False

            for crl in crls:
                asyncio.run(self._store_crl(crl))

            self._update_certificate_status_from_crls(crls)
            self.logger.info("Stored %s CRLs", len(crls))

        except Exception as e:
            self.logger.exception("Failed to store CRLs: %s", e)
            return False
        else:
            return True

    async def _store_certificate(self, certificate: dict[str, Any], cert_type: str) -> str | None:
        """
        Store a certificate in the database.

        Args:
            certificate: Certificate data dictionary
            cert_type: Type of certificate (CSCA or DSC)

        Returns:
            ID of the stored certificate or None if failed
        """
        try:
            return await DatabaseManager.store_certificate(certificate, cert_type)
        except Exception as e:
            self.logger.exception(f"Error storing certificate: {e}")
            return None

    async def _store_crl(self, crl: dict[str, Any]) -> str | None:
        """
        Store a CRL in the database.

        Args:
            crl: CRL data dictionary

        Returns:
            ID of the stored CRL or None if failed
        """
        try:
            return await DatabaseManager.store_crl(crl)
        except Exception as e:
            self.logger.exception(f"Error storing CRL: {e}")
            return None

    def _parse_certificates(self, cert_data: bytes, cert_type: str) -> list[dict[str, Any]]:
        """
        Parse certificates from binary data.

        Args:
            cert_data: Binary certificate data
            cert_type: Type of certificates (CSCA or DSC)

        Returns:
            list: List of certificate data dictionaries
        """
        certificates = parse_certificate_payload(cert_data, source_hint=cert_type)
        parsed: list[dict[str, Any]] = []

        for cert in certificates:
            parsed.append(
                {
                    "subject": cert.subject,
                    "issuer": cert.issuer,
                    "valid_from": cert.valid_from,
                    "valid_to": cert.valid_to,
                    "serial_number": cert.serial_number,
                    "certificate_data": cert.certificate_data,
                    "status": (
                        cert.status.value
                        if isinstance(cert.status, CertificateStatus)
                        else str(cert.status)
                    ),
                    "country_code": cert.country_code,
                }
            )

        return parsed

    def _parse_crls(self, crl_data: bytes) -> list[dict[str, Any]]:
        """
        Parse CRLs from binary data.

        Args:
            crl_data: Binary CRL data

        Returns:
            list: List of CRL data dictionaries
        """
        return parse_crl_payload(crl_data)

    def _update_certificate_status_from_crls(self, crls: list[dict[str, Any]]) -> None:
        """
        Update certificate status based on CRLs.

        Args:
            crls: List of CRL data dictionaries
        """
        serials = set()
        for crl in crls:
            for revoked in crl.get("revoked_certificates", []):
                serial = revoked.get("serial_number")
                if serial:
                    serials.add(serial)

        if not serials:
            return

        for serial in serials:
            for cert_type in ("CSCA", "DSC"):
                try:
                    asyncio.run(
                        DatabaseManager.update_certificate_status_by_serial(
                            serial_number=serial,
                            cert_type=cert_type,
                            status=CertificateStatus.REVOKED,
                        )
                    )
                except Exception as exc:  # pragma: no cover - logged for observability
                    self.logger.warning(
                        "Failed to update status for serial %s (%s): %s", serial, cert_type, exc
                    )

    def get_csca_certificates(self, country_code: str | None = None) -> list[dict[str, Any]]:
        """
        Get CSCA certificates from the database.

        Args:
            country_code: Optional country code filter

        Returns:
            List of certificate data dictionaries
        """
        # Run async get in a synchronous context
        return asyncio.run(DatabaseManager.get_certificates("CSCA", country_code))

    def get_dsc_certificates(self, country_code: str | None = None) -> list[dict[str, Any]]:
        """
        Get DSC certificates from the database.

        Args:
            country_code: Optional country code filter

        Returns:
            List of certificate data dictionaries
        """
        # Run async get in a synchronous context
        return asyncio.run(DatabaseManager.get_certificates("DSC", country_code))

    def get_crls(self, issuer: str | None = None) -> dict[str, Any] | None:
        """
        Get the latest CRL from the database.

        Args:
            issuer: Optional issuer filter

        Returns:
            CRL data dictionary or None if not found
        """
        # Run async get in a synchronous context
        return asyncio.run(DatabaseManager.get_crl(issuer))
