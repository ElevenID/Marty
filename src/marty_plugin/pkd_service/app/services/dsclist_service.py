"""
Service for handling Document Signer Certificate (DSC) List operations
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
    DSCListResponse,
    DSCListUploadResponse,
    UploadStatus,
)
from app.utils.asn1_utils import ASN1Decoder, ASN1Encoder

logger = logging.getLogger(__name__)


class DSCListService:
    """Service for managing DSC Lists"""

    def __init__(self, db_connection: aiosqlite.Connection | None = None) -> None:
        """Initialize with optional database connection"""
        self.db_connection = db_connection

    async def get_dsc_list(self, country: str | None = None) -> DSCListResponse:
        """
        Retrieve the DSC List, optionally filtered by country.
        """
        # Get certificates from database
        certificates = []
        cert_dicts = await DatabaseManager.get_certificates("DSC", country)

        if not cert_dicts:
            # Fallback to mock data if database is empty
            certificates = await self._get_dsc_certificates(country)
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

        return DSCListResponse(
            id=uuid.uuid4(),
            version=1,  # In real implementation, track versions
            created=datetime.now(),
            countries=countries,
            certificates=certificates,
        )

    async def get_dsc_list_binary(self, country: str | None = None) -> bytes:
        """
        Get the ASN.1 encoded DSC list data, optionally filtered by country.

        Returns a properly ASN.1 encoded DSC list that follows ICAO specifications.
        """
        # Get certificates
        dsc_list = await self.get_dsc_list(country)
        certificates = dsc_list.certificates

        # Encode as ASN.1 DSC list
        return ASN1Encoder.encode_dsc_list(certificates)

    async def upload_dsc_list(self, dsc_list_data: bytes) -> DSCListUploadResponse:
        """
        Process and store an uploaded DSC list.
        """
        try:
            # Parse the ASN.1 DSC list data
            certificates = ASN1Decoder.decode_dsc_list(dsc_list_data)

            # Save the raw DSC list file
            storage_path = settings.DSCLIST_PATH
            os.makedirs(storage_path, exist_ok=True)

            dsc_list_path = os.path.join(
                storage_path, f"dsclist-{datetime.now().strftime('%Y%m%d%H%M%S')}.dsc"
            )
            with open(dsc_list_path, "wb") as f:
                f.write(dsc_list_data)

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
                await DatabaseManager.store_certificate(cert_dict, "DSC")
                certificate_count += 1

            # Log the operation
            logger.info(f"Processed DSC list with {certificate_count} certificates")

            return DSCListUploadResponse(
                id=uuid.uuid4(),
                version=1,
                created=datetime.now(),
                status=UploadStatus.PROCESSED,
                certificate_count=certificate_count,
            )

        except Exception as e:
            logger.exception(f"Failed to process DSC list: {e}")
            return DSCListUploadResponse(
                id=uuid.uuid4(),
                version=0,
                created=datetime.now(),
                status=UploadStatus.ERROR,
                certificate_count=0,
            )

    async def _get_dsc_certificates(self, country: str | None = None) -> list[Certificate]:
        """
        Helper method to get DSC certificates.
        This is a fallback when the database is empty.
        """
        # This is a simplified mock implementation with sample data
        certificates = [
            Certificate(
                id=uuid.uuid4(),
                subject="CN=DS-USA-001,O=Department of State,C=US",
                issuer="CN=CSCA-USA,O=Department of State,C=US",
                valid_from=datetime(2023, 1, 1),
                valid_to=datetime(2025, 1, 1),
                serial_number="DSC00001",
                certificate_data=b"MOCK_DSC_DATA_USA_1",
                status=CertificateStatus.ACTIVE,
                country_code="USA",
            ),
            Certificate(
                id=uuid.uuid4(),
                subject="CN=DS-USA-002,O=Department of State,C=US",
                issuer="CN=CSCA-USA,O=Department of State,C=US",
                valid_from=datetime(2023, 6, 1),
                valid_to=datetime(2025, 6, 1),
                serial_number="DSC00002",
                certificate_data=b"MOCK_DSC_DATA_USA_2",
                status=CertificateStatus.ACTIVE,
                country_code="USA",
            ),
            Certificate(
                id=uuid.uuid4(),
                subject="CN=DS-CAN-001,O=Passport Canada,C=CA",
                issuer="CN=CSCA-CAN,O=Passport Canada,C=CA",
                valid_from=datetime(2023, 3, 1),
                valid_to=datetime(2025, 3, 1),
                serial_number="DSC00003",
                certificate_data=b"MOCK_DSC_DATA_CAN",
                status=CertificateStatus.ACTIVE,
                country_code="CAN",
            ),
            Certificate(
                id=uuid.uuid4(),
                subject="CN=DS-GBR-001,O=HM Passport Office,C=GB",
                issuer="CN=CSCA-GBR,O=HM Passport Office,C=GB",
                valid_from=datetime(2023, 2, 1),
                valid_to=datetime(2025, 2, 1),
                serial_number="DSC00004",
                certificate_data=b"MOCK_DSC_DATA_GBR",
                status=CertificateStatus.ACTIVE,
                country_code="GBR",
            ),
        ]

        # Generate mock certificate data for demo
        for cert in certificates:
            if cert.certificate_data.startswith(b"MOCK_DSC_DATA_"):
                cert.certificate_data = ASN1Encoder._create_mock_certificate(cert)

        if country:
            return [cert for cert in certificates if cert.country_code == country]
        return certificates
