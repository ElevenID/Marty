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
    DSCListResponse,
    DSCListUploadResponse,
    UploadStatus,
)
from app.utils.native_pkd import (
    decode_signed_certificate_list,
    unsigned_artifact_unavailable,
)

from marty_plugin.native_backends import NativeOperationError

logger = logging.getLogger(__name__)


class DSCListService:
    """Service for managing DSC Lists"""

    def __init__(
        self,
        db_connection: aiosqlite.Connection | None = None,
        signer_certificate_der: bytes | None = None,
    ) -> None:
        """Initialize with optional database connection"""
        self.db_connection = db_connection
        self.signer_certificate_der = signer_certificate_der

    async def get_dsc_list(self, country: str | None = None) -> DSCListResponse:
        """
        Retrieve the DSC List, optionally filtered by country.
        """
        # Get certificates from database
        certificates = []
        cert_dicts = await DatabaseManager.get_certificates("DSC", country)

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
        del country
        raise unsigned_artifact_unavailable("DSC List")

    async def upload_dsc_list(self, dsc_list_data: bytes) -> DSCListUploadResponse:
        """
        Process and store an uploaded DSC list.
        """
        try:
            if self.signer_certificate_der is None:
                raise NativeOperationError(
                    "DSC List signer certificate is not configured"
                )
            certificates = decode_signed_certificate_list(
                dsc_list_data,
                self.signer_certificate_der,
                label="DSC List",
            )

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
