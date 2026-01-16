"""
Application Ports - Digital Identity

Defines the port interfaces (protocols) for the digital identity feature.
Ports are divided into:
- Inbound (driving) ports: Interfaces exposed to external callers
- Outbound (driven) ports: Interfaces required from infrastructure
"""

from digital_identity.application.ports.inbound import (
    TrustProfileServicePort,
    CredentialTemplateServicePort,
    PresentationPolicyServicePort,
    DeploymentProfileServicePort,
    FlowServicePort,
)
from digital_identity.application.ports.outbound import (
    TrustProfileRepositoryPort,
    CredentialTemplateRepositoryPort,
    PresentationPolicyRepositoryPort,
    DeploymentProfileRepositoryPort,
    FlowRepositoryPort,
    FlowExecutionRepositoryPort,
    TrustValidationPort,
    EventPublisherPort,
)
from digital_identity.application.ports.trust_profile import (
    TrustProfilePort,
    ChainValidationResult,
    RevocationCheckResult,
    RefreshResult,
)

__all__ = [
    # Inbound Ports
    "TrustProfileServicePort",
    "CredentialTemplateServicePort",
    "PresentationPolicyServicePort",
    "DeploymentProfileServicePort",
    "FlowServicePort",
    # Outbound Ports
    "TrustProfileRepositoryPort",
    "CredentialTemplateRepositoryPort",
    "PresentationPolicyRepositoryPort",
    "DeploymentProfileRepositoryPort",
    "FlowRepositoryPort",
    "FlowExecutionRepositoryPort",
    "TrustValidationPort",
    "EventPublisherPort",
    # Trust Profile Port
    "TrustProfilePort",
    "ChainValidationResult",
    "RevocationCheckResult",
    "RefreshResult",
]
