"""
Value Objects for Digital Identity Domain

Immutable value objects representing concepts in the digital identity domain.
These encapsulate domain concepts without identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Any, Final


# =============================================================================
# Trust Profile Value Objects
# =============================================================================

class TrustProfileType(str, Enum):
    """
    Type of trust profile, determining the trust source and validation rules.
    
    Aligns with UI TrustProfileType enum for consistency.
    """
    
    ICAO = "icao"          # ICAO PKD (CSCA/DSC) for ePassports/eMRTD
    AAMVA = "aamva"        # AAMVA IACA for mDL (ISO 18013-5)
    EUDI = "eudi"          # EU Digital Identity Wallet ecosystem
    CUSTOM = "custom"      # Custom X.509/pinned keys
    
    def __str__(self) -> str:
        return self.value


class RevocationCheckMode(str, Enum):
    """How revocation checking should be performed."""
    
    HARD_FAIL = "hard_fail"      # Fail if revocation check fails
    SOFT_FAIL = "soft_fail"      # Allow if revocation check unavailable
    SKIP = "skip"                # Do not check revocation
    
    def __str__(self) -> str:
        return self.value


class CryptoAlgorithm(str, Enum):
    """Supported cryptographic algorithms."""
    
    ES256 = "ES256"
    ES384 = "ES384"
    ES512 = "ES512"
    RS256 = "RS256"
    RS384 = "RS384"
    RS512 = "RS512"
    PS256 = "PS256"
    PS384 = "PS384"
    PS512 = "PS512"
    EDDSA = "EdDSA"
    
    def __str__(self) -> str:
        return self.value


class CredentialFormat(str, Enum):
    """Supported credential formats."""
    
    MDOC = "mdoc"              # ISO 18013-5 mDoc
    SD_JWT_VC = "sd_jwt_vc"    # SD-JWT Verifiable Credential
    JWT_VC = "jwt_vc"          # JWT Verifiable Credential
    LDP_VC = "ldp_vc"          # JSON-LD Verifiable Credential
    
    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class RevocationPolicy:
    """
    Revocation checking policy configuration.
    
    Immutable value object defining how revocation should be handled.
    """
    
    mode: RevocationCheckMode = RevocationCheckMode.HARD_FAIL
    check_ocsp: bool = True
    check_crl: bool = True
    check_status_list: bool = True
    offline_grace_period: timedelta = field(default_factory=lambda: timedelta(hours=24))
    cache_ttl: timedelta = field(default_factory=lambda: timedelta(hours=1))


@dataclass(frozen=True)
class TimePolicy:
    """
    Time validation policy configuration.
    
    Controls clock skew tolerance and freshness requirements.
    """
    
    clock_skew_tolerance: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    max_credential_age: timedelta | None = None  # None = no limit
    require_not_before: bool = True
    require_not_after: bool = True


# =============================================================================
# Credential Template Value Objects
# =============================================================================

@dataclass(frozen=True)
class ClaimDefinition:
    """
    Definition of a claim in a credential template.
    
    Defines the structure and constraints for a single claim.
    """
    
    name: str
    display_name: str
    data_type: str  # string, number, boolean, date, object, array
    required: bool = True
    selectively_disclosable: bool = True
    derived_from: str | None = None  # e.g., "age_over_21" derived from "birth_date"
    predicate_type: str | None = None  # e.g., "gte", "eq" for derived claims
    predicate_value: Any | None = None  # e.g., 21 for age_over_21
    validation_regex: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class ValidityRules:
    """
    Validity rules for a credential.
    
    Defines TTL, reissue requirements, and expiration behavior.
    """
    
    default_ttl: timedelta = field(default_factory=lambda: timedelta(days=365))
    max_ttl: timedelta | None = None
    min_ttl: timedelta = field(default_factory=lambda: timedelta(hours=1))
    allow_reissue: bool = True
    reissue_before_expiry: timedelta = field(default_factory=lambda: timedelta(days=30))


# =============================================================================
# Presentation Policy Value Objects
# =============================================================================

class HolderBindingMethod(str, Enum):
    """Methods for binding a presentation to a holder."""
    
    DEVICE_KEY = "device_key"      # Key bound to device
    SESSION_NONCE = "session_nonce"  # Nonce/challenge based
    BIOMETRIC = "biometric"        # Biometric verification
    NONE = "none"                  # No holder binding
    
    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class RequiredClaim:
    """
    A claim required in a presentation.
    
    Defines what must be disclosed to satisfy the policy.
    """
    
    claim_name: str
    credential_type: str
    accept_predicate: bool = True  # Accept predicate proof instead of raw value
    required_value: Any | None = None  # If set, claim must equal this value


@dataclass(frozen=True)
class FreshnessRequirements:
    """
    Freshness requirements for presentations.
    
    Controls how recent credentials and proofs must be.
    """
    
    max_credential_age: timedelta | None = None  # Max age of credential
    max_proof_age: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    require_live_revocation_check: bool = True


# =============================================================================
# Deployment Profile Value Objects
# =============================================================================

class NetworkMode(str, Enum):
    """Network connectivity mode for deployment."""
    
    ONLINE = "online"              # Always connected
    OFFLINE = "offline"            # Never connected
    HYBRID = "hybrid"              # Sometimes connected
    
    def __str__(self) -> str:
        return self.value


class KeyAccessMode(str, Enum):
    """How signing keys are accessed."""
    
    HSM = "hsm"                    # Hardware Security Module
    KEY_VAULT = "key_vault"        # Cloud key vault (Azure, AWS, etc.)
    SIGNING_AGENT = "signing_agent"  # Remote signing agent
    DEVICE_KEYSTORE = "device_keystore"  # Local device keystore
    BYOK = "byok"                  # Bring Your Own Key
    
    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class UXConfig:
    """
    User experience configuration for a deployment.
    
    Controls display and accessibility settings.
    """
    
    language: str = "en"
    theme: str = "default"
    show_operator_mode: bool = False
    accessibility_enabled: bool = True
    custom_branding: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UpdatePolicy:
    """
    Policy for updating deployment configuration.
    
    Controls how and when updates are applied.
    """
    
    auto_update: bool = True
    update_channel: str = "stable"  # stable, beta, canary
    rollout_percentage: int = 100
    version_pinned: str | None = None  # Pin to specific version


# =============================================================================
# Flow Value Objects
# =============================================================================

class FlowType(str, Enum):
    """
    Type of identity flow (fixed protocol sequences).
    
    Each flow type has a predefined sequence of steps.
    """
    
    # Issuance flows
    OID4VCI_PRE_AUTHORIZED = "oid4vci_pre_authorized"
    OID4VCI_AUTHORIZATION_CODE = "oid4vci_authorization_code"
    MDL_ISSUANCE = "mdl_issuance"
    
    # Presentation/verification flows
    OID4VP_PRESENTATION = "oid4vp_presentation"
    MDL_PRESENTATION = "mdl_presentation"
    
    # Application flows
    APPLICATION_APPROVAL_ISSUANCE = "application_approval_issuance"
    
    def __str__(self) -> str:
        return self.value


class FlowStatus(str, Enum):
    """Status of a flow execution."""
    
    CREATED = "created"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    
    def __str__(self) -> str:
        return self.value


class ApprovalStrategy(str, Enum):
    """Strategy for approval decisions in flows."""
    
    AUTO = "auto"              # Automatic approval
    MANUAL = "manual"          # Manual officer review
    RULES_BASED = "rules_based"  # Policy rules evaluation
    EXTERNAL = "external"      # External system callback
    
    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class FlowStep:
    """
    A step in a flow sequence.
    
    Defines a single step with its properties.
    """
    
    name: str
    display_name: str
    required: bool = True
    extensible: bool = False  # Can be customized via hooks
    timeout: timedelta = field(default_factory=lambda: timedelta(minutes=5))


# Flow step definitions per flow type (fixed sequences)
FLOW_STEPS: Final[dict[FlowType, list[FlowStep]]] = {
    FlowType.OID4VCI_PRE_AUTHORIZED: [
        FlowStep("create_offer", "Create Credential Offer"),
        FlowStep("token_exchange", "Token Exchange"),
        FlowStep("credential_request", "Credential Request"),
        FlowStep("issue_credential", "Issue Credential"),
    ],
    FlowType.OID4VCI_AUTHORIZATION_CODE: [
        FlowStep("create_offer", "Create Credential Offer"),
        FlowStep("authorization", "Authorization"),
        FlowStep("token_exchange", "Token Exchange"),
        FlowStep("credential_request", "Credential Request"),
        FlowStep("issue_credential", "Issue Credential"),
    ],
    FlowType.OID4VP_PRESENTATION: [
        FlowStep("create_request", "Create Presentation Request"),
        FlowStep("wallet_selection", "Wallet Selection"),
        FlowStep("presentation_submission", "Presentation Submission"),
        FlowStep("verify_presentation", "Verify Presentation"),
    ],
    FlowType.MDL_ISSUANCE: [
        FlowStep("application_submit", "Submit Application"),
        FlowStep("validate_evidence", "Validate Evidence"),
        FlowStep("approval_decision", "Approval Decision", extensible=True),
        FlowStep("issue_mdl", "Issue mDL"),
        FlowStep("deliver_credential", "Deliver Credential", extensible=True),
    ],
    FlowType.MDL_PRESENTATION: [
        FlowStep("device_engagement", "Device Engagement"),
        FlowStep("session_establishment", "Session Establishment"),
        FlowStep("request_items", "Request Items"),
        FlowStep("response_items", "Response Items"),
        FlowStep("session_termination", "Session Termination"),
    ],
    FlowType.APPLICATION_APPROVAL_ISSUANCE: [
        FlowStep("accept_application", "Accept Application"),
        FlowStep("validate_evidence", "Validate Evidence"),
        FlowStep("approval_decision", "Approval Decision", extensible=True),
        FlowStep("issue_credential", "Issue Credential"),
        FlowStep("deliver_credential", "Deliver Credential", extensible=True),
    ],
}
