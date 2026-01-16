"""
REST API Adapters - Digital Identity

FastAPI routers for the Digital Identity API.
Uses URL path versioning: /v1/identity/
"""

from digital_identity.infrastructure.adapters.rest.routers import (
    trust_profile_router,
    credential_template_router,
    presentation_policy_router,
    deployment_profile_router,
    flow_router,
)
from digital_identity.infrastructure.adapters.rest.schemas import (
    TrustProfileCreate,
    TrustProfileUpdate,
    TrustProfileResponse,
    CredentialTemplateCreate,
    CredentialTemplateUpdate,
    CredentialTemplateResponse,
    PresentationPolicyCreate,
    PresentationPolicyUpdate,
    PresentationPolicyResponse,
    DeploymentProfileCreate,
    DeploymentProfileUpdate,
    DeploymentProfileResponse,
    FlowCreate,
    FlowUpdate,
    FlowResponse,
    FlowExecutionStart,
    FlowExecutionApproval,
    FlowExecutionResponse,
)

__all__ = [
    # Routers
    "trust_profile_router",
    "credential_template_router",
    "presentation_policy_router",
    "deployment_profile_router",
    "flow_router",
    # Trust Profile Schemas
    "TrustProfileCreate",
    "TrustProfileUpdate",
    "TrustProfileResponse",
    # Credential Template Schemas
    "CredentialTemplateCreate",
    "CredentialTemplateUpdate",
    "CredentialTemplateResponse",
    # Presentation Policy Schemas
    "PresentationPolicyCreate",
    "PresentationPolicyUpdate",
    "PresentationPolicyResponse",
    # Deployment Profile Schemas
    "DeploymentProfileCreate",
    "DeploymentProfileUpdate",
    "DeploymentProfileResponse",
    # Flow Schemas
    "FlowCreate",
    "FlowUpdate",
    "FlowResponse",
    "FlowExecutionStart",
    "FlowExecutionApproval",
    "FlowExecutionResponse",
]
