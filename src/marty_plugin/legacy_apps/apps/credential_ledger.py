"""Entry point for the credential ledger event consumer."""

from __future__ import annotations

import asyncio
import logging

from apps.runtime import build_dependencies_async
from marty_plugin.common.config import Config as MartyConfig
from marty_plugin.lib.credential_ledger import CredentialLedgerService

logger = logging.getLogger(__name__)


async def main_async() -> None:
    runtime_config = MartyConfig()
    dependencies = await build_dependencies_async(runtime_config)

    ledger_service = CredentialLedgerService(
        dependencies.database,
        runtime_config.event_bus(),
    )
    dependencies.register_shutdown_hook(ledger_service.stop)

    await ledger_service.start()
    logger.info("Credential ledger service started")

    try:
        await ledger_service.wait_until_stopped()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutdown signal received by credential ledger")
    finally:
        await ledger_service.stop()
        await dependencies.shutdown()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
