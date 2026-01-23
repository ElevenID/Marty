"""
Digital Identity API Module

FastAPI routers and schemas for digital identity operations.
"""

from digital_identity.api.routers import (
    application_template_router,
    compliance_profile_router,
)
from digital_identity.api.schemas import (
    ApplicationTemplateCreate,
    ApplicationTemplateListResponse,
    ApplicationTemplateResponse,
    ApplicationTemplateUpdate,
    ArtifactValidationRequest,
    ArtifactValidationResponse,
    ComplianceProfileCreate,
    ComplianceProfileListResponse,
    ComplianceProfileResponse,
    ComplianceProfileUpdate,
    EvidenceRequirementSchema,
    ClaimVerificationRuleSchema,
)

__all__ = [
    # Routers
    "application_template_router",
    "compliance_profile_router",
    # Schemas
    "ApplicationTemplateCreate",
    "ApplicationTemplateListResponse",
    "ApplicationTemplateResponse",
    "ApplicationTemplateUpdate",
    "ArtifactValidationRequest",
    "ArtifactValidationResponse",
    "ComplianceProfileCreate",
    "ComplianceProfileListResponse",
    "ComplianceProfileResponse",
    "ComplianceProfileUpdate",
    "EvidenceRequirementSchema",
    "ClaimVerificationRuleSchema",
]
