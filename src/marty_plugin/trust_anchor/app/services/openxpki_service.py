"""
OpenXPKI Service Integration (Trust Anchor Service)
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from marty_common.services.base_openxpki_service import BaseOpenXPKIService

logger = logging.getLogger(__name__)


class OpenXPKIService(BaseOpenXPKIService):
    """
    Trust Anchor specific OpenXPKI integration.
    Extends base functionality with trust anchor specific operations.
    """

    def import_master_list(
        self, master_list_data: bytes, format_type: str = "DER"
    ) -> dict[str, Any]:
        """
        Import master list (PKD) data to OpenXPKI

        Args:
            master_list_data: The master list data as bytes
            format_type: The format of the data (DER or PEM)

        Returns:
            dict: Response from OpenXPKI import operation
        """
        try:
            logger.info("Importing master list to OpenXPKI (format: %s)", format_type)

            # Convert to PEM if needed
            if format_type.upper() == "DER":
                # Convert DER to PEM
                pem_data = (
                    "-----BEGIN CERTIFICATE-----\n"
                    + base64.b64encode(master_list_data).decode("ascii")
                    + "\n-----END CERTIFICATE-----"
                )
            else:
                # Assume it's already PEM
                pem_data = master_list_data.decode("utf-8", errors="ignore")

            # Prepare import request
            import_data = {
                "workflow": "import_master_list",
                "params": {"data": pem_data, "format": "PEM", "source": "TRUST_ANCHOR"},
            }

            success, response = self._api_request("workflow/start", "POST", import_data)

            if success:
                logger.info("Master list import initiated successfully")
                return {
                    "status": "success",
                    "workflow_id": response.get("workflow_id"),
                    "message": "Import initiated",
                }

            logger.error("Master list import failed: %s", response)
            return {"status": "error", "error": response.get("error", "Unknown error")}

        except Exception as e:
            logger.exception("Error importing master list")
            return {"status": "error", "error": str(e)}

    def get_master_list_status(self, workflow_id: str) -> dict[str, Any]:
        """
        Get status of master list import workflow

        Args:
            workflow_id: The workflow ID from import operation

        Returns:
            dict: Workflow status information
        """
        try:
            success, response = self._api_request(f"workflow/{workflow_id}/status")

            if success:
                return {
                    "status": "success",
                    "workflow_status": response.get("status"),
                    "details": response,
                }

            return {
                "status": "error",
                "error": response.get("error", "Failed to get workflow status"),
            }

        except Exception as e:
            logger.exception("Error getting workflow status")
            return {"status": "error", "error": str(e)}

    def import_csca_certificate(
        self, certificate_data: bytes, country_code: str, format_type: str = "DER"
    ) -> dict[str, Any]:
        """
        Import CSCA certificate to OpenXPKI

        Args:
            certificate_data: The certificate data as bytes
            country_code: ISO country code
            format_type: The format of the data (DER or PEM)

        Returns:
            dict: Response from OpenXPKI import operation
        """
        try:
            logger.info("Importing CSCA certificate for %s (format: %s)", country_code, format_type)

            # Convert to PEM if needed
            if format_type.upper() == "DER":
                pem_data = (
                    "-----BEGIN CERTIFICATE-----\n"
                    + base64.b64encode(certificate_data).decode("ascii")
                    + "\n-----END CERTIFICATE-----"
                )
            else:
                pem_data = certificate_data.decode("utf-8", errors="ignore")

            # Prepare import request
            import_data = {
                "workflow": "import_csca_certificate",
                "params": {
                    "data": pem_data,
                    "country": country_code,
                    "format": "PEM",
                    "source": "TRUST_ANCHOR",
                },
            }

            success, response = self._api_request("workflow/start", "POST", import_data)

            if success:
                logger.info("CSCA certificate import initiated for %s", country_code)
                return {
                    "status": "success",
                    "workflow_id": response.get("workflow_id"),
                    "country": country_code,
                    "message": "Import initiated",
                }

            logger.error("CSCA certificate import failed: %s", response)
            return {"status": "error", "error": response.get("error", "Unknown error")}

        except Exception as e:
            logger.exception("Error importing CSCA certificate")
            return {"status": "error", "error": str(e)}
