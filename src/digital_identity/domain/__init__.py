"""
Domain Layer - Digital Identity

Contains domain entities, value objects, and events.
"""

from digital_identity.domain.entities import (
    TrustProfile,
    CredentialTemplate,
    PresentationPolicy,
    DeploymentProfile,
    Flow,
)
from digital_identity.domain.value_objects import (
    TrustProfileType,
    FlowType,
    FlowStatus,
    NetworkMode,
    ApprovalStrategy,
)
from digital_identity.domain.events import (
    FlowStartedEvent,
    FlowCompletedEvent,
    FlowFailedEvent,
    CredentialIssuedEvent,
    PresentationVerifiedEvent,
)

__all__ = [
    # Entities
    "TrustProfile",
    "CredentialTemplate",
    "PresentationPolicy",
    "DeploymentProfile",
    "Flow",
    # Value Objects
    "TrustProfileType",
    "FlowType",
    "FlowStatus",
    "NetworkMode",
    "ApprovalStrategy",
    # Events
    "FlowStartedEvent",
    "FlowCompletedEvent",
    "FlowFailedEvent",
    "CredentialIssuedEvent",
    "PresentationVerifiedEvent",
]
