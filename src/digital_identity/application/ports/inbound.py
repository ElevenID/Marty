"""
Inbound Ports (Driving Ports) for Digital Identity

These protocols define the interfaces that the application layer
exposes to inbound adapters (REST controllers, gRPC handlers, CLI, etc.).
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
)
from digital_identity.domain.value_objects import (
    TrustProfileType,
    FlowType,
    FlowStatus,
    ApprovalStrategy,
)


@runtime_checkable
class TrustProfileServicePort(Protocol):
    """
    Service port for Trust Profile management.
    
    Handles CRUD operations and trust validation for Trust Profiles.
    """
    
    async def create(
        self,
        name: str,
        profile_type: TrustProfileType,
        description: str | None = None,
        trust_sources: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> TrustProfile:
        """Create a new Trust Profile."""
        ...
    
    async def get(self, profile_id: str) -> TrustProfile | None:
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
    
    async def update(
        self,
        profile_id: str,
        **updates: Any,
    ) -> TrustProfile | None:
        """Update a Trust Profile."""
        ...
    
    async def delete(self, profile_id: str) -> bool:
        """Delete a Trust Profile."""
        ...
    
    async def add_trust_source(
        self,
        profile_id: str,
        source_type: str,
        source_uri: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> TrustProfile | None:
        """Add a trust source to a profile."""
        ...
    
    async def refresh_trust_data(self, profile_id: str) -> dict[str, Any]:
        """Refresh trust data for a profile."""
        ...


@runtime_checkable
class CredentialTemplateServicePort(Protocol):
    """
    Service port for Credential Template management.
    
    Handles CRUD operations for Credential Templates.
    """
    
    async def create(
        self,
        name: str,
        credential_type: str,
        description: str | None = None,
        claims: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> CredentialTemplate:
        """Create a new Credential Template."""
        ...
    
    async def get(self, template_id: str) -> CredentialTemplate | None:
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
    
    async def update(
        self,
        template_id: str,
        **updates: Any,
    ) -> CredentialTemplate | None:
        """Update a Credential Template."""
        ...
    
    async def delete(self, template_id: str) -> bool:
        """Delete a Credential Template."""
        ...
    
    async def add_claim(
        self,
        template_id: str,
        name: str,
        display_name: str,
        data_type: str,
        **kwargs: Any,
    ) -> CredentialTemplate | None:
        """Add a claim to a template."""
        ...


@runtime_checkable
class PresentationPolicyServicePort(Protocol):
    """
    Service port for Presentation Policy management.
    
    Handles CRUD operations for Presentation Policies.
    """
    
    async def create(
        self,
        name: str,
        purpose: str,
        description: str | None = None,
        required_claims: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> PresentationPolicy:
        """Create a new Presentation Policy."""
        ...
    
    async def get(self, policy_id: str) -> PresentationPolicy | None:
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
    
    async def update(
        self,
        policy_id: str,
        **updates: Any,
    ) -> PresentationPolicy | None:
        """Update a Presentation Policy."""
        ...
    
    async def delete(self, policy_id: str) -> bool:
        """Delete a Presentation Policy."""
        ...
    
    async def add_required_claim(
        self,
        policy_id: str,
        claim_name: str,
        credential_type: str,
        **kwargs: Any,
    ) -> PresentationPolicy | None:
        """Add a required claim to a policy."""
        ...


@runtime_checkable
class DeploymentProfileServicePort(Protocol):
    """
    Service port for Deployment Profile management.
    
    Handles CRUD operations for Deployment Profiles.
    """
    
    async def create(
        self,
        name: str,
        site_id: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> DeploymentProfile:
        """Create a new Deployment Profile."""
        ...
    
    async def get(self, profile_id: str) -> DeploymentProfile | None:
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
    
    async def update(
        self,
        profile_id: str,
        **updates: Any,
    ) -> DeploymentProfile | None:
        """Update a Deployment Profile."""
        ...
    
    async def delete(self, profile_id: str) -> bool:
        """Delete a Deployment Profile."""
        ...
    
    async def enable_flow(
        self,
        profile_id: str,
        flow_id: str,
    ) -> DeploymentProfile | None:
        """Enable a flow for a deployment."""
        ...
    
    async def disable_flow(
        self,
        profile_id: str,
        flow_id: str,
    ) -> DeploymentProfile | None:
        """Disable a flow for a deployment."""
        ...


@runtime_checkable
class FlowServicePort(Protocol):
    """
    Service port for Flow management and execution.
    
    Handles CRUD operations for Flows and orchestrates flow execution.
    """
    
    # Flow CRUD
    async def create(
        self,
        name: str,
        flow_type: FlowType,
        description: str | None = None,
        trust_profile_id: str | None = None,
        credential_template_id: str | None = None,
        presentation_policy_id: str | None = None,
        approval_strategy: ApprovalStrategy = ApprovalStrategy.AUTO,
        **kwargs: Any,
    ) -> Flow:
        """Create a new Flow."""
        ...
    
    async def get(self, flow_id: str) -> Flow | None:
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
    
    async def update(
        self,
        flow_id: str,
        **updates: Any,
    ) -> Flow | None:
        """Update a Flow."""
        ...
    
    async def delete(self, flow_id: str) -> bool:
        """Delete a Flow."""
        ...
    
    # Flow Execution
    async def start_execution(
        self,
        flow_id: str,
        context_data: dict[str, Any] | None = None,
    ) -> FlowExecution:
        """Start a new flow execution."""
        ...
    
    async def get_execution(self, execution_id: str) -> FlowExecution | None:
        """Get a flow execution by ID."""
        ...
    
    async def list_executions(
        self,
        flow_id: str | None = None,
        status: FlowStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[FlowExecution]:
        """List flow executions with optional filters."""
        ...
    
    async def approve_execution(
        self,
        execution_id: str,
        approved_by: str | None = None,
        reason: str | None = None,
    ) -> FlowExecution | None:
        """Approve a pending execution."""
        ...
    
    async def reject_execution(
        self,
        execution_id: str,
        rejected_by: str | None = None,
        reason: str | None = None,
    ) -> FlowExecution | None:
        """Reject a pending execution."""
        ...
    
    async def cancel_execution(
        self,
        execution_id: str,
        cancelled_by: str | None = None,
        reason: str | None = None,
    ) -> FlowExecution | None:
        """Cancel an execution."""
        ...
    
    # Hook management
    async def add_hook(
        self,
        flow_id: str,
        step_name: str,
        hook_type: str,  # "pre" or "post"
        hook_config: dict[str, Any],
    ) -> Flow | None:
        """Add a hook to a flow step."""
        ...
    
    async def remove_hook(
        self,
        flow_id: str,
        step_name: str,
        hook_type: str,
        hook_index: int,
    ) -> Flow | None:
        """Remove a hook from a flow step."""
        ...
