#!/usr/bin/env python3
"""
Certificate Revocation Service.

This service is responsible for:
1. Checking certificate revocation status
2. Caching revocation results for performance
3. Supporting bulk revocation status checking
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Import shared utilities
from marty_common.certificate import CertificateProcessor
from marty_common.service_config_factory import get_config_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CertificateRevocationService:
    """
    Service for checking certificate revocation status.

    This service checks if certificates have been revoked using OpenXPKI's
    verification capabilities. It caches results to improve performance and
    reduce load on the certificate authority.
    """

    def __init__(self, openxpki_service, cache_file=None, cache_ttl_hours=24) -> None:
        """
        Initialize the Certificate Revocation Service.

        Args:
            openxpki_service: The OpenXPKI service to use for verification
            cache_file: Path to the file for caching revocation results
            cache_ttl_hours: How long to keep results in cache (in hours)
        """
        self.openxpki_service = openxpki_service
        self.cache_ttl_hours = cache_ttl_hours

        # Initialize shared utilities
        self.config_manager = get_config_manager("trust-anchor")
        self.cert_processor = CertificateProcessor()

        # Use ConfigurationManager for path resolution
        data_dir = self.config_manager.get_env_path("DATA_DIR") or Path("data")
        default_cache_path = data_dir / "trust" / "revocation_cache.json"
        self.cache_file = Path(cache_file or default_cache_path)

        # Ensure cache directory exists
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Initialized Certificate Revocation Service with cache TTL of {cache_ttl_hours} hours"
        )

    def _get_certificate_fingerprint(self, certificate_data: bytes) -> str:
        """
        Generate a unique fingerprint for a certificate to use as cache key.

        Args:
            certificate_data: Raw certificate data

        Returns:
            str: Hex-encoded SHA-256 hash of the certificate data
        """
        return hashlib.sha256(certificate_data).hexdigest()

    def _load_cache(self) -> dict[str, dict[str, Any]]:
        """
        Load the revocation cache from file.

        Returns:
            dict: Mapping of certificate fingerprints to cached results
        """
        try:
            if self.cache_file.exists():
                content = self.cache_file.read_text()
                if content:
                    return json.loads(content)
                    if content:
                        return json.loads(content)

            logger.debug(f"No cache file found at {self.cache_file} or file is empty")
        except json.JSONDecodeError as e:
            logger.exception(f"Error decoding cache JSON: {e!s}")
            return {}
        except Exception as e:
            logger.exception(f"Error loading cache: {e!s}")
            return {}
        else:
            return {}

    def _save_cache(self, cache: dict[str, dict[str, Any]]) -> None:
        """
        Save the revocation cache to file.

        Args:
            cache: Mapping of certificate fingerprints to cached results
        """
        try:
            with open(self.cache_file, "w") as f:
                json.dump(cache, f, indent=2)
                logger.debug(f"Cache saved to {self.cache_file}")
        except Exception as e:
            logger.exception(f"Error saving cache: {e!s}")

    def clean_expired_cache(self) -> None:
        """
        Remove expired entries from the cache.
        """
        cache = self._load_cache()
        now = datetime.now()
        expired_keys = []

        # Find expired entries
        for fingerprint, entry in cache.items():
            try:
                timestamp = datetime.fromisoformat(entry.get("timestamp", ""))
                age = now - timestamp

                if age > timedelta(hours=self.cache_ttl_hours):
                    expired_keys.append(fingerprint)
            except (ValueError, TypeError):
                # If timestamp is invalid, mark for removal
                expired_keys.append(fingerprint)

        # Remove expired entries
        for key in expired_keys:
            del cache[key]

        # Save updated cache
        if expired_keys:
            logger.info(f"Removed {len(expired_keys)} expired entries from revocation cache")
            self._save_cache(cache)

    def check_revocation_status(self, certificate_data: bytes) -> dict[str, Any]:
        """
        Check if a certificate has been revoked.

        Args:
            certificate_data: Raw certificate data

        Returns:
            dict: Revocation status and certificate details
        """
        # Generate fingerprint for cache lookup
        fingerprint = self._get_certificate_fingerprint(certificate_data)

        # Check cache first
        cache = self._load_cache()
        now = datetime.now()

        if fingerprint in cache:
            try:
                entry = cache[fingerprint]
                timestamp = datetime.fromisoformat(entry.get("timestamp", ""))
                age = now - timestamp

                # If cache entry is still valid, use it
                if age <= timedelta(hours=self.cache_ttl_hours):
                    logger.debug(
                        f"Using cached revocation status for certificate {fingerprint[:8]}"
                    )
                    return entry
            except (ValueError, TypeError):
                # Invalid timestamp, will refresh from source
                logger.debug(f"Invalid timestamp in cache for {fingerprint[:8]}")

        # Cache miss or expired, check with OpenXPKI
        logger.debug(f"Checking revocation status for certificate {fingerprint[:8]}")

        # Call OpenXPKI to verify the certificate (including revocation check)
        result = self.openxpki_service.verify_certificate(
            certificate_data=certificate_data, format_type="DER", check_revocation=True
        )

        # Add timestamp and cache the result
        result["timestamp"] = now.isoformat()

        # Update cache
        cache[fingerprint] = result
        self._save_cache(cache)

        return result

    def bulk_check_revocation_status(self, certificates: list[bytes]) -> list[dict[str, Any]]:
        """
        Check revocation status for multiple certificates.

        Args:
            certificates: List of raw certificate data

        Returns:
            list: List of revocation status dictionaries
        """
        results = []

        for cert_data in certificates:
            result = self.check_revocation_status(cert_data)
            results.append(result)

        return results
