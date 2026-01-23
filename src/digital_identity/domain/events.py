"""
Domain Events for Digital Identity

Events emitted by domain entities to signal important state changes.
These follow the domain event pattern for loose coupling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from digital_identity.domain.value_objects import FlowType, FlowStatus


@dataclass
class DomainEvent:
    """
    Base class for domain events.
    
    All domain events inherit from this class and include
    common metadata like event ID and timestamp.
    """
    
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def event_type(self) -> str:
        """Return the event type name."""
        return self.__class__.__name__


# =============================================================================
# Trust Profile Events
# =============================================================================

@dataclass
class TrustProfileCreatedEvent(DomainEvent):
    """Emitted when a new Trust Profile is created."""
    
    trust_profile_id: str = ""
    name: str = ""
    profile_type: str = ""


@dataclass
class TrustProfileUpdatedEvent(DomainEvent):
    """Emitted when a Trust Profile is updated."""
    
    trust_profile_id: str = ""
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrustProfileDeletedEvent(DomainEvent):
    """Emitted when a Trust Profile is deleted."""
    
    trust_profile_id: str = ""


# =============================================================================
# Credential Template Events
# =============================================================================

@dataclass
class CredentialTemplateCreatedEvent(DomainEvent):
    """Emitted when a new Credential Template is created."""
    
    template_id: str = ""
    name: str = ""
    credential_type: str = ""


@dataclass
class CredentialTemplateUpdatedEvent(DomainEvent):
    """Emitted when a Credential Template is updated."""
    
    template_id: str = ""
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass
class CredentialTemplateDeletedEvent(DomainEvent):
    """Emitted when a Credential Template is deleted."""
    
    template_id: str = ""


# =============================================================================
# Presentation Policy Events
# =============================================================================

@dataclass
class PresentationPolicyCreatedEvent(DomainEvent):
    """Emitted when a new Presentation Policy is created."""
    
    policy_id: str = ""
    name: str = ""
    purpose: str = ""


@dataclass
class PresentationPolicyUpdatedEvent(DomainEvent):
    """Emitted when a Presentation Policy is updated."""
    
    policy_id: str = ""
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass
class PresentationPolicyDeletedEvent(DomainEvent):
    """Emitted when a Presentation Policy is deleted."""
    
    policy_id: str = ""


# =============================================================================
# Deployment Profile Events
# =============================================================================

@dataclass
class DeploymentProfileCreatedEvent(DomainEvent):
    """Emitted when a new Deployment Profile is created."""
    
    profile_id: str = ""
    name: str = ""
    site_id: str | None = None


@dataclass
class DeploymentProfileUpdatedEvent(DomainEvent):
    """Emitted when a Deployment Profile is updated."""
    
    profile_id: str = ""
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeploymentProfileDeletedEvent(DomainEvent):
    """Emitted when a Deployment Profile is deleted."""
    
    profile_id: str = ""


# =============================================================================
# Flow Events
# =============================================================================

@dataclass
class FlowCreatedEvent(DomainEvent):
    """Emitted when a new Flow is created."""
    
    flow_id: str = ""
    name: str = ""
    flow_type: FlowType = FlowType.APPLICATION_APPROVAL_ISSUANCE


@dataclass
class FlowUpdatedEvent(DomainEvent):
    """Emitted when a Flow is updated."""
    
    flow_id: str = ""
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowDeletedEvent(DomainEvent):
    """Emitted when a Flow is deleted."""
    
    flow_id: str = ""


# =============================================================================
# Flow Execution Events
# =============================================================================

@dataclass
class FlowStartedEvent(DomainEvent):
    """Emitted when a Flow execution starts."""
    
    execution_id: str = ""
    flow_id: str = ""
    flow_type: FlowType = FlowType.APPLICATION_APPROVAL_ISSUANCE
    context_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowStepCompletedEvent(DomainEvent):
    """Emitted when a Flow step completes."""
    
    execution_id: str = ""
    flow_id: str = ""
    step_name: str = ""
    step_index: int = 0
    result: Any = None


@dataclass
class FlowAwaitingApprovalEvent(DomainEvent):
    """Emitted when a Flow requires approval."""
    
    execution_id: str = ""
    flow_id: str = ""
    step_name: str = ""
    context_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowApprovedEvent(DomainEvent):
    """Emitted when a Flow is approved."""
    
    execution_id: str = ""
    flow_id: str = ""
    approved_by: str | None = None
    reason: str | None = None


@dataclass
class FlowRejectedEvent(DomainEvent):
    """Emitted when a Flow is rejected."""
    
    execution_id: str = ""
    flow_id: str = ""
    rejected_by: str | None = None
    reason: str | None = None


@dataclass
class FlowCompletedEvent(DomainEvent):
    """Emitted when a Flow execution completes successfully."""
    
    execution_id: str = ""
    flow_id: str = ""
    flow_type: FlowType = FlowType.APPLICATION_APPROVAL_ISSUANCE
    result: dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowFailedEvent(DomainEvent):
    """Emitted when a Flow execution fails."""
    
    execution_id: str = ""
    flow_id: str = ""
    flow_type: FlowType = FlowType.APPLICATION_APPROVAL_ISSUANCE
    error: str = ""
    step_name: str | None = None


@dataclass
class FlowCancelledEvent(DomainEvent):
    """Emitted when a Flow execution is cancelled."""
    
    execution_id: str = ""
    flow_id: str = ""
    cancelled_by: str | None = None
    reason: str | None = None


# =============================================================================
# Credential Events
# =============================================================================

@dataclass
class CredentialIssuedEvent(DomainEvent):
    """Emitted when a credential is issued via a Flow."""
    
    execution_id: str = ""
    flow_id: str = ""
    credential_id: str = ""
    credential_type: str = ""
    holder_id: str = ""
    issuer_id: str = ""


@dataclass
class CredentialRevokedEvent(DomainEvent):
    """Emitted when a credential is revoked."""
    
    credential_id: str = ""
    reason: str | None = None
    revoked_by: str | None = None


# =============================================================================
# Presentation Events
# =============================================================================

@dataclass
class PresentationRequestedEvent(DomainEvent):
    """Emitted when a presentation is requested."""
    
    execution_id: str = ""
    flow_id: str = ""
    request_id: str = ""
    policy_id: str = ""
    verifier_id: str = ""


@dataclass
class PresentationVerifiedEvent(DomainEvent):
    """Emitted when a presentation is verified."""
    
    execution_id: str = ""
    flow_id: str = ""
    presentation_id: str = ""
    holder_id: str = ""
    verifier_id: str = ""
    verified: bool = True
    claims_disclosed: list[str] = field(default_factory=list)


@dataclass
class PresentationRejectedEvent(DomainEvent):
    """Emitted when a presentation is rejected."""
    
    execution_id: str = ""
    flow_id: str = ""
    presentation_id: str = ""
    reason: str = ""


# =============================================================================
# Aliases for backward compatibility
# =============================================================================

# Trust Profile aliases (without "Event" suffix)
TrustProfileCreated = TrustProfileCreatedEvent
TrustProfileUpdated = TrustProfileUpdatedEvent
TrustProfileDeleted = TrustProfileDeletedEvent

# Credential Template aliases
CredentialTemplateCreated = CredentialTemplateCreatedEvent
CredentialTemplateUpdated = CredentialTemplateUpdatedEvent
CredentialTemplateDeleted = CredentialTemplateDeletedEvent

# Presentation Policy aliases
PresentationPolicyCreated = PresentationPolicyCreatedEvent
PresentationPolicyUpdated = PresentationPolicyUpdatedEvent
PresentationPolicyDeleted = PresentationPolicyDeletedEvent

# Deployment Profile aliases
DeploymentProfileCreated = DeploymentProfileCreatedEvent
DeploymentProfileUpdated = DeploymentProfileUpdatedEvent
DeploymentProfileDeleted = DeploymentProfileDeletedEvent

# Flow aliases
FlowCreated = FlowCreatedEvent
FlowUpdated = FlowUpdatedEvent
FlowDeleted = FlowDeletedEvent

# Flow Execution aliases (map to Flow event names)
FlowExecutionStarted = FlowStartedEvent
FlowExecutionStepCompleted = FlowStepCompletedEvent
FlowExecutionAwaitingApproval = FlowAwaitingApprovalEvent
FlowExecutionCompleted = FlowCompletedEvent
FlowExecutionFailed = FlowFailedEvent
