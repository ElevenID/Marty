"""
Outbound Ports (Driven Ports) for Digital Identity

These protocols define the interfaces that the application layer
requires from infrastructure adapters (repositories, external services, etc.).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from digital_identity.domain.entities import (
    TrustProfile,
    CredentialTemplate,
    PresentationPolicy,
    DeploymentProfile,
    Flow,
    FlowExecution,
    IssuedCredential,
    OrganizationCustomAnchor,
)
from digital_identity.domain.events import DomainEvent
from digital_identity.domain.value_objects import (
    TrustProfileType,
    FlowType,
    FlowStatus,
)


# =============================================================================
# Repository Ports
# =============================================================================

@runtime_checkable
class TrustProfileRepositoryPort(Protocol):
    """
    Repository port for Trust Profile persistence.
    
    Handles storage and retrieval of Trust Profile entities.
    """
    
    async def save(self, entity: TrustProfile) -> TrustProfile:
        """Save a Trust Profile (create or update)."""
        ...
    
    async def get(self, entity_id: str) -> TrustProfile | None:
        """Get a Trust Profile by ID."""
        ...
    
    async def get_by_name(self, name: str) -> TrustProfile | None:
        """Get a Trust Profile by name."""
        ...
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        profile_type: TrustProfileType | None = None,
        enabled: bool | None = None,
    ) -> list[TrustProfile]:
        """List Trust Profiles with optional filters."""
        ...
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a Trust Profile."""
        ...
    
    async def exists(self, entity_id: str) -> bool:
        """Check if a Trust Profile exists."""
        ...


@runtime_checkable
class CustomAnchorRepositoryPort(Protocol):
    """
    Repository port for Organization Custom Anchor persistence.
    
    Handles storage and retrieval of custom trust anchors (BYOK certificates).
    """
    
    async def save(self, entity: OrganizationCustomAnchor) -> OrganizationCustomAnchor:
        """Save a custom anchor (create or update)."""
        ...
    
    async def get(self, entity_id: str) -> OrganizationCustomAnchor | None:
        """Get a custom anchor by ID."""
        ...
    
    async def list_by_profile(self, profile_id: str) -> list[OrganizationCustomAnchor]:
        """List all custom anchors for a trust profile."""
        ...
    
    async def list_by_organization(self, organization_id: str) -> list[OrganizationCustomAnchor]:
        """List all custom anchors for an organization."""
        ...
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a custom anchor."""
        ...
    
    async def exists(self, entity_id: str) -> bool:
        """Check if a custom anchor exists."""
        ...


@runtime_checkable
class CredentialTemplateRepositoryPort(Protocol):
    """
    Repository port for Credential Template persistence.
    
    Handles storage and retrieval of Credential Template entities.
    """
    
    async def save(self, entity: CredentialTemplate) -> CredentialTemplate:
        """Save a Credential Template (create or update)."""
        ...
    
    async def get(self, entity_id: str) -> CredentialTemplate | None:
        """Get a Credential Template by ID."""
        ...
    
    async def get_by_type(self, credential_type: str) -> CredentialTemplate | None:
        """Get a Credential Template by credential type."""
        ...
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        format: str | None = None,
    ) -> list[CredentialTemplate]:
        """List Credential Templates with optional filters."""
        ...
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a Credential Template."""
        ...
    
    async def exists(self, entity_id: str) -> bool:
        """Check if a Credential Template exists."""
        ...


@runtime_checkable
class PresentationPolicyRepositoryPort(Protocol):
    """
    Repository port for Presentation Policy persistence.
    
    Handles storage and retrieval of Presentation Policy entities.
    """
    
    async def save(self, entity: PresentationPolicy) -> PresentationPolicy:
        """Save a Presentation Policy (create or update)."""
        ...
    
    async def get(self, entity_id: str) -> PresentationPolicy | None:
        """Get a Presentation Policy by ID."""
        ...
    
    async def get_by_name(self, name: str) -> PresentationPolicy | None:
        """Get a Presentation Policy by name."""
        ...
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        trust_profile_id: str | None = None,
    ) -> list[PresentationPolicy]:
        """List Presentation Policies with optional filters."""
        ...
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a Presentation Policy."""
        ...
    
    async def exists(self, entity_id: str) -> bool:
        """Check if a Presentation Policy exists."""
        ...


@runtime_checkable
class DeploymentProfileRepositoryPort(Protocol):
    """
    Repository port for Deployment Profile persistence.
    
    Handles storage and retrieval of Deployment Profile entities.
    """
    
    async def save(self, entity: DeploymentProfile) -> DeploymentProfile:
        """Save a Deployment Profile (create or update)."""
        ...
    
    async def get(self, entity_id: str) -> DeploymentProfile | None:
        """Get a Deployment Profile by ID."""
        ...
    
    async def get_by_site(self, site_id: str) -> DeploymentProfile | None:
        """Get a Deployment Profile by site ID."""
        ...
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        network_mode: str | None = None,
    ) -> list[DeploymentProfile]:
        """List Deployment Profiles with optional filters."""
        ...
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a Deployment Profile."""
        ...
    
    async def exists(self, entity_id: str) -> bool:
        """Check if a Deployment Profile exists."""
        ...


@runtime_checkable
class FlowRepositoryPort(Protocol):
    """
    Repository port for Flow persistence.
    
    Handles storage and retrieval of Flow entities.
    """
    
    async def save(self, entity: Flow) -> Flow:
        """Save a Flow (create or update)."""
        ...
    
    async def get(self, entity_id: str) -> Flow | None:
        """Get a Flow by ID."""
        ...
    
    async def get_by_name(self, name: str) -> Flow | None:
        """Get a Flow by name."""
        ...
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        flow_type: FlowType | None = None,
        enabled: bool | None = None,
    ) -> list[Flow]:
        """List Flows with optional filters."""
        ...
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a Flow."""
        ...
    
    async def exists(self, entity_id: str) -> bool:
        """Check if a Flow exists."""
        ...


@runtime_checkable
class FlowExecutionRepositoryPort(Protocol):
    """
    Repository port for Flow Execution persistence.
    
    Handles storage and retrieval of Flow Execution state.
    """
    
    async def save(self, entity: FlowExecution) -> FlowExecution:
        """Save a Flow Execution (create or update)."""
        ...
    
    async def get(self, entity_id: str) -> FlowExecution | None:
        """Get a Flow Execution by ID."""
        ...
    
    async def list(
        self,
        flow_id: str | None = None,
        status: FlowStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[FlowExecution]:
        """List Flow Executions with optional filters."""
        ...
    
    async def delete(self, entity_id: str) -> bool:
        """Delete a Flow Execution."""
        ...
    
    async def get_pending_approvals(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[FlowExecution]:
        """Get executions awaiting approval."""
        ...


@runtime_checkable
class IssuedCredentialRepositoryPort(Protocol):
    """
    Repository port for Issued Credential persistence.
    
    Handles storage and retrieval of issued credential metadata.
    """
    
    async def save(self, entity: IssuedCredential) -> IssuedCredential:
        """Save an Issued Credential (create or update)."""
        ...
    
    async def get(self, entity_id: str) -> IssuedCredential | None:
        """Get an Issued Credential by ID."""
        ...
    
    async def get_by_credential_id(self, credential_id: str) -> IssuedCredential | None:
        """Get an Issued Credential by its credential_id (urn:uuid:... or custom ID)."""
        ...
    
    async def list_by_flow_execution(self, flow_execution_id: str) -> list[IssuedCredential]:
        """List credentials issued by a specific flow execution."""
        ...
    
    async def list_by_subject(
        self,
        subject_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[IssuedCredential]:
        """List credentials for a specific subject/holder."""
        ...
    
    async def list_by_template(
        self,
        credential_template_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[IssuedCredential]:
        """List credentials issued from a specific template."""
        ...
    
    async def delete(self, entity_id: str) -> bool:
        """Delete an Issued Credential record."""
        ...


# =============================================================================
# External Service Ports
# =============================================================================

@runtime_checkable
class TrustValidationPort(Protocol):
    """
    Port for trust validation operations.
    
    Provides certificate chain validation and revocation checking
    using the underlying trust infrastructure.
    """
    
    async def validate_certificate_chain(
        self,
        profile_id: str,
        certificate_pem: str | None = None,
        certificate_der: bytes | None = None,
    ) -> dict[str, Any]:
        """
        Validate a certificate chain using a Trust Profile.
        
        Args:
            profile_id: ID of the Trust Profile to use
            certificate_pem: PEM-encoded certificate
            certificate_der: DER-encoded certificate
            
        Returns:
            Validation result dictionary
        """
        ...
    
    async def check_revocation(
        self,
        profile_id: str,
        certificate_pem: str | None = None,
        certificate_der: bytes | None = None,
    ) -> dict[str, Any]:
        """
        Check revocation status using a Trust Profile.
        
        Args:
            profile_id: ID of the Trust Profile to use
            certificate_pem: PEM-encoded certificate
            certificate_der: DER-encoded certificate
            
        Returns:
            Revocation check result dictionary
        """
        ...
    
    async def refresh_trust_data(self, profile_id: str) -> dict[str, Any]:
        """
        Refresh trust data for a profile.
        
        Args:
            profile_id: ID of the Trust Profile to refresh
            
        Returns:
            Refresh result dictionary
        """
        ...


@runtime_checkable
class EventPublisherPort(Protocol):
    """
    Port for publishing domain events.
    
    Provides event publishing for loose coupling between components.
    """
    
    async def publish(self, event: DomainEvent) -> None:
        """
        Publish a domain event.
        
        Args:
            event: The domain event to publish
        """
        ...
    
    async def publish_many(self, events: list[DomainEvent]) -> None:
        """
        Publish multiple domain events.
        
        Args:
            events: List of domain events to publish
        """
        ...


@runtime_checkable
class StepHandlerRegistryPort(Protocol):
    """
    Port for flow step handler registration.
    
    Allows registration of custom step handlers and hooks.
    """
    
    def register_handler(
        self,
        step_name: str,
        handler: Any,  # Callable
    ) -> None:
        """Register a custom handler for a step."""
        ...
    
    def get_handler(self, step_name: str) -> Any | None:
        """Get the handler for a step."""
        ...
    
    def register_pre_hook(
        self,
        step_name: str,
        hook: Any,  # Callable
    ) -> None:
        """Register a pre-execution hook for a step."""
        ...
    
    def register_post_hook(
        self,
        step_name: str,
        hook: Any,  # Callable
    ) -> None:
        """Register a post-execution hook for a step."""
        ...
    
    def get_pre_hooks(self, step_name: str) -> list[Any]:
        """Get pre-execution hooks for a step."""
        ...
    
    def get_post_hooks(self, step_name: str) -> list[Any]:
        """Get post-execution hooks for a step."""
        ...


@runtime_checkable
class ApprovalStrategyPort(Protocol):
    """
    Port for approval strategy implementations.
    
    Different strategies can be plugged in for flow approval decisions.
    """
    
    async def evaluate(
        self,
        execution: FlowExecution,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Evaluate an approval decision.
        
        Args:
            execution: The flow execution awaiting approval
            context: Additional context for the decision
            
        Returns:
            Decision result with 'approved', 'pending', or 'rejected'
        """
        ...


@runtime_checkable
class AuditEventRepositoryPort(Protocol):
    """
    Repository port for Audit Event persistence.
    
    Handles storage and retrieval of immutable audit events.
    """
    
    async def save(self, entity: Any) -> Any:  # AuditEvent type
        """Save an audit event (create only)."""
        ...
    
    async def get(self, entity_id: str) -> Any | None:  # AuditEvent type
        """Get an audit event by ID."""
        ...
    
    async def find_by_entity(
        self,
        entity_type: str,
        entity_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Any]:  # list[AuditEvent]
        """Find all audit events for a specific entity."""
        ...
    
    async def find_by_correlation_id(
        self,
        correlation_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Any]:  # list[AuditEvent]
        """Find all audit events with a specific correlation ID."""
        ...
    
    async def list_by_time_range(
        self,
        start_time: Any,  # datetime
        end_time: Any,  # datetime
        event_type: str | None = None,
        entity_type: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Any]:  # list[AuditEvent]
        """List audit events within a time range with optional filters."""
        ...
