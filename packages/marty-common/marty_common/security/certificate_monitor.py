"""
Certificate expiry monitoring and notification system for Marty services.

Provides automated monitoring of certificate lifecycles with proactive
expiry notifications and renewal recommendations to prevent service disruptions.
"""

from __future__ import annotations

import logging
import socket
import ssl
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from marty_common.crypto_bridge import (
    certificate_pem_to_der,
    get_certificate_info,
)

logger = logging.getLogger(__name__)


class CertificateType(Enum):
    """Types of certificates to monitor."""

    ROOT_CA = "root_ca"
    INTERMEDIATE_CA = "intermediate_ca"
    DOCUMENT_SIGNER = "document_signer"
    TLS_SERVER = "tls_server"
    CLIENT_AUTH = "client_auth"
    CODE_SIGNING = "code_signing"
    CSCA = "csca"  # Country Signing Certificate Authority
    DSC = "dsc"  # Document Security Certificate


class ExpiryStatus(Enum):
    """Certificate expiry status."""

    VALID = "valid"
    WARNING = "warning"  # Within warning period
    CRITICAL = "critical"  # Within critical period
    EXPIRED = "expired"
    RENEWAL_SCHEDULED = "renewal_scheduled"
    RENEWED = "renewed"


@dataclass
class CertificateInfo:
    """Certificate information for monitoring."""

    cert_id: str
    common_name: str
    cert_type: CertificateType
    issuer: str
    serial_number: str
    not_before: datetime
    not_after: datetime
    source_type: str  # "file", "url", "service", "database"
    source_location: str
    fingerprint_sha256: str
    subject_alt_names: list[str] = field(default_factory=list)
    key_usage: list[str] = field(default_factory=list)
    extended_key_usage: list[str] = field(default_factory=list)
    is_ca: bool = False
    last_checked: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expiry_status: ExpiryStatus = ExpiryStatus.VALID
    days_until_expiry: int = 0
    renewal_requested: bool = False
    renewal_request_date: datetime | None = None
    notes: str = ""


@dataclass
class ExpiryNotification:
    """Certificate expiry notification."""

    notification_id: str
    cert_id: str
    cert_info: CertificateInfo
    notification_type: str  # "warning", "critical", "expired", "renewal_reminder"
    message: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sent_at: datetime | None = None
    acknowledged: bool = False
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None


class CertificateSource(ABC):
    """Abstract interface for certificate sources."""

    @abstractmethod
    def load_certificates(self) -> list[CertificateInfo]:
        """Load certificates from this source."""


class FileCertificateSource(CertificateSource):
    """Load certificates from files."""

    def __init__(self, file_paths: list[str]) -> None:
        self.file_paths = file_paths

    def load_certificates(self) -> list[CertificateInfo]:
        """Load certificates from PEM/DER files."""
        certificates = []

        for file_path in self.file_paths:
            try:
                with open(file_path, "rb") as f:
                    cert_data = f.read()

                # Convert to DER if PEM
                if b"-----BEGIN CERTIFICATE-----" in cert_data:
                    der_data = certificate_pem_to_der(cert_data.decode("utf-8"))
                else:
                    der_data = cert_data

                cert_info = self._extract_cert_info(der_data, file_path)
                certificates.append(cert_info)

            except Exception as e:
                logger.exception(f"Failed to load certificate from {file_path}: {e}")

        return certificates

    def _extract_cert_info(self, der_data: bytes, source: str) -> CertificateInfo:
        """Extract certificate information using Rust bindings."""
        info = get_certificate_info(der_data)

        # Parse subject DN to extract common name
        subject = info.get("subject", "")
        issuer = info.get("issuer", "")
        common_name = self._extract_dn_component(subject, "CN") or "Unknown"
        issuer_name = self._extract_dn_component(issuer, "CN") or "Unknown Issuer"

        # Parse dates from ISO 8601 strings
        not_before = datetime.fromisoformat(info["not_before"].replace("Z", "+00:00"))
        not_after = datetime.fromisoformat(info["not_after"].replace("Z", "+00:00"))

        # Extract fields from Rust bindings
        san_list = info.get("subject_alt_names", [])
        key_usage_list = [ku.lower().replace("signature", "_signature") for ku in info.get("key_usage", [])]
        is_ca = info.get("is_ca", False)
        fingerprint = info.get("fingerprint_sha256", "")

        # Determine certificate type based on attributes
        cert_type = self._determine_cert_type(common_name, key_usage_list, is_ca)

        return CertificateInfo(
            cert_id=f"file-{fingerprint[:16]}",
            common_name=common_name,
            cert_type=cert_type,
            issuer=issuer_name,
            serial_number=info.get("serial_number", ""),
            not_before=not_before,
            not_after=not_after,
            source_type="file",
            source_location=source,
            fingerprint_sha256=fingerprint,
            subject_alt_names=san_list,
            key_usage=key_usage_list,
            is_ca=is_ca,
        )

    def _extract_dn_component(self, dn: str, component: str) -> str:
        """Extract a component from an X.500 Distinguished Name string."""
        for part in dn.split(","):
            part = part.strip()
            if part.startswith(f"{component}="):
                return part[len(component) + 1:]
        return ""

    def _determine_cert_type(
        self, common_name: str, key_usage: list[str], is_ca: bool
    ) -> CertificateType:
        """Determine certificate type from attributes."""
        cn_lower = common_name.lower()

        if is_ca:
            if "root" in cn_lower:
                return CertificateType.ROOT_CA
            if "csca" in cn_lower:
                return CertificateType.CSCA
            return CertificateType.INTERMEDIATE_CA

        if "dsc" in cn_lower or "document" in cn_lower:
            return CertificateType.DSC
        if "signer" in cn_lower or "signing" in cn_lower:
            return CertificateType.DOCUMENT_SIGNER
        if "tls" in cn_lower or "server" in cn_lower:
            return CertificateType.TLS_SERVER
        return CertificateType.CLIENT_AUTH


class TLSCertificateSource(CertificateSource):
    """Load certificates from TLS endpoints."""

    def __init__(self, endpoints: list[tuple[str, int]]) -> None:
        self.endpoints = endpoints  # [(hostname, port), ...]

    def load_certificates(self) -> list[CertificateInfo]:
        """Load certificates from TLS endpoints."""
        certificates = []

        for hostname, port in self.endpoints:
            try:
                # Get certificate from TLS connection
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

                with socket.create_connection((hostname, port), timeout=10) as sock:
                    with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                        cert_der = ssock.getpeercert(True)
                        if cert_der:
                            cert_info = self._extract_cert_info(cert_der, f"{hostname}:{port}")
                            certificates.append(cert_info)

            except Exception as e:
                logger.exception(f"Failed to get certificate from {hostname}:{port}: {e}")

        return certificates

    def _extract_cert_info(self, der_data: bytes, source: str) -> CertificateInfo:
        """Extract certificate information from TLS cert using Rust bindings."""
        info = get_certificate_info(der_data)

        # Parse subject DN to extract common name
        subject = info.get("subject", "")
        issuer = info.get("issuer", "")
        common_name = self._extract_dn_component(subject, "CN") or "Unknown"
        issuer_name = self._extract_dn_component(issuer, "CN") or "Unknown Issuer"

        # Parse dates from ISO 8601 strings
        not_before = datetime.fromisoformat(info["not_before"].replace("Z", "+00:00"))
        not_after = datetime.fromisoformat(info["not_after"].replace("Z", "+00:00"))

        fingerprint = info.get("fingerprint_sha256", "")

        return CertificateInfo(
            cert_id=f"tls-{fingerprint[:16]}",
            common_name=common_name,
            cert_type=CertificateType.TLS_SERVER,
            issuer=issuer_name,
            serial_number=info.get("serial_number", ""),
            not_before=not_before,
            not_after=not_after,
            source_type="tls",
            source_location=source,
            fingerprint_sha256=fingerprint,
        )

    def _extract_dn_component(self, dn: str, component: str) -> str:
        """Extract a component from an X.500 Distinguished Name string."""
        for part in dn.split(","):
            part = part.strip()
            if part.startswith(f"{component}="):
                return part[len(component) + 1:]
        return ""


class CertificateExpiryMonitor:
    """Certificate expiry monitoring and notification system."""

    def __init__(
        self, warning_days: int = 30, critical_days: int = 7, check_interval_hours: int = 6
    ) -> None:
        self.warning_days = warning_days
        self.critical_days = critical_days
        self.check_interval_hours = check_interval_hours

        self.certificates: dict[str, CertificateInfo] = {}
        self.sources: list[CertificateSource] = []
        self.notifications: dict[str, ExpiryNotification] = {}
        self.notification_callbacks: list[Callable[[ExpiryNotification], None]] = []

        self._monitor_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def add_source(self, source: CertificateSource) -> None:
        """Add a certificate source for monitoring."""
        self.sources.append(source)
        logger.info(f"Added certificate source: {type(source).__name__}")

    def add_notification_callback(self, callback: Callable[[ExpiryNotification], None]) -> None:
        """Add callback for expiry notifications."""
        self.notification_callbacks.append(callback)

    def load_certificates(self) -> None:
        """Load certificates from all sources."""
        with self._lock:
            self.certificates.clear()

            for source in self.sources:
                try:
                    certs = source.load_certificates()
                    for cert in certs:
                        self.certificates[cert.cert_id] = cert
                        logger.debug(
                            f"Loaded certificate: {cert.common_name} (expires: {cert.not_after})"
                        )
                except Exception as e:
                    logger.exception(
                        f"Failed to load certificates from {type(source).__name__}: {e}"
                    )

        logger.info(f"Loaded {len(self.certificates)} certificates for monitoring")

    def check_expiry_status(self) -> None:
        """Check expiry status of all certificates."""
        now = datetime.now(timezone.utc)

        with self._lock:
            for cert in self.certificates.values():
                cert.last_checked = now
                cert.days_until_expiry = (cert.not_after - now).days

                # Determine expiry status
                if cert.not_after <= now:
                    cert.expiry_status = ExpiryStatus.EXPIRED
                elif cert.days_until_expiry <= self.critical_days:
                    cert.expiry_status = ExpiryStatus.CRITICAL
                elif cert.days_until_expiry <= self.warning_days:
                    cert.expiry_status = ExpiryStatus.WARNING
                else:
                    cert.expiry_status = ExpiryStatus.VALID

                # Generate notifications for status changes
                self._check_notification_needed(cert)

    def _check_notification_needed(self, cert: CertificateInfo) -> None:
        """Check if a notification should be sent for this certificate."""
        notification_type = None
        message = ""

        if cert.expiry_status == ExpiryStatus.EXPIRED:
            notification_type = "expired"
            message = f"Certificate '{cert.common_name}' has EXPIRED on {cert.not_after.strftime('%Y-%m-%d')}"
        elif cert.expiry_status == ExpiryStatus.CRITICAL:
            notification_type = "critical"
            message = f"Certificate '{cert.common_name}' expires in {cert.days_until_expiry} days ({cert.not_after.strftime('%Y-%m-%d')})"
        elif cert.expiry_status == ExpiryStatus.WARNING:
            notification_type = "warning"
            message = f"Certificate '{cert.common_name}' expires in {cert.days_until_expiry} days ({cert.not_after.strftime('%Y-%m-%d')})"

        if notification_type:
            # Check if we've already sent this type of notification recently
            existing_notifications = [
                n
                for n in self.notifications.values()
                if n.cert_id == cert.cert_id
                and n.notification_type == notification_type
                and (datetime.now(timezone.utc) - n.created_at).days < 7
            ]

            if not existing_notifications:
                self._create_notification(cert, notification_type, message)

    def _create_notification(
        self, cert: CertificateInfo, notification_type: str, message: str
    ) -> None:
        """Create and send an expiry notification."""
        notification_id = f"expiry-{cert.cert_id}-{int(datetime.now(timezone.utc).timestamp())}"

        notification = ExpiryNotification(
            notification_id=notification_id,
            cert_id=cert.cert_id,
            cert_info=cert,
            notification_type=notification_type,
            message=message,
        )

        self.notifications[notification_id] = notification

        # Send notification via callbacks
        for callback in self.notification_callbacks:
            try:
                callback(notification)
            except Exception as e:
                logger.exception(f"Error sending notification via callback: {e}")

        logger.warning(f"Certificate expiry notification: {message}")

    def start_monitoring(self) -> None:
        """Start the certificate monitoring process."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.warning("Certificate monitoring is already running")
            return

        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Certificate expiry monitoring started")

    def stop_monitoring(self) -> None:
        """Stop the certificate monitoring process."""
        if self._monitor_thread:
            self._stop_event.set()
            self._monitor_thread.join()
        logger.info("Certificate expiry monitoring stopped")

    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while not self._stop_event.is_set():
            try:
                # Load certificates and check expiry status
                self.load_certificates()
                self.check_expiry_status()

                # Wait for next check
                self._stop_event.wait(self.check_interval_hours * 3600)

            except Exception as e:
                logger.exception(f"Error in certificate monitoring loop: {e}")
                # Continue monitoring even if there's an error
                self._stop_event.wait(300)  # Wait 5 minutes before retrying

    def get_expiring_certificates(self, days_threshold: int | None = None) -> list[CertificateInfo]:
        """Get certificates that are expiring within the specified days."""
        if days_threshold is None:
            days_threshold = self.warning_days

        with self._lock:
            return [
                cert
                for cert in self.certificates.values()
                if cert.days_until_expiry <= days_threshold
                and cert.expiry_status != ExpiryStatus.EXPIRED
            ]

    def get_expired_certificates(self) -> list[CertificateInfo]:
        """Get certificates that have already expired."""
        with self._lock:
            return [
                cert
                for cert in self.certificates.values()
                if cert.expiry_status == ExpiryStatus.EXPIRED
            ]

    def acknowledge_notification(self, notification_id: str, acknowledged_by: str) -> bool:
        """Acknowledge a certificate expiry notification."""
        with self._lock:
            notification = self.notifications.get(notification_id)
            if notification:
                notification.acknowledged = True
                notification.acknowledged_by = acknowledged_by
                notification.acknowledged_at = datetime.now(timezone.utc)
                logger.info(f"Notification {notification_id} acknowledged by {acknowledged_by}")
                return True
            return False

    def request_renewal(self, cert_id: str) -> bool:
        """Request renewal for a certificate."""
        with self._lock:
            cert = self.certificates.get(cert_id)
            if cert:
                cert.renewal_requested = True
                cert.renewal_request_date = datetime.now(timezone.utc)
                cert.expiry_status = ExpiryStatus.RENEWAL_SCHEDULED
                logger.info(f"Renewal requested for certificate: {cert.common_name}")
                return True
            return False

    def get_certificate_status_summary(self) -> dict[str, int]:
        """Get summary of certificate expiry status."""
        summary = {status.value: 0 for status in ExpiryStatus}

        with self._lock:
            for cert in self.certificates.values():
                summary[cert.expiry_status.value] += 1

        return summary


def create_certificate_monitor(
    warning_days: int = 30, critical_days: int = 7, check_interval_hours: int = 6
) -> CertificateExpiryMonitor:
    """Create a certificate expiry monitor with default settings."""
    return CertificateExpiryMonitor(warning_days, critical_days, check_interval_hours)


def create_file_source(cert_files: list[str]) -> FileCertificateSource:
    """Create a file-based certificate source."""
    return FileCertificateSource(cert_files)


def create_tls_source(endpoints: list[tuple[str, int]]) -> TLSCertificateSource:
    """Create a TLS endpoint certificate source."""
    return TLSCertificateSource(endpoints)
