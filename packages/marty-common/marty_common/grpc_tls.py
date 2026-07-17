"""TLS helpers for Marty gRPC services."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import grpc

LOGGER = logging.getLogger(__name__)


def build_client_credentials(tls_options: dict[str, object]) -> grpc.ChannelCredentials:
    """Create channel credentials for mTLS client connections.

    TLS is ALWAYS required for client connections.
    """

    ca_bytes = _read_file_if_exists(tls_options.get("client_ca"))
    cert_bytes = _read_file_if_exists(tls_options.get("client_cert"))
    key_bytes = _read_file_if_exists(tls_options.get("client_key"))

    if not ca_bytes:
        LOGGER.warning("No client CA configured; using system CA for TLS")

    if not cert_bytes or not key_bytes:
        LOGGER.warning("Client certificate/key not configured; using TLS without client auth")
        cert_bytes = None
        key_bytes = None

    return grpc.ssl_channel_credentials(
        root_certificates=ca_bytes,
        private_key=key_bytes,
        certificate_chain=cert_bytes,
    )


def configure_server_security(tls_options: dict[str, object]) -> grpc.ServerCredentials:
    """Create server credentials for TLS/mTLS configuration.

    TLS is ALWAYS required - no backward compatibility.

    Returns ServerCredentials for TLS/mTLS configuration.
    Raises RuntimeError if TLS cannot be configured.
    """
    # Check if ACME is enabled
    acme_enabled = tls_options.get("acme_enabled", False)
    if acme_enabled:
        return _configure_acme_tls(tls_options)

    cert_bytes = _read_file_if_exists(tls_options.get("server_cert"))
    key_bytes = _read_file_if_exists(tls_options.get("server_key"))

    if not cert_bytes or not key_bytes:
        raise RuntimeError(
            "TLS is required but server certificate/key missing. "
            "Provide valid server_cert and server_key paths or enable ACME."
        )

    # mTLS is enabled by default
    require_client = bool(tls_options.get("require_client_auth", True))
    ca_bytes = _read_file_if_exists(tls_options.get("client_ca"))

    # Support for mTLS toggle
    mtls_enabled = bool(tls_options.get("mtls", True))
    if mtls_enabled and ca_bytes:
        require_client = True
    elif mtls_enabled and not ca_bytes:
        raise RuntimeError(
            "mTLS is enabled but client CA certificate missing. " "Provide valid client_ca path."
        )

    credentials = grpc.ssl_server_credentials(
        [(key_bytes, cert_bytes)],
        root_certificates=ca_bytes,
        require_client_auth=require_client,
    )

    LOGGER.info(
        "gRPC TLS configured (client auth=%s, mTLS=%s)",
        "required" if require_client else "optional",
        "enabled" if mtls_enabled else "disabled",
    )
    return credentials


def _configure_acme_tls(tls_options: dict[str, object]) -> grpc.ServerCredentials:
    """Configure TLS using ACME-managed certificates."""
    acme_domain = tls_options.get("acme_domain")
    acme_cert_dir = tls_options.get("acme_cert_dir", "data/acme_certs")

    if not acme_domain or not isinstance(acme_domain, str):
        raise RuntimeError("ACME is enabled but acme_domain not specified or invalid")

    if not isinstance(acme_cert_dir, str):
        acme_cert_dir = str(acme_cert_dir)

    # Build paths to ACME-managed certificates
    cert_path = Path(acme_cert_dir) / f"{acme_domain}.crt"
    key_path = Path(acme_cert_dir) / f"{acme_domain}.key"

    # Check if certificates exist
    if not cert_path.exists() or not key_path.exists():
        LOGGER.warning(
            "ACME certificates not found at %s and %s, attempting to request them",
            cert_path,
            key_path,
        )

        # Try to request certificate automatically
        try:
            _request_acme_certificate(tls_options)
        except Exception as e:
            raise RuntimeError(
                f"ACME certificates not found and automatic request failed: {e}"
            ) from e

    # Load the certificates
    cert_bytes = cert_path.read_bytes()
    key_bytes = key_path.read_bytes()

    # For ACME certificates, typically no client authentication
    require_client = bool(tls_options.get("require_client_auth", False))
    ca_bytes = None

    if require_client:
        ca_bytes = _read_file_if_exists(tls_options.get("client_ca"))
        if not ca_bytes:
            LOGGER.warning("Client authentication requested but no client CA found")

    credentials = grpc.ssl_server_credentials(
        [(key_bytes, cert_bytes)],
        root_certificates=ca_bytes,
        require_client_auth=require_client,
    )

    LOGGER.info(
        "gRPC TLS configured with ACME certificate for domain %s (client auth=%s)",
        acme_domain,
        "required" if require_client else "disabled",
    )
    return credentials


def _request_acme_certificate(tls_options: dict[str, object]) -> None:
    """Request a certificate using ACME client."""
    try:
        # Import here to avoid circular dependencies
        from marty_common.acme_client import create_acme_client
    except ImportError as e:
        raise RuntimeError("ACME client not available") from e

    acme_domain = tls_options.get("acme_domain")
    acme_server = tls_options.get("acme_server", "pebble")
    acme_email = tls_options.get("acme_email")
    acme_cert_dir = tls_options.get("acme_cert_dir", "data/acme_certs")

    # Type validation
    if not acme_domain or not isinstance(acme_domain, str):
        raise RuntimeError("Invalid acme_domain")
    if not isinstance(acme_server, str):
        acme_server = str(acme_server)
    if acme_email is not None and not isinstance(acme_email, str):
        acme_email = str(acme_email)
    if not isinstance(acme_cert_dir, str):
        acme_cert_dir = str(acme_cert_dir)

    async def request_cert():
        async with await create_acme_client(
            server=acme_server,
            contact_email=acme_email,
            cert_storage_dir=acme_cert_dir,
        ) as client:
            await client.request_certificate(acme_domain)

    # Run the async function
    try:
        asyncio.run(request_cert())
        LOGGER.info("Successfully requested ACME certificate for %s", acme_domain)
    except Exception as e:
        LOGGER.exception("Failed to request ACME certificate")
        raise


async def ensure_acme_certificate(
    domain: str,
    acme_server: str = "pebble",
    contact_email: str | None = None,
    cert_storage_dir: str = "data/acme_certs",
    days_before_expiry: int = 30,
) -> tuple[str, str]:
    """
    Ensure an ACME certificate exists and is valid for the given domain.

    Args:
        domain: Domain name for the certificate
        acme_server: ACME server to use
        contact_email: Contact email for ACME account
        cert_storage_dir: Directory to store certificates
        days_before_expiry: Renew certificate if it expires within this many days

    Returns:
        Tuple of (certificate_path, private_key_path)
    """
    try:
        from marty_common.acme_client import create_acme_client
    except ImportError as e:
        raise RuntimeError("ACME client not available") from e

    cert_path = Path(cert_storage_dir) / f"{domain}.crt"
    key_path = Path(cert_storage_dir) / f"{domain}.key"

    async with await create_acme_client(
        server=acme_server,
        contact_email=contact_email,
        cert_storage_dir=cert_storage_dir,
    ) as client:
        # Check if renewal is needed or certificate doesn't exist
        renewed = await client.renew_certificate(
            domain=domain,
            cert_path=str(cert_path),
            key_path=str(key_path),
            days_before_expiry=days_before_expiry,
        )

        if renewed:
            LOGGER.info("Certificate for %s renewed", domain)
        else:
            LOGGER.info("Certificate for %s is up to date", domain)

    return str(cert_path), str(key_path)


def is_acme_enabled(tls_options: dict[str, object]) -> bool:
    """Check if ACME is enabled in TLS options."""
    return bool(tls_options.get("acme_enabled", False))


def get_acme_config_from_env() -> dict[str, Any]:
    """Get ACME configuration from environment variables."""
    config = {}

    if os.getenv("ACME_ENABLED", "").lower() in ("true", "1", "yes"):
        config["acme_enabled"] = True
        config["acme_domain"] = os.getenv("ACME_DOMAIN")
        config["acme_server"] = os.getenv("ACME_SERVER", "pebble")
        config["acme_email"] = os.getenv("ACME_EMAIL")
        config["acme_cert_dir"] = os.getenv("ACME_CERT_DIR", "data/acme_certs")

    return config


def _read_file_if_exists(path_value: object) -> bytes | None:
    if not path_value:
        return None
    path = Path(str(path_value))
    if not path.exists():
        LOGGER.warning("TLS material not found at %s", path)
        return None
    return path.read_bytes()


__all__ = [
    "build_client_credentials",
    "configure_server_security",
    "ensure_acme_certificate",
    "is_acme_enabled",
    "get_acme_config_from_env",
]
