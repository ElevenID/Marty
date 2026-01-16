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

__all__ = [
    "trust_profile_router",
    "credential_template_router",
    "presentation_policy_router",
    "deployment_profile_router",
    "flow_router",
]
