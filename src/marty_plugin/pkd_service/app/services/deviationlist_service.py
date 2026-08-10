"""
Service for handling Deviation List operations
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
    DeviationEntry,
    DeviationListResponse,
    DeviationListUploadResponse,
    DeviationStatus,
    UploadStatus,
)
from app.utils.asn1_utils import ASN1Decoder, ASN1Encoder

logger = logging.getLogger(__name__)


class DeviationListService:
    """Service for managing Deviation Lists"""

    def __init__(self, db_connection: aiosqlite.Connection | None = None) -> None:
        """Initialize with optional database connection"""
        self.db_connection = db_connection

    async def get_deviation_list(
        self, country: str | None = None
    ) -> DeviationListResponse:
        """
        Retrieve Deviation List data, optionally filtered by country.
        """
        # Try to get deviation list from database
        deviations = []
        db_deviations = await DatabaseManager.get_deviation_list(country)

        if db_deviations:
            # Convert from database format to model
            for dev_dict in db_deviations:
                deviations.append(
                    DeviationEntry(
                        id=uuid.UUID(dev_dict["id"]),
                        country_code=dev_dict["country_code"],
                        description=dev_dict["description"],
                        status=dev_dict["status"],
                        created=dev_dict["created"],
                        updated=dev_dict["updated"],
                        details=dev_dict.get("details", {}),
                    )
                )
        # Get list of unique countries
        countries = list({dev.country_code for dev in deviations})

        return DeviationListResponse(
            id=uuid.uuid4(),
            version=1,
            created=datetime.now(),
            countries=countries,
            deviations=deviations,
        )

    async def get_deviation_list_binary(self, country: str | None = None) -> bytes:
        """
        Get the ASN.1 encoded deviation list data, optionally filtered by country.
        """
        # Get the deviation list
        deviation_list = await self.get_deviation_list(country)

        # Encode the deviation list as ASN.1
        return ASN1Encoder.encode_deviation_list(deviation_list.deviations)

    async def upload_deviation_list(
        self, deviation_list_data: bytes
    ) -> DeviationListUploadResponse:
        """
        Process and store an uploaded deviation list.
        """
        try:
            # Parse the ASN.1 deviation list data
            deviations = ASN1Decoder.decode_deviation_list(deviation_list_data)

            # Save the raw deviation list file
            storage_path = settings.DEVIATIONLIST_PATH
            os.makedirs(storage_path, exist_ok=True)

            dev_list_filename = (
                f"deviationlist-{datetime.now().strftime('%Y%m%d%H%M%S')}.dl"
            )
            dev_list_path = os.path.join(storage_path, dev_list_filename)
            with open(dev_list_path, "wb") as f:
                f.write(deviation_list_data)

            # Store in database
            deviation_count = 0
            for dev in deviations:
                # Convert to dictionary for database
                dev_dict = {
                    "id": str(dev.id),
                    "country_code": dev.country_code,
                    "description": dev.description,
                    "status": dev.status,
                    "created": dev.created,
                    "updated": dev.updated,
                    "details": dev.details,
                }

                # Store in database
                await DatabaseManager.store_deviation(dev_dict)
                deviation_count += 1

            # Log the operation
            logger.info(f"Processed deviation list with {deviation_count} entries")

            return DeviationListUploadResponse(
                id=uuid.uuid4(),
                version=1,
                created=datetime.now(),
                status=UploadStatus.PROCESSED,
                deviation_count=deviation_count,
            )

        except Exception as e:
            logger.exception(f"Failed to process deviation list: {e}")
            return DeviationListUploadResponse(
                id=uuid.uuid4(),
                version=0,
                created=datetime.now(),
                status=UploadStatus.ERROR,
                deviation_count=0,
            )
