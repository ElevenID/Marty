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
        raise RuntimeError(
            "Automatic Python ACME issuance is retired; provision TLS certificates through the Rust managed-signing owner"
        )

    cert_bytes = _read_file_if_exists(tls_options.get("server_cert"))
    key_bytes = _read_file_if_exists(tls_options.get("server_key"))

    if not cert_bytes or not key_bytes:
        raise RuntimeError(
            "TLS is required but server certificate/key missing. "
            "Provide valid externally provisioned server_cert and server_key paths."
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
    "is_acme_enabled",
    "get_acme_config_from_env",
]
