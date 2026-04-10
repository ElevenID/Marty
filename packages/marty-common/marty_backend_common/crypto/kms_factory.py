"""KMS Provider Factory.

Constructs and wires KMS providers and the CredentialKeyManager from
configuration.  This is the single entry-point for dependency injection
of key management into application services.

Usage::

    from marty_backend_common.crypto.kms_factory import create_credential_key_manager

    ckm = await create_credential_key_manager()
    info = await ckm.generate_issuer_key("US", "dsc-1")
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from .credential_kms import CredentialKeyManager
from .openbao_provider import OpenBaoTransitProvider

if TYPE_CHECKING:
    from .credential_kms import ICredentialKeyManager

logger = logging.getLogger(__name__)


async def create_credential_key_manager(
    *,
    openbao_addr: str | None = None,
    openbao_token: str | None = None,
    transit_mount: str = "transit",
) -> ICredentialKeyManager | None:
    """Create a CredentialKeyManager wired to the configured KMS backend.

    Reads configuration from parameters or environment variables:
      - ``OPENBAO_ADDR`` / ``BAO_ADDR``: OpenBao server URL
      - ``OPENBAO_TOKEN`` / ``BAO_TOKEN``: authentication token

    Returns ``None`` if no KMS backend is configured (local-signing mode).
    """
    addr = openbao_addr or os.getenv("OPENBAO_ADDR") or os.getenv("BAO_ADDR")
    token = openbao_token or os.getenv("OPENBAO_TOKEN") or os.getenv("BAO_TOKEN")

    if not addr or not token:
        logger.info("No KMS backend configured — using local signing mode")
        return None

    provider = OpenBaoTransitProvider(
        bao_addr=addr,
        bao_token=token,
        transit_mount=transit_mount,
    )

    # Verify connectivity
    try:
        client = await provider._get_client()
        resp = await client.get("/v1/sys/health")
        if resp.status_code not in (200, 429, 472, 473):
            logger.warning("OpenBao health check returned %s", resp.status_code)
    except Exception as exc:
        logger.warning("Could not connect to OpenBao at %s: %s", addr, exc)
        return None

    logger.info("KMS backend: OpenBao Transit at %s", addr)
    return CredentialKeyManager(kms_provider=provider)


def create_openbao_provider(
    *,
    openbao_addr: str | None = None,
    openbao_token: str | None = None,
    transit_mount: str = "transit",
) -> OpenBaoTransitProvider | None:
    """Create an OpenBaoTransitProvider from config or env.

    Returns ``None`` if not configured.
    """
    addr = openbao_addr or os.getenv("OPENBAO_ADDR") or os.getenv("BAO_ADDR")
    token = openbao_token or os.getenv("OPENBAO_TOKEN") or os.getenv("BAO_TOKEN")

    if not addr or not token:
        return None

    return OpenBaoTransitProvider(
        bao_addr=addr,
        bao_token=token,
        transit_mount=transit_mount,
    )
