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
    
    Values match the spec enum (SCREAMING_SNAKE_CASE).
    """
    
    ICAO = "ICAO"          # ICAO PKD (CSCA/DSC) for ePassports/eMRTD
    AAMVA = "AAMVA"        # AAMVA IACA for mDL (ISO 18013-5)
    EUDI = "EUDI"          # EU Digital Identity Wallet ecosystem
    CUSTOM = "CUSTOM"      # Custom X.509/pinned keys
    
    def __str__(self) -> str:
        return self.value


class RevocationCheckMode(str, Enum):
    """How revocation checking should be performed. Values match the spec."""
    
    HARD_FAIL = "HARD_FAIL"      # Fail if revocation check fails
    SOFT_FAIL = "SOFT_FAIL"      # Allow if revocation check unavailable
    SKIP = "SKIP"                # Do not check revocation
    
    def __str__(self) -> str:
        return self.value


class RevocationTimingMode(str, Enum):
    """Timing mode for revocation checks on RevocationProfile. Spec: revocation-timing-modes.json."""
    
    ALWAYS = "ALWAYS"                # Check every time
    CACHED = "CACHED"                # Use cached result within TTL
    OFFLINE_GRACE = "OFFLINE_GRACE"  # Allow offline grace period
    DISABLED = "DISABLED"            # Revocation checking disabled
    
    def __str__(self) -> str:
        return self.value


class RevocationMethod(str, Enum):
    """Revocation publication method. Spec: revocation-methods.json."""
    
    OCSP = "OCSP"
    CRL = "CRL"
    STATUS_LIST_2021 = "STATUS_LIST_2021"
    BITSTRING_STATUS_LIST = "BITSTRING_STATUS_LIST"
    TOKEN_STATUS_LIST = "TOKEN_STATUS_LIST"
    
    def __str__(self) -> str:
        return self.value


class IssuanceProtocol(str, Enum):
    """Issuance protocol. Spec: issuance-protocols.json."""
    
    OID4VCI_PRE_AUTH = "OID4VCI_PRE_AUTH"
    OID4VCI_AUTH_CODE = "OID4VCI_AUTH_CODE"
    DIRECT = "DIRECT"
    
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
    ED25519 = "Ed25519"
    ED448 = "Ed448"
    BBS_BLS12381_SHA256 = "BBS_BLS12381_SHA256"
    BBS_BLS12381_SHAKE256 = "BBS_BLS12381_SHAKE256"
    
    def __str__(self) -> str:
        return self.value


class CredentialFormat(str, Enum):
    """Supported credential formats. Values match the spec enum."""
    
    MDOC = "MDOC"              # ISO 18013-5 mDoc
    SD_JWT_VC = "SD_JWT_VC"    # SD-JWT Verifiable Credential
    JWT_VC = "VC_JWT"          # JWT Verifiable Credential (spec: VC_JWT)
    LDP_VC = "JSON_LD"         # JSON-LD Verifiable Credential (spec: JSON_LD)
    ZK_MDOC = "ZK_MDOC"       # Zero-knowledge mDoc (experimental)
    
    def __str__(self) -> str:
        return self.value


class CredentialStatus(str, Enum):
    """Status of an issued credential. Values match the spec enum."""
    
    ACTIVE = "ACTIVE"          # Credential is valid and active
    SUSPENDED = "SUSPENDED"    # Temporarily suspended
    REVOKED = "REVOKED"        # Permanently revoked
    EXPIRED = "EXPIRED"        # Validity period has passed
    
    def __str__(self) -> str:
        return self.value


class RevocationReason(str, Enum):
    """RFC 5280 CRL reason codes for credential/trust-anchor revocation."""
    
    UNSPECIFIED = "unspecified"
    KEY_COMPROMISE = "key_compromise"
    CA_COMPROMISE = "ca_compromise"
    AFFILIATION_CHANGED = "affiliation_changed"
    SUPERSEDED = "superseded"
    CESSATION_OF_OPERATION = "cessation_of_operation"
    CERTIFICATE_HOLD = "certificate_hold"
    PRIVILEGE_WITHDRAWN = "privilege_withdrawn"
    
    def __str__(self) -> str:
        return self.value


class ComplianceCode(str, Enum):
    """Recognized compliance frameworks. Spec: compliance-codes.json."""
    
    ICAO_DTC = "ICAO_DTC"
    ICAO_MRZ = "ICAO_MRZ"
    AAMVA_MDL = "AAMVA_MDL"
    EUDI_PID = "EUDI_PID"
    EUDI_MDL = "EUDI_MDL"
    OB3_JWT = "OB3_JWT"
    OB3_JSONLD = "OB3_JSONLD"
    OB2_COMPATIBILITY = "OB2_COMPATIBILITY"
    SD_JWT_VC = "SD_JWT_VC"
    ENTERPRISE_VC = "ENTERPRISE_VC"
    OID4VC = "OID4VC"
    PEX = "PEX"
    CUSTOM = "CUSTOM"
    
    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class RevocationPolicy:
    """
    Revocation checking policy configuration.
    
    Uses seconds to match spec shape directly.
    """
    
    check_mode: RevocationCheckMode = RevocationCheckMode.HARD_FAIL
    cache_ttl_seconds: int = 300  # spec default: 300s


@dataclass(frozen=True)
class TimePolicy:
    """
    Time validation policy configuration.
    
    Uses seconds to match spec shape directly.
    """
    
    clock_skew_seconds: int = 300  # 5 minutes
    max_credential_age_seconds: int | None = None  # None = no limit
    require_freshness: bool = False
    freshness_window_seconds: int | None = None


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
    claim_type: str  # STRING, INTEGER, BOOLEAN, DATE, OBJECT, ARRAY (spec: "type")
    required: bool = True
    selectively_disclosable: bool = False  # spec default: false
    derived_from: str | None = None  # e.g., "age_over_21" derived from "birth_date"
    predicate_type: str | None = None  # e.g., "gte", "eq" for derived claims
    predicate_value: Any | None = None  # e.g., 21 for age_over_21
    validation_regex: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class ValidityRules:
    """
    Validity rules for a credential.
    
    Uses seconds to match spec shape directly.
    """

    ttl_seconds: int = 31536000  # 365 days
    renewable: bool = False  # spec default: false
    reissue_within_seconds: int | None = None
    not_before_offset_seconds: int = 0


@dataclass(frozen=True)
class PrivacyPosture:
    """Structured privacy posture matching spec shape.
    
    Spec: {default_disclose_all: bool, prefer_predicates: bool, sd_alg: str}
    """
    
    default_disclose_all: bool = False
    prefer_predicates: bool = False
    sd_alg: str = "sha-256"

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_disclose_all": self.default_disclose_all,
            "prefer_predicates": self.prefer_predicates,
            "sd_alg": self.sd_alg,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PrivacyPosture:
        return cls(
            default_disclose_all=data.get("default_disclose_all", False),
            prefer_predicates=data.get("prefer_predicates", False),
            sd_alg=data.get("sd_alg", "sha-256"),
        )

    @classmethod
    def from_legacy(cls, value: str) -> PrivacyPosture:
        """Convert legacy string like 'selective_disclosure' to structured config."""
        if value == "full_disclosure":
            return cls(default_disclose_all=True, prefer_predicates=False)
        return cls(default_disclose_all=False, prefer_predicates=False)

# =============================================================================

class HolderBindingMethod(str, Enum):
    """Control mechanisms that bind a presentation to its holder."""

    CREDENTIAL_KEY = "CREDENTIAL_KEY"   # Key bound to the credential
    DEVICE_KEY = "DEVICE_KEY"           # Key bound to device
    SESSION_BINDING = "SESSION_BINDING" # Session-level binding
    
    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class HolderBindingConfig:
    """Holder control, wire proof, and proof-freshness requirements."""

    required: bool = False
    binding_methods: list[HolderBindingMethod] = field(default_factory=list)
    proof_profiles: list[str] = field(default_factory=list)
    proof_freshness: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        if not self.required:
            return {"required": False}
        return {
            "required": True,
            "binding_methods": [m.value for m in self.binding_methods],
            "proof_profiles": self.proof_profiles,
            "proof_freshness": self.proof_freshness,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HolderBindingConfig:
        required = bool(data.get("required", False))
        raw_methods = [
            "SESSION_BINDING" if method == "NONCE" else method
            for method in data.get("binding_methods", [])
            if method != "BIOMETRIC"
        ]
        methods = [HolderBindingMethod(method) for method in raw_methods]
        if required and not methods:
            methods = [HolderBindingMethod.DEVICE_KEY]
        return cls(
            required=required,
            binding_methods=methods,
            proof_profiles=list(data.get("proof_profiles") or (
                ["OID4VP_VERIFIABLE_PRESENTATION"] if required else []
            )),
            proof_freshness=dict(data.get("proof_freshness") or (
                {
                    "challenge_required": True,
                    "audience_binding_required": True,
                    "replay_detection_required": True,
                } if required else {}
            )),
        )

    @classmethod
    def from_legacy(cls, value: str) -> HolderBindingConfig:
        """Convert an old single-enum value to the canonical structure."""
        if value == "NONE":
            return cls(required=False)
        method = "SESSION_BINDING" if value == "NONCE" else value
        if method == "BIOMETRIC":
            method = "DEVICE_KEY"
        return cls.from_dict({"required": True, "binding_methods": [method]})


class CredentialRankingStrategy(str, Enum):
    """Strategy for ranking credentials when multiple match a policy.
    
    Spec values: FRESHEST_FIRST, HIGHEST_TRUST_FIRST, CUSTOM.
    """
    
    FRESHEST_FIRST = "FRESHEST_FIRST"            # Prefer most recently issued
    HIGHEST_TRUST_FIRST = "HIGHEST_TRUST_FIRST"  # Prefer highest trust level issuer
    CUSTOM = "CUSTOM"                            # Use custom weighting
    
    def __str__(self) -> str:
        return self.value


class PredicateType(str, Enum):
    """
    Types of zero-knowledge predicate proofs.
    
    Defines the comparison or proof operation to be performed.
    """
    
    RANGE_PROOF = "RANGE_PROOF"          # Value is within a range (e.g., age >= 21)
    MEMBERSHIP = "MEMBERSHIP"              # Value is in a set (e.g., country in [US, CA, MX])
    EQUALITY = "EQUALITY"                  # Value equals target without revealing value
    NON_MEMBERSHIP = "NON_MEMBERSHIP"      # Value is NOT in a set
    INEQUALITY = "INEQUALITY"              # Value does not equal target
    
    def __str__(self) -> str:
        return self.value


class PredicateFallbackPolicy(str, Enum):
    """
    Fallback policy when ZK predicate proof is unavailable.
    
    Controls behavior when holder cannot produce a ZK proof.
    """
    
    REQUIRE_PREDICATE = "REQUIRE_PREDICATE"  # Strict: reject if ZK unavailable
    ACCEPT_RAW = "ACCEPT_RAW"                  # Graceful: accept raw claim as fallback
    DENY = "DENY"                              # Block: deny verification entirely
    
    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class PredicateSpecification:
    """
    Specification for a zero-knowledge predicate proof.
    
    Defines the type of proof, parameters, and acceptable ZK circuits.
    This enables structured ZK proof requests in Presentation Policies.
    
    Examples:
        # Age over 21 range proof
        PredicateSpecification(
            predicate_type=PredicateType.RANGE_PROOF,
            params={"threshold": 21, "comparison": "gte"},
            supported_circuits=["ligero_age_over_21", "bbs_range"],
        )
        
        # Country membership proof
        PredicateSpecification(
            predicate_type=PredicateType.MEMBERSHIP,
            params={"allowed_values": ["US", "CA", "MX"]},
        )
    
    Attributes:
        predicate_type: Type of predicate (range, membership, equality)
        params: Type-specific parameters (threshold, comparison, allowed_values, etc.)
        supported_circuits: List of acceptable ZK circuit identifiers
        fallback_policy: What to do if ZK proof is unavailable
    """
    
    predicate_type: PredicateType
    params: dict[str, Any] = field(default_factory=dict)
    supported_circuits: list[str] = field(default_factory=list)
    fallback_policy: PredicateFallbackPolicy = PredicateFallbackPolicy.ACCEPT_RAW
    
    def __post_init__(self) -> None:
        """Validate predicate specification."""
        self._validate_params()
        # Normalize legacy lowercase values
        if isinstance(self.predicate_type, str):
            object.__setattr__(self, 'predicate_type', PredicateType(self.predicate_type.upper()))
        if isinstance(self.fallback_policy, str):
            object.__setattr__(self, 'fallback_policy', PredicateFallbackPolicy(self.fallback_policy.upper()))
    
    def _validate_params(self) -> None:
        """Validate params based on predicate type."""
        if self.predicate_type == PredicateType.RANGE_PROOF:
            if "threshold" not in self.params and "min" not in self.params and "max" not in self.params:
                raise ValueError("Range proof requires 'threshold', 'min', or 'max' in params")
            if "comparison" in self.params:
                valid_comparisons = {"gt", "gte", "lt", "lte", "eq", "between"}
                if self.params["comparison"] not in valid_comparisons:
                    raise ValueError(f"Invalid comparison: {self.params['comparison']}")
        
        elif self.predicate_type == PredicateType.MEMBERSHIP:
            if "allowed_values" not in self.params:
                raise ValueError("Membership proof requires 'allowed_values' in params")
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "predicate_type": self.predicate_type.value,
            "params": self.params,
            "supported_circuits": self.supported_circuits,
            "fallback_policy": self.fallback_policy.value,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PredicateSpecification":
        """Create from dictionary."""
        raw_type = data["predicate_type"]
        raw_fallback = data.get("fallback_policy", "ACCEPT_RAW")
        return cls(
            predicate_type=PredicateType(raw_type.upper() if raw_type.islower() else raw_type),
            params=data.get("params", {}),
            supported_circuits=data.get("supported_circuits", []),
            fallback_policy=PredicateFallbackPolicy(
                raw_fallback.upper() if raw_fallback.islower() else raw_fallback
            ),
        )
    
    @classmethod
    def age_over(cls, age: int, circuits: list[str] | None = None) -> "PredicateSpecification":
        """Factory for age-over predicates."""
        return cls(
            predicate_type=PredicateType.RANGE_PROOF,
            params={"threshold": age, "comparison": "gte"},
            supported_circuits=circuits or [f"ligero_age_over_{age}"],
        )
    
    @classmethod
    def country_membership(cls, countries: list[str]) -> "PredicateSpecification":
        """Factory for country membership predicates."""
        return cls(
            predicate_type=PredicateType.MEMBERSHIP,
            params={"allowed_values": countries},
        )


@dataclass(frozen=True)
class RequiredClaim:
    """
    A claim required in a presentation.
    
    Defines what must be disclosed to satisfy the policy, including
    optional zero-knowledge predicate specifications.
    
    Attributes:
        claim_name: Name of the claim (e.g., "age", "country", "age_over_21")
        credential_type: Type of credential containing this claim
        accept_predicate: Whether to accept ZK predicate proofs (legacy boolean)
        required_value: If set, claim must equal this value
        predicate_spec: Structured ZK predicate specification (replaces accept_predicate)
    """
    
    claim_name: str
    credential_type: str
    accept_predicate: bool = True  # Accept predicate proof instead of raw value
    value_constraint: Any | None = None  # If set, claim must equal this value (spec: value_constraint)
    predicate_spec: PredicateSpecification | None = None  # Structured ZK specification
    
    def __post_init__(self) -> None:
        """Sync accept_predicate with predicate_spec if needed."""
        # If predicate_spec is provided, it takes precedence
        # accept_predicate is kept for backward compatibility
        pass
    
    def allows_predicate(self) -> bool:
        """Check if this claim accepts predicate proofs."""
        if self.predicate_spec is not None:
            return True
        return self.accept_predicate
    
    def get_fallback_policy(self) -> PredicateFallbackPolicy:
        """Get the fallback policy for ZK unavailability."""
        if self.predicate_spec is not None:
            return self.predicate_spec.fallback_policy
        # Default fallback for legacy accept_predicate=True
        return PredicateFallbackPolicy.ACCEPT_RAW if self.accept_predicate else PredicateFallbackPolicy.DENY
    
    def get_supported_circuits(self) -> list[str]:
        """Get list of supported ZK circuits."""
        if self.predicate_spec is not None:
            return self.predicate_spec.supported_circuits
        return []


@dataclass(frozen=True)
class FreshnessRequirements:
    """
    Freshness requirements for presentations.
    
    Uses seconds to match spec shape directly.
    """

    max_age_seconds: int | None = None
    require_not_revoked: bool = False
    revocation_grace_seconds: int | None = None
# =============================================================================

class NetworkMode(str, Enum):
    """Network connectivity mode for deployment. Values match spec network-modes.json."""
    
    ONLINE = "ONLINE"              # Always connected
    OFFLINE = "OFFLINE"            # Never connected
    HYBRID = "HYBRID"              # Sometimes connected
    
    def __str__(self) -> str:
        return self.value


class KeyAccessMode(str, Enum):
    """How signing keys are accessed. Spec values: KEY_VAULT, HSM, DEVICE_KEYSTORE."""
    
    HSM = "HSM"                          # Hardware Security Module
    KEY_VAULT = "KEY_VAULT"              # Cloud key vault (Azure, AWS, etc.)
    DEVICE_KEYSTORE = "DEVICE_KEYSTORE"  # Local device keystore
    
    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class UXConfig:
    """
    User experience configuration for a deployment.
    
    Controls display and accessibility settings.
    """
    
    language: str = "en-US"
    theme: str = "light"  # Spec: light, dark, high_contrast
    operator_mode: bool = False
    accessibility_mode: bool = False
    signage_text: dict[str, str] | None = None  # Multilingual signage: {"en": "Please present ID", "es": "..."}


@dataclass(frozen=True)
class UpdatePolicy:
    """
    Policy for updating deployment configuration.
    
    Controls how and when updates are applied.
    """
    
    auto_update: bool = True
    channel: str = "stable"  # stable, beta, pinned (spec values)
    rollout_percentage: int = 100
    pinned_version: str | None = None  # Pin to specific version
    rollout_ring: str | None = None  # Named rollout ring


# =============================================================================
# Flow Value Objects
# =============================================================================

class FlowType(str, Enum):
    """
    Type of identity flow (fixed protocol sequences).
    
    Each flow type has a predefined sequence of steps.
    Values match the spec flow-types.json enum.
    """
    
    # Issuance flows
    OID4VCI_PRE_AUTHORIZED = "oid4vci_pre_authorized"
    OID4VCI_AUTHORIZATION_CODE = "oid4vci_authorization_code"
    MDL_ISSUANCE = "mdl_issuance"
    
    # Presentation/verification flows
    OID4VP_PRESENTATION = "oid4vp_presentation"
    MDL_PRESENTATION = "mdl_presentation"
    SIOPV2 = "siopv2"
    
    # Application flows
    APPLICATION_APPROVAL_ISSUANCE = "application_approval_issuance"
    
    # Lifecycle flows
    CREDENTIAL_RENEWAL = "credential_renewal"
    CREDENTIAL_REVOCATION = "credential_revocation"
    
    # Combined flows
    COMBINED = "combined"
    
    def __str__(self) -> str:
        return self.value


# Flow category derivation (spec flow_category is read-only, derived from flow_type)
FLOW_CATEGORY: Final[dict[str, str]] = {
    "oid4vci_pre_authorized": "ISSUANCE",
    "oid4vci_authorization_code": "ISSUANCE",
    "mdl_issuance": "ISSUANCE",
    "application_approval_issuance": "ISSUANCE",
    "oid4vp_presentation": "VERIFICATION",
    "mdl_presentation": "VERIFICATION",
    "siopv2": "VERIFICATION",
    "credential_renewal": "RENEWAL",
    "credential_revocation": "REVOCATION",
    "combined": "COMBINED",
}


class FlowStatus(str, Enum):
    """
    Lifecycle status of a FlowExecution.
    
    Aligned with spec §9.9.2 state machine and flow-statuses.json.
    Terminal states: COMPLETED, FAILED, EXPIRED, CANCELLED.
    """
    
    PENDING = "PENDING"                       # Instance created; not yet started
    IN_PROGRESS = "IN_PROGRESS"               # Active execution; a step is running
    AWAITING_APPROVAL = "AWAITING_APPROVAL"   # Paused pending manual reviewer decision
    AWAITING_WALLET = "AWAITING_WALLET"       # Paused pending holder action
    AWAITING_EVIDENCE = "AWAITING_EVIDENCE"   # Paused pending supplementary evidence
    COMPLETED = "COMPLETED"                   # All steps finished successfully (terminal)
    FAILED = "FAILED"                         # A step failed with no retries (terminal)
    EXPIRED = "EXPIRED"                       # Exceeded TTL before completing (terminal)
    CANCELLED = "CANCELLED"                   # Explicitly cancelled (terminal)
    
    def __str__(self) -> str:
        return self.value


class ApprovalStrategy(str, Enum):
    """Strategy for approval decisions in flows. Values match spec approval-strategies.json."""
    
    AUTO = "AUTO"                  # Automatic approval
    MANUAL = "MANUAL"              # Manual officer review
    RULES_BASED = "RULES_BASED"    # Policy rules evaluation
    EXTERNAL = "EXTERNAL"          # External system callback
    
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
    FlowType.CREDENTIAL_RENEWAL: [
        FlowStep("validate_existing", "Validate Existing Credential"),
        FlowStep("create_offer", "Create Credential Offer"),
        FlowStep("token_exchange", "Token Exchange"),
        FlowStep("credential_request", "Credential Request"),
        FlowStep("issue_renewed_credential", "Issue Renewed Credential"),
        FlowStep("revoke_old_credential", "Revoke Old Credential"),
    ],
    FlowType.CREDENTIAL_REVOCATION: [
        FlowStep("validate_revocation_request", "Validate Revocation Request"),
        FlowStep("update_status_list", "Update Status List"),
        FlowStep("notify_holder", "Notify Holder"),
    ],
    FlowType.COMBINED: [
        FlowStep("accept_application", "Accept Application"),
        FlowStep("approval_decision", "Approval Decision", extensible=True),
        FlowStep("issue_credential", "Issue Credential"),
        FlowStep("create_request", "Create Presentation Request"),
        FlowStep("presentation_submission", "Presentation Submission"),
        FlowStep("verify_presentation", "Verify Presentation"),
    ],
    FlowType.SIOPV2: [
        FlowStep("create_request", "Create Self-Issued OP Request"),
        FlowStep("id_token_request", "Request ID Token"),
        FlowStep("id_token_response", "Receive ID Token Response"),
        FlowStep("verify_id_token", "Verify Self-Issued ID Token"),
    ],
}


# =============================================================================
# Compliance Profile & Issuer Artifact Value Objects
# =============================================================================

@dataclass(frozen=True)
class IssuerArtifactRequirements:
    """
    Issuer artifact requirements per credential format.
    
    Spec fields: requires_x509_cert, requires_did, requires_jwk,
    cert_key_usage, recommended_algorithms.
    """
    
    requires_x509_cert: bool = False
    requires_did: bool = False
    requires_jwk: bool = False
    cert_key_usage: list[str] = field(default_factory=list)
    recommended_algorithms: list[CryptoAlgorithm] = field(default_factory=list)


# Preset artifact requirements per format
ARTIFACT_REQUIREMENTS: Final[dict[CredentialFormat, IssuerArtifactRequirements]] = {
    CredentialFormat.MDOC: IssuerArtifactRequirements(
        requires_x509_cert=True,
        requires_did=False,
        recommended_algorithms=[CryptoAlgorithm.ES256],
    ),
    CredentialFormat.SD_JWT_VC: IssuerArtifactRequirements(
        requires_x509_cert=False,
        requires_did=False,
        requires_jwk=True,
        recommended_algorithms=[CryptoAlgorithm.ES256, CryptoAlgorithm.ES384],
    ),
    CredentialFormat.JWT_VC: IssuerArtifactRequirements(
        requires_x509_cert=False,
        requires_did=True,
        recommended_algorithms=[
            CryptoAlgorithm.ES256,
            CryptoAlgorithm.EDDSA,
            CryptoAlgorithm.RS256,
        ],
    ),
    CredentialFormat.LDP_VC: IssuerArtifactRequirements(
        requires_x509_cert=False,
        requires_did=True,
        recommended_algorithms=[
            CryptoAlgorithm.ES256,
            CryptoAlgorithm.EDDSA,
        ],
    ),
}


# =============================================================================
# Evidence & Claim Verification Value Objects
# =============================================================================

class EvidenceType(str, Enum):
    """Types of evidence that can be required for credential issuance."""
    
    IDENTITY_VERIFICATION = "identity_verification"
    DOCUMENT_VERIFICATION = "document_verification"
    BIOMETRIC_ENROLLMENT = "biometric_enrollment"
    CRIMINAL_HISTORY = "criminal_history"
    SECURITY_CLEARANCE = "security_clearance"
    EMPLOYMENT_VERIFICATION = "employment_verification"
    ADDRESS_VERIFICATION = "address_verification"
    AGE_VERIFICATION = "age_verification"
    PAYMENT_VERIFICATION = "payment_verification"
    CUSTOM = "custom"
    
    def __str__(self) -> str:
        return self.value


class ClaimVerificationMethod(str, Enum):
    """Methods for verifying claim values before issuance."""
    
    MANUAL_REVIEW = "manual_review"
    AUTOMATED_CHECK = "automated_check"
    THIRD_PARTY_API = "third_party_api"
    EVIDENCE_EXTRACTION = "evidence_extraction"
    USER_ATTESTATION = "user_attestation"
    BIOMETRIC_MATCH = "biometric_match"
    DOCUMENT_PARSE = "document_parse"
    
    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class EvidenceRequirement:
    """
    Evidence requirement for credential issuance.
    
    Defines what evidence must be collected and validated
    before a credential can be issued.
    """
    
    evidence_type: EvidenceType
    required: bool = True
    provider_config: dict[str, Any] = field(default_factory=dict)
    description: str | None = None
    auto_validate: bool = False


@dataclass(frozen=True)
class ClaimVerificationRule:
    """
    Claim verification rule for credential issuance.
    
    Defines how a specific claim value must be verified
    before being included in a credential.
    """
    
    claim_name: str
    verification_method: ClaimVerificationMethod
    source_evidence_type: EvidenceType | None = None
    validation_rules: dict[str, Any] = field(default_factory=dict)
    required: bool = True
    description: str | None = None


@dataclass(frozen=True)
class StatusListEntryRef:
    """
    Reference to a status list entry for credential revocation/suspension.
    
    Contains the information needed to check a credential's status
    and for the issuer to update its revocation/suspension state.
    """
    
    purpose: str  # "revocation" or "suspension"
    status_list_id: str  # Identifier for the status list
    status_list_uri: str  # URL to the StatusListCredential
    index: int  # Index within the status list (bit position)
