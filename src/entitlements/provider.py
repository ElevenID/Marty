"""Provider-neutral entitlement extension contract for public Marty builds."""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class EntitlementRequest:
    """A capability decision requested by a public Marty service."""

    capability: str
    subject: str | None = None
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EntitlementDecision:
    """The provider's decision without exposing billing or plan concepts."""

    allowed: bool
    reason: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


class EntitlementProvider(Protocol):
    """Structural interface implemented by optional downstream extensions."""

    async def authorize(self, request: EntitlementRequest) -> EntitlementDecision:
        """Return whether the requested capability is available."""


class NoopEntitlementProvider:
    """Public default: Marty has no commercial capability restrictions."""

    async def authorize(self, request: EntitlementRequest) -> EntitlementDecision:
        return EntitlementDecision(
            allowed=True,
            reason="public-build",
            metadata={"provider": "none", "capability": request.capability},
        )


def load_entitlement_provider(module_name: str | None = None) -> EntitlementProvider:
    """Load an optional provider module or return the public no-op provider.

    Extension modules expose a zero-argument ``get_provider`` function. The
    module name may be supplied directly or through
    ``MARTY_ENTITLEMENT_PROVIDER_MODULE`` in a downstream image.
    """

    configured = module_name or os.getenv("MARTY_ENTITLEMENT_PROVIDER_MODULE", "").strip()
    if not configured:
        return NoopEntitlementProvider()

    module = importlib.import_module(configured)
    factory = getattr(module, "get_provider", None)
    if not callable(factory):
        raise TypeError(f"Entitlement extension {configured!r} must expose get_provider()")
    provider = factory()
    if not callable(getattr(provider, "authorize", None)):
        raise TypeError(f"Entitlement extension {configured!r} returned an invalid provider")
    return provider
