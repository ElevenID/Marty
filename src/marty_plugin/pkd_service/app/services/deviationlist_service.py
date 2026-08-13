"""
Service for handling Deviation List operations
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

import aiosqlite
from app.db.database import DatabaseManager
from app.models.pkd_models import (
    DeviationEntry,
    DeviationListResponse,
    DeviationListUploadResponse,
    UploadStatus,
)

from marty_plugin.native_backends import NativeOperationError

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
        del country
        raise NativeOperationError(
            "Deviation List encoding is unavailable until a canonical native signed format is configured"
        )

    async def upload_deviation_list(
        self, deviation_list_data: bytes
    ) -> DeviationListUploadResponse:
        """
        Process and store an uploaded deviation list.
        """
        del deviation_list_data
        logger.error(
            "Deviation List decoding is unavailable until a canonical native parser is configured"
        )
        return DeviationListUploadResponse(
            id=uuid.uuid4(),
            version=0,
            created=datetime.now(),
            status=UploadStatus.ERROR,
            deviation_count=0,
        )
