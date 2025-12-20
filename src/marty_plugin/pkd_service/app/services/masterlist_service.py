"""
Service for handling CSCA Master List operations
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime

import aiosqlite
from app.core.config import settings
from app.db.database import DatabaseManager
from app.models.pkd_models import (
    Certificate,
    CertificateStatus,
    MasterListResponse,
    MasterListUploadResponse,
    UploadStatus,
)
from app.utils.asn1_utils import ASN1Decoder, ASN1Encoder

logger = logging.getLogger(__name__)


class MasterListService:
    """Service for managing CSCA Master Lists"""

    def __init__(self, db_connection: aiosqlite.Connection | None = None) -> None:
        """Initialize with optional database connection"""
        self.db_connection = db_connection

    async def get_master_list(self, country: str | None = None) -> MasterListResponse:
        """
        Retrieve the CSCA Master List, optionally filtered by country.
        """
        # Get certificates from database
        certificates = []
        cert_dicts = await DatabaseManager.get_certificates("CSCA", country)

        if not cert_dicts:
            # Fallback to mock data if database is empty
            certificates = await self._get_certificates(country)
        else:
            # Convert dictionaries to Certificate objects
            for cert_dict in cert_dicts:
                certificates.append(
                    Certificate(
                        id=uuid.UUID(cert_dict["id"]),
                        subject=cert_dict["subject"],
                        issuer=cert_dict["issuer"],
                        valid_from=cert_dict["valid_from"],
                        valid_to=cert_dict["valid_to"],
                        serial_number=cert_dict["serial_number"],
                        certificate_data=cert_dict["certificate_data"],
                        status=cert_dict["status"],
                        country_code=cert_dict["country_code"],
                    )
                )

        # Get list of unique countries from certificates
        countries = list({cert.country_code for cert in certificates})

        return MasterListResponse(
            id=uuid.uuid4(),
            version=1,  # In real implementation, track versions
            created=datetime.now(),
            countries=countries,
            certificates=certificates,
        )

    async def get_master_list_binary(self, country: str | None = None) -> bytes:
        """
        Get the ASN.1 encoded master list data, optionally filtered by country.

        Returns a properly ASN.1 encoded master list that follows ICAO specifications.
        """
        # Get certificates
        master_list = await self.get_master_list(country)
        certificates = master_list.certificates

        # Encode as ASN.1 master list
        return ASN1Encoder.encode_master_list(certificates)

    async def upload_master_list(self, master_list_data: bytes) -> MasterListUploadResponse:
        """
        Process and store an uploaded master list.
        """
        try:
            # Parse the ASN.1 master list data
            certificates = ASN1Decoder.decode_master_list(master_list_data)

            # Save the raw master list file to file system
            storage_path = settings.MASTERLIST_PATH
            os.makedirs(storage_path, exist_ok=True)

            master_list_path = os.path.join(
                storage_path, f"masterlist-{datetime.now().strftime('%Y%m%d%H%M%S')}.ml"
            )
            with open(master_list_path, "wb") as f:
                f.write(master_list_data)

            # Store certificates in database
            certificate_count = 0
            for cert in certificates:
                # Convert Certificate to dictionary for database
                cert_dict = {
                    "subject": cert.subject,
                    "issuer": cert.issuer,
                    "valid_from": cert.valid_from,
                    "valid_to": cert.valid_to,
                    "serial_number": cert.serial_number,
                    "certificate_data": cert.certificate_data,
                    "status": cert.status,
                    "country_code": cert.country_code,
                }

                # Store in database
                await DatabaseManager.store_certificate(cert_dict, "CSCA")
                certificate_count += 1

            # Log the operation
            logger.info(f"Processed master list with {certificate_count} certificates")

            return MasterListUploadResponse(
                id=uuid.uuid4(),
                version=1,
                created=datetime.now(),
                status=UploadStatus.PROCESSED,
                certificate_count=certificate_count,
            )

        except Exception as e:
            logger.exception(f"Failed to process master list: {e}")
            return MasterListUploadResponse(
                id=uuid.uuid4(),
                version=0,
                created=datetime.now(),
                status=UploadStatus.ERROR,
                certificate_count=0,
            )

    async def _get_certificates(self, country: str | None = None) -> list[Certificate]:
        """
        Helper method to get certificates for the master list.
        This is a fallback when the database is empty.
        """
        # This is a simplified mock implementation with sample data
        certificates = [
            Certificate(
                id=uuid.uuid4(),
                subject="CN=CSCA-USA,O=Department of State,C=US",
                issuer="CN=CSCA-USA,O=Department of State,C=US",
                valid_from=datetime(2020, 1, 1),
                valid_to=datetime(2030, 1, 1),
                serial_number="01234567",
                certificate_data=b"MOCK_CERTIFICATE_DATA_USA",
                status=CertificateStatus.ACTIVE,
                country_code="USA",
            ),
            Certificate(
                id=uuid.uuid4(),
                subject="CN=CSCA-CAN,O=Passport Canada,C=CA",
                issuer="CN=CSCA-CAN,O=Passport Canada,C=CA",
                valid_from=datetime(2020, 1, 1),
                valid_to=datetime(2030, 1, 1),
                serial_number="89012345",
                certificate_data=b"MOCK_CERTIFICATE_DATA_CAN",
                status=CertificateStatus.ACTIVE,
                country_code="CAN",
            ),
            Certificate(
                id=uuid.uuid4(),
                subject="CN=CSCA-GBR,O=HM Passport Office,C=GB",
                issuer="CN=CSCA-GBR,O=HM Passport Office,C=GB",
                valid_from=datetime(2020, 1, 1),
                valid_to=datetime(2030, 1, 1),
                serial_number="67890123",
                certificate_data=b"MOCK_CERTIFICATE_DATA_GBR",
                status=CertificateStatus.ACTIVE,
                country_code="GBR",
            ),
        ]

        # Generate mock certificate data for demo
        for cert in certificates:
            if cert.certificate_data in (
                b"MOCK_CERTIFICATE_DATA_USA",
                b"MOCK_CERTIFICATE_DATA_CAN",
                b"MOCK_CERTIFICATE_DATA_GBR",
            ):
                cert.certificate_data = ASN1Encoder._create_mock_certificate(cert)

        if country:
            return [cert for cert in certificates if cert.country_code == country]
        return certificates
