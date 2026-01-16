"""
Persistence Layer - Digital Identity

SQLAlchemy models, repository implementations, and database management.
"""

from digital_identity.infrastructure.persistence.models import (
    Base,
    TrustProfileModel,
    CredentialTemplateModel,
    PresentationPolicyModel,
    DeploymentProfileModel,
    FlowModel,
    FlowExecutionModel,
)
from digital_identity.infrastructure.persistence.repositories import (
    TrustProfileRepository,
    CredentialTemplateRepository,
    PresentationPolicyRepository,
    DeploymentProfileRepository,
    FlowRepository,
    FlowExecutionRepository,
)
from digital_identity.infrastructure.persistence.database import (
    DigitalIdentityDatabaseConfig,
    DigitalIdentityDatabaseManager,
    get_database_manager,
    set_database_manager,
    get_db_session,
    init_database,
    close_database,
)

__all__ = [
    # Base
    "Base",
    # Models
    "TrustProfileModel",
    "CredentialTemplateModel",
    "PresentationPolicyModel",
    "DeploymentProfileModel",
    "FlowModel",
    "FlowExecutionModel",
    # Repositories
    "TrustProfileRepository",
    "CredentialTemplateRepository",
    "PresentationPolicyRepository",
    "DeploymentProfileRepository",
    "FlowRepository",
    "FlowExecutionRepository",
    # Database Management
    "DigitalIdentityDatabaseConfig",
    "DigitalIdentityDatabaseManager",
    "get_database_manager",
    "set_database_manager",
    "get_db_session",
    "init_database",
    "close_database",
]
