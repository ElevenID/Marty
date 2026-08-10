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
    MasterListResponse,
    MasterListUploadResponse,
    UploadStatus,
)
from app.utils.asn1_utils import ASN1Decoder, ASN1Encoder

from marty_plugin.native_backends import NativeOperationError, require_backend

logger = logging.getLogger(__name__)


class MasterListService:
    """Service for managing CSCA Master Lists"""

    def __init__(
        self,
        db_connection: aiosqlite.Connection | None = None,
        signer_certificate_der: bytes | None = None,
    ) -> None:
        """Initialize with optional database connection"""
        self.db_connection = db_connection
        self.signer_certificate_der = signer_certificate_der

    async def get_master_list(self, country: str | None = None) -> MasterListResponse:
        """
        Retrieve the CSCA Master List, optionally filtered by country.
        """
        # Get certificates from database
        certificates = []
        cert_dicts = await DatabaseManager.get_certificates("CSCA", country)

        if cert_dicts:
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

    async def upload_master_list(
        self, master_list_data: bytes
    ) -> MasterListUploadResponse:
        """
        Process and store an uploaded master list.
        """
        try:
            if self.signer_certificate_der is None:
                raise NativeOperationError(
                    "Master List signer certificate is not configured"
                )
            native = require_backend("marty_verification")
            if not native.verify_master_list_signature(
                master_list_data, self.signer_certificate_der
            ):
                raise NativeOperationError("Master List signature verification failed")
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
