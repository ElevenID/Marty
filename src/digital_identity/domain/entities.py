"""
Domain Entities for Digital Identity

Core domain entities representing the five identity primitives:
- Trust Profile: Who is trusted and how crypto validation occurs
- Credential Template: What is issued (schema + semantics)
- Presentation Policy: What must be shown (minimum disclosure)
- Deployment Profile: Where it runs (device/site behavior)
- Flow: How identity moves (apply → issue → verify)

These are aggregate roots that encapsulate domain logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from digital_identity.domain.value_objects import (
    TrustProfileType,
    RevocationPolicy,
    TimePolicy,
    CryptoAlgorithm,
    CredentialFormat,
    ClaimDefinition,
    ValidityRules,
    RequiredClaim,
    FreshnessRequirements,
    HolderBindingMethod,
    NetworkMode,
    KeyAccessMode,
    UXConfig,
    UpdatePolicy,
    FlowType,
    FlowStatus,
    ApprovalStrategy,
    FLOW_STEPS,
)


# =============================================================================
# Base Entity
# =============================================================================

@dataclass
class Entity:
    """
    Base class for domain entities.
    
    Provides common identity and timestamp fields.
    """
    
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1
    
    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1


# =============================================================================
# Trust Profile
# =============================================================================

@dataclass
class TrustProfile(Entity):
    """
    Trust Profile entity - defines who is trusted and how validation occurs.
    
    A Trust Profile encapsulates:
    - Trust sources (ICAO PKD, AAMVA VICAL, EU Trusted Lists, pinned keys)
    - Accepted cryptographic algorithms and key usages
    - Revocation policy (OCSP, CRL, status lists, offline grace)
    - Time and freshness rules
    - Supported credential formats
    
    This is an abstraction layer that hides the complexity of multiple
    trust models behind a unified interface.
    
    Business Context (v2):
    - Multi-organization support via organization_id scoping
    - Business-friendly display names abstract technical complexity
    - Use case tags map business intent to technical configuration
    - Compliance status for dashboard indicators
    - Auto-generation flag distinguishes wizard-created from manual profiles
    
    Attributes:
        name: Technical identifier (e.g., "Passports-ICAO-US")
        display_name: Business-friendly name (e.g., "Travel Documents")
        description: Optional description
        profile_type: Type of trust model (ICAO, AAMVA, EUDI, CUSTOM)
        enabled: Whether the profile is active
        organization_id: Organization ID for multi-tenant scoping
        use_case_tags: Business context tags (e.g., ["travel_documents"])
        auto_generated: Whether created by business wizard vs manual
        compliance_status: Current status (COMPLIANT, NEEDS_ATTENTION, SETUP_REQUIRED)
        manually_configured: Whether user manually configured advanced settings
        trust_sources: List of trust source configurations
        allowed_algorithms: Accepted cryptographic algorithms
        allowed_formats: Accepted credential formats
        revocation_policy: Revocation checking configuration
        time_policy: Time validation configuration
        allowed_issuers: Optional allowlist of issuer identifiers
        denied_issuers: Optional denylist of issuer identifiers
        metadata: Additional configuration data
    """
    
    name: str = ""
    display_name: str = ""
    description: str | None = None
    profile_type: TrustProfileType = TrustProfileType.CUSTOM
    enabled: bool = True
    
    # Organization scoping (v2)
    organization_id: str | None = None
    use_case_tags: list[str] = field(default_factory=list)
    auto_generated: bool = False
    compliance_status: str = "SETUP_REQUIRED"  # COMPLIANT, NEEDS_ATTENTION, SETUP_REQUIRED
    manually_configured: bool = False
    
    # Trust sources configuration
    trust_sources: list[dict[str, Any]] = field(default_factory=list)
    
    # Cryptographic constraints
    allowed_algorithms: list[CryptoAlgorithm] = field(
        default_factory=lambda: [
            CryptoAlgorithm.ES256,
            CryptoAlgorithm.ES384,
            CryptoAlgorithm.ES512,
        ]
    )
    allowed_formats: list[CredentialFormat] = field(
        default_factory=lambda: [
            CredentialFormat.MDOC,
            CredentialFormat.SD_JWT_VC,
        ]
    )
    
    # Validation policies
    revocation_policy: RevocationPolicy = field(default_factory=RevocationPolicy)
    time_policy: TimePolicy = field(default_factory=TimePolicy)
    
    # Issuer constraints
    allowed_issuers: list[str] | None = None
    denied_issuers: list[str] | None = None
    
    # Extension point
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def add_trust_source(
        self,
        source_type: str,
        source_uri: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Add a trust source to this profile."""
        self.trust_sources.append({
            "type": source_type,
            "uri": source_uri,
            "config": config or {},
        })
        self.touch()
    
    def is_issuer_allowed(self, issuer_id: str) -> bool:
        """Check if an issuer is allowed by this profile."""
        if self.denied_issuers and issuer_id in self.denied_issuers:
            return False
        if self.allowed_issuers is not None:
            return issuer_id in self.allowed_issuers
        return True
    
    def is_algorithm_allowed(self, algorithm: CryptoAlgorithm) -> bool:
        """Check if an algorithm is allowed by this profile."""
        return algorithm in self.allowed_algorithms
    
    def is_format_allowed(self, format: CredentialFormat) -> bool:
        """Check if a credential format is allowed by this profile."""
        return format in self.allowed_formats


# =============================================================================
# Credential Template
# =============================================================================

@dataclass
class CredentialTemplate(Entity):
    """
    Credential Template entity - defines what is issued.
    
    A Credential Template encapsulates:
    - Credential type and schema
    - Claims (raw and derived, e.g., `age_over_21`)
    - Validity rules (TTL, reissue requirements)
    - Issuer constraints (which keys may sign)
    - Selective-disclosure intent
    
    Attributes:
        name: Human-readable name for the template
        description: Optional description
        credential_type: Type identifier (e.g., "org.iso.18013.5.1.mDL")
        schema_uri: Optional URI to credential schema
        claims: List of claim definitions
        validity_rules: TTL and reissue configuration
        issuer_key_ids: Optional list of allowed signing key IDs
        trust_profile_id: Optional reference to required Trust Profile
        format: Default credential format
        namespace: Credential namespace (for mDoc)
        display: Display metadata for wallet rendering
        metadata: Additional configuration
    """
    
    name: str = ""
    description: str | None = None
    credential_type: str = ""
    schema_uri: str | None = None
    
    # Claims definition
    claims: list[ClaimDefinition] = field(default_factory=list)
    
    # Validity configuration
    validity_rules: ValidityRules = field(default_factory=ValidityRules)
    
    # Issuer constraints
    issuer_key_ids: list[str] | None = None
    trust_profile_id: str | None = None
    
    # Format and structure
    format: CredentialFormat = CredentialFormat.SD_JWT_VC
    namespace: str | None = None  # For mDoc: e.g., "org.iso.18013.5.1"
    
    # Display metadata
    display: dict[str, Any] = field(default_factory=dict)
    
    # Extension point
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def add_claim(self, claim: ClaimDefinition) -> None:
        """Add a claim definition to this template."""
        self.claims.append(claim)
        self.touch()
    
    def get_required_claims(self) -> list[ClaimDefinition]:
        """Get all required claims."""
        return [c for c in self.claims if c.required]
    
    def get_disclosable_claims(self) -> list[ClaimDefinition]:
        """Get all selectively disclosable claims."""
        return [c for c in self.claims if c.selectively_disclosable]
    
    def get_derived_claims(self) -> list[ClaimDefinition]:
        """Get all derived claims (predicates)."""
        return [c for c in self.claims if c.derived_from is not None]


# =============================================================================
# Presentation Policy
# =============================================================================

@dataclass
class PresentationPolicy(Entity):
    """
    Presentation Policy entity - defines what must be shown.
    
    A Presentation Policy encapsulates:
    - Accepted credential templates
    - Required claims or predicates
    - Holder-binding requirements
    - Issuer constraints (via Trust Profile reference)
    - Freshness and revocation expectations
    - Data-minimization rules
    
    Attributes:
        name: Human-readable name for the policy
        description: Optional description
        purpose: Purpose description for consent
        accepted_credential_types: List of accepted credential type IDs
        required_claims: List of required claims
        holder_binding: Required holder binding method
        trust_profile_id: Reference to Trust Profile for issuer validation
        freshness_requirements: How fresh credentials must be
        prefer_predicates: Prefer predicate proofs over raw values
        single_presentation: Require all claims in single credential
        metadata: Additional configuration
    """
    
    name: str = ""
    description: str | None = None
    purpose: str = ""
    
    # Accepted credentials
    accepted_credential_types: list[str] = field(default_factory=list)
    
    # Required claims
    required_claims: list[RequiredClaim] = field(default_factory=list)
    
    # Holder binding
    holder_binding: HolderBindingMethod = HolderBindingMethod.SESSION_NONCE
    
    # Trust constraints
    trust_profile_id: str | None = None
    
    # Freshness
    freshness_requirements: FreshnessRequirements = field(
        default_factory=FreshnessRequirements
    )
    
    # Data minimization
    prefer_predicates: bool = True
    single_presentation: bool = False
    
    # Extension point
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def add_required_claim(
        self,
        claim_name: str,
        credential_type: str,
        accept_predicate: bool = True,
        required_value: Any = None,
    ) -> None:
        """Add a required claim to this policy."""
        self.required_claims.append(RequiredClaim(
            claim_name=claim_name,
            credential_type=credential_type,
            accept_predicate=accept_predicate,
            required_value=required_value,
        ))
        self.touch()
    
    def get_claims_by_credential_type(self, credential_type: str) -> list[RequiredClaim]:
        """Get required claims for a specific credential type."""
        return [c for c in self.required_claims if c.credential_type == credential_type]


# =============================================================================
# Deployment Profile
# =============================================================================

@dataclass
class DeploymentProfile(Entity):
    """
    Deployment Profile entity - defines where identity runs.
    
    A Deployment Profile packages identity behavior for real endpoints:
    - Enabled flows and default policies
    - Network mode (online/offline)
    - Device UX configuration
    - Update and rollout rules
    - Key-access strategy
    
    Attributes:
        name: Human-readable name for the profile
        description: Optional description
        site_id: Optional site/location identifier
        enabled_flow_ids: List of enabled Flow IDs
        default_presentation_policy_id: Default policy for verifications
        network_mode: Online/offline/hybrid connectivity
        key_access_mode: How signing keys are accessed
        ux_config: User experience configuration
        update_policy: Software update policy
        offline_cache_ttl_hours: Hours to cache trust data offline
        biometric_required: Require biometric verification
        audit_all_events: Log all verification events
        metadata: Additional configuration
    """
    
    name: str = ""
    description: str | None = None
    site_id: str | None = None
    
    # Enabled flows and policies
    enabled_flow_ids: list[str] = field(default_factory=list)
    default_presentation_policy_id: str | None = None
    
    # Network configuration
    network_mode: NetworkMode = NetworkMode.ONLINE
    
    # Key access
    key_access_mode: KeyAccessMode = KeyAccessMode.KEY_VAULT
    
    # UX
    ux_config: UXConfig = field(default_factory=UXConfig)
    
    # Updates
    update_policy: UpdatePolicy = field(default_factory=UpdatePolicy)
    
    # Operational settings
    offline_cache_ttl_hours: int = 24
    biometric_required: bool = False
    audit_all_events: bool = True
    
    # Extension point
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def is_flow_enabled(self, flow_id: str) -> bool:
        """Check if a flow is enabled for this deployment."""
        return flow_id in self.enabled_flow_ids
    
    def enable_flow(self, flow_id: str) -> None:
        """Enable a flow for this deployment."""
        if flow_id not in self.enabled_flow_ids:
            self.enabled_flow_ids.append(flow_id)
            self.touch()
    
    def disable_flow(self, flow_id: str) -> None:
        """Disable a flow for this deployment."""
        if flow_id in self.enabled_flow_ids:
            self.enabled_flow_ids.remove(flow_id)
            self.touch()


# =============================================================================
# Flow
# =============================================================================

@dataclass
class Flow(Entity):
    """
    Flow entity - orchestrates end-to-end identity journeys.
    
    A Flow ties together:
    - A Trust Profile
    - A Credential Template (if issuing)
    - A Presentation Policy (if verifying)
    - One or more Deployment Profiles
    - An approval strategy
    
    Flows encode ordering, approvals, state transitions, and auditability.
    The flow type determines the fixed protocol sequence, while hooks
    allow business logic customization.
    
    Attributes:
        name: Human-readable name for the flow
        description: Optional description
        flow_type: Type of flow (determines step sequence)
        trust_profile_id: Reference to Trust Profile
        credential_template_id: Reference to Credential Template (for issuance)
        presentation_policy_id: Reference to Presentation Policy (for verification)
        deployment_profile_ids: References to Deployment Profiles
        approval_strategy: How approvals are handled
        enabled: Whether the flow is active
        hooks: Custom hook configurations (pre/post step)
        metadata: Additional configuration
    """
    
    name: str = ""
    description: str | None = None
    flow_type: FlowType = FlowType.APPLICATION_APPROVAL_ISSUANCE
    
    # Referenced entities
    trust_profile_id: str | None = None
    credential_template_id: str | None = None
    presentation_policy_id: str | None = None
    deployment_profile_ids: list[str] = field(default_factory=list)
    
    # Approval configuration
    approval_strategy: ApprovalStrategy = ApprovalStrategy.AUTO
    
    # State
    enabled: bool = True
    
    # Extensibility
    hooks: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    
    # Extension point
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def get_steps(self) -> list:
        """Get the fixed step sequence for this flow type."""
        return FLOW_STEPS.get(self.flow_type, [])
    
    def get_extensible_steps(self) -> list:
        """Get steps that can be customized via hooks."""
        return [s for s in self.get_steps() if s.extensible]
    
    def add_pre_hook(self, step_name: str, hook_config: dict[str, Any]) -> None:
        """Add a pre-execution hook for a step."""
        key = f"pre_{step_name}"
        if key not in self.hooks:
            self.hooks[key] = []
        self.hooks[key].append(hook_config)
        self.touch()
    
    def add_post_hook(self, step_name: str, hook_config: dict[str, Any]) -> None:
        """Add a post-execution hook for a step."""
        key = f"post_{step_name}"
        if key not in self.hooks:
            self.hooks[key] = []
        self.hooks[key].append(hook_config)
        self.touch()
    
    def get_pre_hooks(self, step_name: str) -> list[dict[str, Any]]:
        """Get pre-execution hooks for a step."""
        return self.hooks.get(f"pre_{step_name}", [])
    
    def get_post_hooks(self, step_name: str) -> list[dict[str, Any]]:
        """Get post-execution hooks for a step."""
        return self.hooks.get(f"post_{step_name}", [])


# =============================================================================
# Flow Execution (Runtime State)
# =============================================================================

@dataclass
class FlowExecution(Entity):
    """
    Flow Execution entity - tracks runtime state of a flow instance.
    
    This entity captures the execution state of a specific flow run,
    including current step, status, and step results.
    
    Attributes:
        flow_id: Reference to the Flow being executed
        status: Current execution status
        current_step: Name of the current step
        current_step_index: Index of current step in sequence
        step_results: Results from completed steps
        context_data: Execution context data
        started_at: When execution started
        completed_at: When execution completed (if done)
        error: Error message if failed
        metadata: Additional runtime data
    """
    
    flow_id: str = ""
    status: FlowStatus = FlowStatus.CREATED
    current_step: str | None = None
    current_step_index: int = 0
    step_results: dict[str, Any] = field(default_factory=dict)
    context_data: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def start(self) -> None:
        """Mark execution as started."""
        self.status = FlowStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)
        self.touch()
    
    def complete_step(self, step_name: str, result: Any) -> None:
        """Record step completion."""
        self.step_results[step_name] = {
            "result": result,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        self.current_step_index += 1
        self.touch()
    
    def await_approval(self) -> None:
        """Mark execution as awaiting approval."""
        self.status = FlowStatus.AWAITING_APPROVAL
        self.touch()
    
    def approve(self) -> None:
        """Mark as approved."""
        self.status = FlowStatus.APPROVED
        self.touch()
    
    def reject(self, reason: str | None = None) -> None:
        """Mark as rejected."""
        self.status = FlowStatus.REJECTED
        if reason:
            self.error = reason
        self.touch()
    
    def complete(self) -> None:
        """Mark execution as completed."""
        self.status = FlowStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.touch()
    
    def fail(self, error: str) -> None:
        """Mark execution as failed."""
        self.status = FlowStatus.FAILED
        self.error = error
        self.completed_at = datetime.now(timezone.utc)
        self.touch()
    
    def cancel(self) -> None:
        """Cancel execution."""
        self.status = FlowStatus.CANCELLED
        self.completed_at = datetime.now(timezone.utc)
        self.touch()
