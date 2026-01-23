"""
Base OpenXPKI Service - Shared implementation for OpenXPKI integration
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import urllib3

# Disable SSL warnings - should only be used in development
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class BaseOpenXPKIService:
    """
    Base service class for interacting with OpenXPKI for CSCA certificate and
    master list management operations. Contains shared functionality.
    """

    def __init__(self) -> None:
        """Initialize the OpenXPKI service with configuration settings"""
        self.base_url = os.environ.get("OPENXPKI_BASE_URL", "https://localhost:8443/api/v2")
        self.username = self._resolve_secret(
            env_var="OPENXPKI_USERNAME",
            file_var="OPENXPKI_USERNAME_FILE",
        )
        self.password = self._resolve_secret(
            env_var="OPENXPKI_PASSWORD",
            file_var="OPENXPKI_PASSWORD_FILE",
            secret_name="OpenXPKI password",
        )

        # Validate required credentials are provided
        if not self.username:
            raise ValueError(
                "OPENXPKI_USERNAME must be set via environment variable or OPENXPKI_USERNAME_FILE"
            )
        if not self.password:
            raise ValueError(
                "OPENXPKI_PASSWORD must be set via environment variable or OPENXPKI_PASSWORD_FILE"
            )

        self.realm = os.environ.get("OPENXPKI_REALM", "marty")
        self.connection_timeout = int(os.environ.get("OPENXPKI_CONN_TIMEOUT", "30"))
        self.read_timeout = int(os.environ.get("OPENXPKI_READ_TIMEOUT", "60"))
        self.verify_ssl = os.environ.get("OPENXPKI_VERIFY_SSL", "False").lower() == "true"
        self.local_store_path = os.environ.get("OPENXPKI_LOCAL_STORE", "data/trust/openxpki_sync")

        # Create local store path if it doesn't exist
        Path(self.local_store_path).mkdir(parents=True, exist_ok=True)

        # For session management
        self.session = requests.Session()
        self.session_token: str | None = None
        self.session_expiry = datetime.now(timezone.utc)

    def _resolve_secret(
        self,
        env_var: str,
        file_var: str,
        secret_name: str | None = None,
    ) -> str:
        """Resolve secret from env var or *_FILE indirection.

        Precedence:
          1. Direct environment variable
          2. File path specified via *_FILE environment variable

        Returns empty string if neither is available.
        """
        direct = os.environ.get(env_var)
        if direct:
            return direct
        file_path = os.environ.get(file_var)
        if file_path:
            try:
                content = Path(file_path).read_text(encoding="utf-8").strip()
                if content:
                    return content
                logger.warning("%s file %s is empty.", secret_name or env_var, file_path)
            except FileNotFoundError:
                logger.warning("%s file %s not found.", secret_name or env_var, file_path)
            except Exception:  # pragma: no cover
                logger.exception("Unexpected error reading secret file %s (%s)", file_path, env_var)
        return ""

    def _authenticate(self) -> bool:
        """
        Authenticate with OpenXPKI to obtain a session token

        Returns:
            bool: True if authentication was successful, False otherwise
        """
        try:
            # Check if we already have a valid session
            if self.session_token and datetime.now(timezone.utc) < self.session_expiry:
                return True

            # Build auth request
            auth_data = {"login": self.username, "passwd": self.password, "realm": self.realm}

            logger.debug("Attempting authentication with OpenXPKI...")
            response = requests.post(
                f"{self.base_url}/login",
                json=auth_data,
                timeout=(self.connection_timeout, self.read_timeout),
                verify=self.verify_ssl,
            )

            if response.status_code == 200:
                data = response.json()
                self.session_token = data.get("session_id")
                if self.session_token:
                    # Set session expiry (typically 1 hour)
                    self.session_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
                    logger.debug("Successfully authenticated with OpenXPKI")
                    return True
                else:
                    logger.error("Authentication response missing session_id")
                    return False
            else:
                logger.error("Authentication failed with status: %d", response.status_code)
                return False

        except Exception as e:
            logger.exception("Error during authentication: %s", e)
            return False

    def _api_request(
        self, endpoint: str, method: str = "GET", data: dict[str, Any] | None = None
    ) -> tuple[bool, Any]:
        """
        Make an authenticated API request to OpenXPKI

        Args:
            endpoint: API endpoint (relative to base_url)
            method: HTTP method
            data: Request data

        Returns:
            Tuple of (success: bool, response_data: Any)
        """
        try:
            # Ensure we're authenticated
            if not self._authenticate():
                return False, {"error": "Authentication failed"}

            url = f"{self.base_url}/{endpoint.lstrip('/')}"
            headers = {
                "Authorization": f"Bearer {self.session_token}",
                "Content-Type": "application/json",
            }

            logger.debug("Making %s request to %s", method, url)

            if method.upper() == "POST":
                response = requests.post(
                    url,
                    json=data,
                    headers=headers,
                    timeout=(self.connection_timeout, self.read_timeout),
                    verify=self.verify_ssl,
                )
            elif method.upper() == "PUT":
                response = requests.put(
                    url,
                    json=data,
                    headers=headers,
                    timeout=(self.connection_timeout, self.read_timeout),
                    verify=self.verify_ssl,
                )
            else:  # GET
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=(self.connection_timeout, self.read_timeout),
                    verify=self.verify_ssl,
                )

            if response.status_code == 200:
                return True, response.json()
            elif response.status_code == 401:
                # Session might have expired, clear token and retry once
                self.session_token = None
                if self._authenticate():
                    headers["Authorization"] = f"Bearer {self.session_token}"
                    if method.upper() == "POST":
                        response = requests.post(
                            url,
                            json=data,
                            headers=headers,
                            timeout=(self.connection_timeout, self.read_timeout),
                            verify=self.verify_ssl,
                        )
                    elif method.upper() == "PUT":
                        response = requests.put(
                            url,
                            json=data,
                            headers=headers,
                            timeout=(self.connection_timeout, self.read_timeout),
                            verify=self.verify_ssl,
                        )
                    else:
                        response = requests.get(
                            url,
                            headers=headers,
                            timeout=(self.connection_timeout, self.read_timeout),
                            verify=self.verify_ssl,
                        )

                    if response.status_code == 200:
                        return True, response.json()

                return False, {"error": "Authentication failed", "status": response.status_code}
            else:
                logger.error("API request failed: %d - %s", response.status_code, response.text)
                return False, {
                    "error": f"Request failed: {response.status_code}",
                    "details": response.text,
                }

        except Exception as e:
            logger.exception("Error during API request: %s", e)
            return False, {"error": str(e)}

    def get_server_status(self) -> dict[str, Any]:
        """
        Get OpenXPKI server status

        Returns:
            dict: Server status information
        """
        success, response = self._api_request("status")
        if success:
            return {"status": "operational", "server_info": response, "connected": True}
        else:
            return {
                "status": "error",
                "error": response.get("error", "Unknown error"),
                "connected": False,
            }
