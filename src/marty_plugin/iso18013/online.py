"""ISO 18013-7 orchestration models without a Python protocol fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from marty_plugin.native_backends import NativeOperationError


class PresentationState(Enum):
    INITIATED = "initiated"
    POLICY_DISPLAYED = "policy_displayed"
    CONSENT_PENDING = "consent_pending"
    CONSENT_GRANTED = "consent_granted"
    CONSENT_DENIED = "consent_denied"
    PRESENTATION_SENT = "presentation_sent"
    VERIFIED = "verified"
    COMPLETED = "completed"
    ERROR = "error"


class ConsentLevel(Enum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    FULL = "full"


@dataclass(frozen=True)
class PresentationDefinition:
    id: str
    name: str
    purpose: str
    input_descriptors: list[dict[str, Any]]
    format: dict[str, Any] = field(default_factory=dict)
    submission_requirements: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ConsentRequest:
    session_id: str
    relying_party: str
    purpose: str
    requested_data: dict[str, list[str]]
    policy_url: str | None = None
    retention_period: str | None = None
    consent_level_options: list[ConsentLevel] = field(
        default_factory=lambda: [ConsentLevel.STANDARD]
    )


@dataclass(frozen=True)
class ConsentResponse:
    session_id: str
    granted: bool
    consent_level: ConsentLevel
    approved_data: dict[str, list[str]]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class _NativeOnlineOnly:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise NativeOperationError(
            "The Python ISO 18013-7 protocol implementation was removed; "
            "use the native HTTPS transport and credential verification service"
        )


ISO18013_7RelyingParty = _NativeOnlineOnly
ISO18013_7Holder = _NativeOnlineOnly


async def simulate_online_mdl_transaction() -> dict[str, Any]:
    raise NativeOperationError("Python ISO 18013-7 simulation was removed")


__all__ = [
    "ConsentLevel",
    "ConsentRequest",
    "ConsentResponse",
    "ISO18013_7Holder",
    "ISO18013_7RelyingParty",
    "PresentationDefinition",
    "PresentationState",
    "simulate_online_mdl_transaction",
]
