"""
Service for automatically synchronizing CSCA master lists from trusted sources
"""

import asyncio
import logging
import os
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import aiohttp
from app.core.config import settings
from app.services.masterlist_service import MasterListService

logger = logging.getLogger(__name__)


class MasterListSyncService:
    """
    Service for automatically synchronizing CSCA master lists from trusted sources
    like ICAO PKD or national certificate authorities.
    """

    def __init__(self, master_list_service: MasterListService = None) -> None:
        """
        Initialize the sync service

        Args:
            master_list_service: The master list service to use for storing certificates
        """
        self.master_list_service = master_list_service or MasterListService()
        self.sources_config = settings.TRUSTED_SOURCES
        self.sync_interval = settings.SYNC_INTERVAL_HOURS * 3600  # Convert to seconds
        self.last_sync = {}  # Track last successful sync time for each source
        self.running = False

    async def start_sync_scheduler(self) -> None:
        """
        Start the synchronization scheduler
        """
        if self.running:
            logger.warning("Sync scheduler is already running")
            return

        self.running = True
        logger.info(f"Starting master list sync scheduler (interval: {self.sync_interval}s)")

        try:
            while self.running:
                await self.sync_all_sources()
                await asyncio.sleep(self.sync_interval)
        except asyncio.CancelledError:
            logger.info("Master list sync scheduler was cancelled")
            self.running = False
        except Exception as e:
            logger.exception(f"Error in sync scheduler: {e}")
            self.running = False
            raise

    async def sync_all_sources(self) -> None:
        """
        Synchronize with all configured trusted sources
        """
        logger.info("Starting synchronization with all trusted sources")

        # Check if sources are configured
        if not self.sources_config:
            logger.warning("No trusted sources configured for synchronization")
            return

        for source_id, source_config in self.sources_config.items():
            try:
                logger.info(f"Synchronizing with source: {source_id}")
                await self.sync_with_source(source_id, source_config)
                self.last_sync[source_id] = datetime.now()
            except Exception as e:
                logger.exception(f"Failed to sync with source {source_id}: {e}")

    async def sync_with_source(self, source_id: str, config: dict) -> None:
        """
        Synchronize with a specific trusted source

        Args:
            source_id: The ID of the source to sync with
            config: Configuration for the source
        """
        source_type = config.get("type", "").lower()

        if source_type == "icao_pkd":
            await self._sync_with_icao_pkd(config)
        elif source_type == "national_site":
            await self._sync_with_national_site(config)
        elif source_type == "file":
            await self._sync_with_file(config)
        else:
            logger.warning(f"Unknown source type: {source_type}")

    async def _sync_with_icao_pkd(self, config: dict) -> None:
        """
        Synchronize with ICAO PKD

        Args:
            config: Configuration for the ICAO PKD source
        """
        url = config.get("url")
        if not url:
            logger.error("No URL configured for ICAO PKD source")
            return

        try:
            # ICAO PKD uses special authentication
            auth_headers = await self._get_icao_auth_headers(config)

            async with aiohttp.ClientSession() as session:
                # Request the master list
                async with session.get(
                    url, headers=auth_headers, ssl=False if config.get("ignore_ssl") else None
                ) as response:
                    if response.status != 200:
                        logger.error(
                            f"Failed to retrieve master list from ICAO PKD: {response.status}"
                        )
                        return

                    # Save the master list to a temporary file
                    master_list_data = await response.read()
                    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                        temp_file.write(master_list_data)
                        temp_path = temp_file.name

            # Process the downloaded master list
            try:
                upload_response = await self.master_list_service.upload_master_list(
                    master_list_data
                )
                logger.info(
                    f"ICAO PKD sync completed: {upload_response.certificate_count} certificates processed"
                )
            finally:
                # Clean up the temporary file
                os.unlink(temp_path)

        except Exception as e:
            logger.exception(f"Error syncing with ICAO PKD: {e}")
            raise

    async def _sync_with_national_site(self, config: dict) -> None:
        """
        Synchronize with a national certificate authority site

        Args:
            config: Configuration for the national site
        """
        url = config.get("url")
        if not url:
            logger.error("No URL configured for national site")
            return

        try:
            async with aiohttp.ClientSession() as session:
                # Request the master list
                async with session.get(
                    url, ssl=False if config.get("ignore_ssl") else None
                ) as response:
                    if response.status != 200:
                        logger.error(
                            f"Failed to retrieve master list from national site: {response.status}"
                        )
                        return

                    # Read the response based on the format
                    format_type = config.get("format", "asn1").lower()

                    if format_type == "asn1":
                        master_list_data = await response.read()
                    elif format_type == "xml":
                        # Parse XML response
                        xml_data = await response.text()
                        master_list_data = self._parse_xml_master_list(xml_data, config)
                    elif format_type == "json":
                        # Parse JSON response
                        json_data = await response.json()
                        master_list_data = self._parse_json_master_list(json_data, config)
                    else:
                        logger.error(f"Unsupported format: {format_type}")
                        return

            # Process the master list
            if master_list_data:
                upload_response = await self.master_list_service.upload_master_list(
                    master_list_data
                )
                logger.info(
                    f"National site sync completed: {upload_response.certificate_count} certificates processed"
                )
            else:
                logger.warning("No master list data obtained from national site")

        except Exception as e:
            logger.exception(f"Error syncing with national site: {e}")
            raise

    async def _sync_with_file(self, config: dict) -> None:
        """
        Synchronize with a local file source (for testing or offline updates)

        Args:
            config: Configuration for the file source
        """
        file_path = config.get("path")
        if not file_path:
            logger.error("No file path configured for file source")
            return

        try:
            path = Path(file_path)
            if not path.exists():
                logger.error(f"Master list file not found: {file_path}")
                return

            with open(file_path, "rb") as file:
                master_list_data = file.read()

            # Process the master list
            upload_response = await self.master_list_service.upload_master_list(master_list_data)
            logger.info(
                f"File sync completed: {upload_response.certificate_count} certificates processed"
            )

        except Exception as e:
            logger.exception(f"Error syncing from file: {e}")
            raise

    async def _get_icao_auth_headers(self, config: dict) -> dict:
        """
        Get authentication headers for ICAO PKD requests

        Args:
            config: ICAO PKD configuration

        Returns:
            Authentication headers
        """
        # Implementation would vary based on ICAO PKD authentication requirements
        username = config.get("username")
        password = config.get("password")

        # Basic authentication
        if username and password:
            import base64

            auth_string = base64.b64encode(f"{username}:{password}".encode()).decode()
            return {"Authorization": f"Basic {auth_string}"}

        return {}

    def _parse_xml_master_list(self, xml_data: str, config: dict) -> bytes:
        """
        Parse XML master list data and convert to ASN.1 format

        Args:
            xml_data: XML master list data
            config: Source configuration

        Returns:
            ASN.1 encoded master list
        """
        # This is a placeholder for XML parsing logic
        # In a real implementation, this would parse XML according to the specific format
        # used by the certificate authority and convert to ASN.1
        try:
            root = ET.fromstring(xml_data)
            certificates = []

            # Extract certificates from the XML structure
            # This is highly dependent on the specific XML format used
            for cert_elem in root.findall(".//Certificate"):
                cert_data = cert_elem.text.strip()
                if cert_data:
                    # Convert base64 cert data to binary
                    import base64

                    cert_binary = base64.b64decode(cert_data)
                    certificates.append(cert_binary)

            # Convert to ASN.1 master list format
            # This is a simplified placeholder
            from app.utils.asn1_utils import ASN1Encoder

            return ASN1Encoder.encode_raw_certificates(certificates)

        except Exception as e:
            logger.exception(f"Error parsing XML master list: {e}")
            return None

    def _parse_json_master_list(self, json_data: dict, config: dict) -> bytes:
        """
        Parse JSON master list data and convert to ASN.1 format

        Args:
            json_data: JSON master list data
            config: Source configuration

        Returns:
            ASN.1 encoded master list
        """
        # This is a placeholder for JSON parsing logic
        try:
            certificates = []

            # Extract certificates from the JSON structure
            # This is highly dependent on the specific JSON format used
            cert_list = json_data.get("certificates", [])
            for cert_item in cert_list:
                cert_data = cert_item.get("data")
                if cert_data:
                    # Convert base64 cert data to binary
                    import base64

                    cert_binary = base64.b64decode(cert_data)
                    certificates.append(cert_binary)

            # Convert to ASN.1 master list format
            from app.utils.asn1_utils import ASN1Encoder

            return ASN1Encoder.encode_raw_certificates(certificates)

        except Exception as e:
            logger.exception(f"Error parsing JSON master list: {e}")
            return None
