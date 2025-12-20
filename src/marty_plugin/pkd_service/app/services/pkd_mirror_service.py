from __future__ import annotations

"""
PKD Mirror Service Implementation

This service implements the PKD mirror functionality, which allows synchronization
with an external ICAO Public Key Directory (PKD) to obtain and maintain up-to-date
certificates for document validation.

The PKD Mirror Service periodically connects to the ICAO PKD,
downloads certificates and CRLs, and stores them in the local certificate store.
"""

import logging
import threading
import time
from datetime import datetime, timezone

from app.db.certificate_store import CertificateStore
from app.utils.certificate_validator import CertificateValidator
from app.utils.http_client import HttpClient
from app.utils.pkd_payloads import parse_certificate_payload
# Use Rust crypto_bridge for certificate operations
from marty_plugin.common.crypto_bridge import Certificate


class PKDMirrorService:
    """
    Service for mirroring certificates from ICAO PKD.

    This service connects to the ICAO Public Key Directory (PKD),
    downloads certificates and certificate revocation lists (CRLs),
    validates them, and stores them in the local certificate store.
    """

    _COMPONENT_ALIASES = {
        "csca": "csca",
        "masterlist": "csca",
        "csca_certificates": "csca",
        "csca-certificates": "csca",
        "dsclist": "dsc",
        "dsc": "dsc",
        "dsc_certificates": "dsc",
        "dsc-certificates": "dsc",
        "crl": "crl",
        "crls": "crl",
    }

    def __init__(
        self,
        pkd_url: str,
        sync_interval: int = 3600,
        logger=None,
        trust_roots: list[str | Certificate] | None = None,
        other_certs_for_validation: list[str | Certificate] | None = None,
    ) -> None:
        """
        Initialize the PKD Mirror Service.

        Args:
            pkd_url: URL of the ICAO PKD server
            sync_interval: Interval between synchronizations (in seconds)
            logger: Logger instance
            trust_roots: Optional list of trust root certificates for the validator.
            other_certs_for_validation: Optional list of other certificates for the validator.
        """
        self.pkd_url = pkd_url.rstrip("/")
        self.sync_interval = sync_interval
        self.logger = logger or logging.getLogger(__name__)
        self.http_client = HttpClient()
        self.certificate_store = CertificateStore()
        self.is_syncing = False
        self.last_sync_time = None
        self.sync_thread = None
        # Initialize CertificateValidator with trust roots if provided
        self.cert_validator = CertificateValidator(
            trust_roots=trust_roots, other_certs=other_certs_for_validation, logger=self.logger
        )

    def start_sync_scheduler(self) -> None:
        """
        Start the synchronization scheduler.

        This method starts a background thread that periodically synchronizes
        with the ICAO PKD based on the configured sync interval.
        """
        self.logger.info(
            f"Starting PKD mirror sync scheduler with interval {self.sync_interval} seconds"
        )

        while True:
            try:
                self.sync()
                time.sleep(self.sync_interval)
            except Exception as e:
                self.logger.exception(f"Error in PKD mirror sync scheduler: {e}")
                # Sleep for a shorter interval before retrying after an error
                time.sleep(min(300, self.sync_interval))  # Sleep for at most 5 minutes

    def start_sync_thread(self) -> None:
        """
        Start the synchronization in a background thread.
        """
        if self.sync_thread and self.sync_thread.is_alive():
            self.logger.warning("PKD mirror sync thread is already running")
            return

        self.sync_thread = threading.Thread(target=self.start_sync_scheduler, daemon=True)
        self.sync_thread.start()
        self.logger.info("PKD mirror sync thread started")

    def stop_sync_thread(self) -> None:
        """
        Stop the synchronization thread.

        Note: This method does not actually stop the thread, as Python threads
        cannot be forcibly terminated. It simply sets a flag that the thread
        should exit at the next opportunity.
        """
        self.is_syncing = False
        self.logger.info("PKD mirror sync thread stop signal sent")

    def sync(self) -> bool:
        """
        Synchronize with the ICAO PKD.

        Returns:
            bool: True if synchronization was successful, False otherwise
        """
        self.logger.info("Starting PKD mirror synchronization")
        self.is_syncing = True
        success = True

        try:
            component_results = self.sync_components(["csca", "dsc", "crl"])
            success = all(
                component_results.get(component, False) for component in ("csca", "dsc", "crl")
            )

            # Update last sync time if at least one component was synced successfully
            if success:
                self.last_sync_time = datetime.now(tz=timezone.utc)
                self.logger.info("PKD mirror synchronization completed successfully")
            else:
                self.logger.warning("PKD mirror synchronization completed with errors")

        except Exception as e:
            self.logger.exception(f"Error during PKD mirror synchronization: {e}")
            success = False

        self.is_syncing = False
        return success

    def _download_and_store_certificates(self, endpoint: str, store_func) -> bool:
        """
        Download and store certificates from a specific endpoint.

        Args:
            endpoint: PKD endpoint to download from
            store_func: Function to store the downloaded data

        Returns:
            bool: True if download and storage were successful, False otherwise
        """
        url = f"{self.pkd_url}/{endpoint}"
        self.logger.info(f"Downloading from PKD endpoint: {url}")

        try:
            response = self.http_client.get(url)

            if response.status_code != 200:
                self.logger.error(f"Failed to download from {url}: HTTP {response.status_code}")
                return False

            data = response.content

            # Determine usage based on endpoint for more specific validation
            validation_usage = None
            if endpoint == "CscaCertificates":
                validation_usage = "key_cert_sign"  # CSCA certs sign other certs
            elif endpoint == "DscCertificates":
                validation_usage = "digital_signature"  # DSC certs sign data

            if "Certificates" in endpoint and not self.validate_certificates(
                data, usage=validation_usage
            ):
                self.logger.error(f"Certificate validation failed for {endpoint}")
                return False

            # Store the certificates or CRLs
            store_func(data)
            self.logger.info(f"Successfully downloaded and stored {endpoint}")

        except Exception as e:
            self.logger.exception(f"Error downloading or storing {endpoint}: {e}")
            return False
        else:
            return True

    def resolve_component(self, component: str) -> str | None:
        """Resolve a component alias to its canonical name."""

        if not component:
            return None
        return self._COMPONENT_ALIASES.get(component.lower())

    def sync_components(self, components: list[str] | None) -> dict[str, bool]:
        """Synchronize a subset of PKD components."""

        handler_map = {
            "csca": ("CscaCertificates", self.certificate_store.store_csca_certificates),
            "dsc": ("DscCertificates", self.certificate_store.store_dsc_certificates),
            "crl": ("CRLs", self.certificate_store.store_crls),
        }

        requested = components or ["csca", "dsc", "crl"]
        results: dict[str, bool] = {}

        for entry in requested:
            canonical = self.resolve_component(entry)
            if canonical is None:
                self.logger.warning("Skipping unknown PKD component: %s", entry)
                results[entry.lower()] = False
                continue

            endpoint, store_func = handler_map[canonical]
            success = self._download_and_store_certificates(endpoint, store_func)
            results[canonical] = success

        return results

    def get_last_sync_time(self) -> datetime | None:
        """
        Get the time of the last successful synchronization.

        Returns:
            datetime or None: The time of the last successful sync, or None if no sync has occurred
        """
        return self.last_sync_time

    def validate_certificates(
        self, cert_data: bytes, usage: str | None = "digital_signature"
    ) -> bool:
        """
        Validate a batch of certificates.

        Args:
            cert_data: Binary certificate data (potentially multiple PEM/DER certs concatenated).
            usage: The key usage to validate for (e.g., 'digital_signature', 'key_cert_sign').
                   Passed to individual certificate validation.

        Returns:
            bool: True if all certificates are valid, False otherwise
        """
        try:
            certificates = self._parse_certificates(cert_data)
            if not certificates:
                self.logger.warning("No certificates found in provided data for validation.")
                return False

            all_valid = True
            for cert in certificates:
                if not self.cert_validator.validate(
                    cert, usage=usage if usage else "digital_signature"
                ):
                    self.logger.warning(
                        f"Validation failed for certificate: {cert.subject.rfc4514_string() if cert else 'Unknown'}"
                    )
                    all_valid = False

        except Exception as e:
            self.logger.exception(f"Certificate validation error: {e}")
            return False
        else:
            return all_valid

    def validate_certificate(
        self,
        certificate: str | bytes | Certificate,
        usage: str | None = "digital_signature",
    ) -> bool:
        """
        Validate a single certificate.

        Args:
            certificate: Certificate to validate (PEM string, DER bytes, or x509.Certificate object).
            usage: The key usage to validate for.

        Returns:
            bool: True if the certificate is valid, False otherwise
        """
        try:
            return self.cert_validator.validate(
                certificate, usage=usage if usage else "digital_signature"
            )

        except Exception as e:
            self.logger.exception(f"Error validating certificate: {e}")
            return False

    def _parse_certificates(self, cert_data: bytes) -> list[Certificate]:
        """Parse ICAO master list payloads into crypto_bridge Certificate objects."""

        parsed = []
        for cert in parse_certificate_payload(cert_data):
            try:
                parsed.append(
                    Certificate.from_der(cert.certificate_data)
                )
            except ValueError as exc:  # pragma: no cover - logged for visibility in mirror logs
                self.logger.debug("Certificate payload decode failed for %s: %s", cert.subject, exc)

        if not parsed:
            self.logger.debug("No certificates recovered from payload for validation")

        return parsed
