"""
Trust Profile Resolver Service

Resolves effective trust profile configuration by merging TrustFramework
defaults with OrganizationTrustProfile overrides, and routes verification
based on credential format (mdoc/mDL → ICAO/AAMVA, SD-JWT/VC → EUDI).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from digital_identity.domain.entities import OrganizationTrustProfile, TrustFramework
from digital_identity.domain.value_objects import (
    CredentialFormat,
    CryptoAlgorithm,
    RevocationCheckMode,
    RevocationPolicy,
    TimePolicy,
    TrustProfileType,
)

if TYPE_CHECKING:
    from digital_identity.application.ports.outbound import TrustProfileRepositoryPort


@dataclass
class ResolvedTrustProfile:
    """
    Fully resolved trust profile combining framework defaults and org overrides.
    
    This is the effective configuration used for verification operations.
    """
    
    # Identity
    organization_id: str
    framework_id: str
    framework_type: TrustProfileType
    
    # Trust sources
    trust_anchor_source: str  # e.g., "ICAO PKD", "AAMVA IACA", "EUDI LoTL"
    use_custom_anchors: bool
    
    # Policies
    revocation_policy: RevocationPolicy
    time_policy: TimePolicy
    
    # Crypto
    allowed_algorithms: list[CryptoAlgorithm]
    min_key_size: int
    
    # Format support
    allowed_formats: list[CredentialFormat]
    
    # Jurisdiction filtering
    jurisdiction_filter: list[str] | None = None
    issuer_allowlist: list[str] | None = None
    issuer_denylist: list[str] | None = None
    
    # Metadata
    profile_name: str | None = None
    description: str | None = None


class TrustProfileResolver:
    """
    Service for resolving trust profiles with format-based dispatch.
    
    Responsibilities:
    - Merge TrustFramework defaults with OrganizationTrustProfile overrides
    - Route to appropriate trust anchor registry based on format
    - Apply jurisdiction and issuer filtering
    - Validate crypto algorithm compatibility
    """
    
    def __init__(self, trust_profile_repository: TrustProfileRepositoryPort):
        self.repository = trust_profile_repository
    
    async def resolve_for_organization(
        self,
        organization_id: str,
        credential_format: CredentialFormat | None = None,
    ) -> list[ResolvedTrustProfile]:
        """
        Resolve all trust profiles for an organization.
        
        Args:
            organization_id: Organization identifier
            credential_format: Optional format filter
        
        Returns:
            List of resolved trust profiles
        """
        # Get all organization trust profiles
        org_profiles = await self.repository.list_by_organization(organization_id)
        
        resolved = []
        for org_profile in org_profiles:
            # Get trust framework
            framework = await self.repository.get_framework(org_profile.framework_id)
            if not framework:
                continue
            
            # Resolve the profile
            resolved_profile = await self._resolve_profile(org_profile, framework)
            
            # Apply format filter if specified
            if credential_format:
                if credential_format not in resolved_profile.allowed_formats:
                    continue
            
            resolved.append(resolved_profile)
        
        return resolved
    
    async def resolve_for_verification(
        self,
        organization_id: str,
        credential_format: CredentialFormat,
        issuer_id: str | None = None,
        jurisdiction: str | None = None,
    ) -> ResolvedTrustProfile | None:
        """
        Resolve the best-matching trust profile for a verification operation.
        
        Dispatch logic:
        - mdoc/mDL → ICAO (ePassport) or AAMVA (mDL) based on jurisdiction
        - SD-JWT/VC → EUDI (EU) or Custom based on issuer
        - JWT-VC/LDP-VC → Custom trust roots
        
        Args:
            organization_id: Organization identifier
            credential_format: Format of credential being verified
            issuer_id: Optional issuer identifier for filtering
            jurisdiction: Optional jurisdiction code for filtering
        
        Returns:
            Best-matching resolved trust profile, or None if no match
        """
        # Get all profiles for this organization
        all_profiles = await self.resolve_for_organization(
            organization_id,
            credential_format=credential_format,
        )
        
        if not all_profiles:
            return None
        
        # Filter by format
        format_matches = [
            p for p in all_profiles
            if credential_format in p.allowed_formats
        ]
        
        if not format_matches:
            return None
        
        # Apply issuer filtering
        if issuer_id:
            format_matches = [
                p for p in format_matches
                if self._issuer_allowed(p, issuer_id)
            ]
        
        # Apply jurisdiction filtering
        if jurisdiction:
            format_matches = [
                p for p in format_matches
                if self._jurisdiction_allowed(p, jurisdiction)
            ]
        
        if not format_matches:
            return None
        
        # Dispatch based on format and framework type
        best_match = self._select_best_match(
            format_matches,
            credential_format,
            jurisdiction,
        )
        
        return best_match
    
    async def _resolve_profile(
        self,
        org_profile: OrganizationTrustProfile,
        framework: TrustFramework,
    ) -> ResolvedTrustProfile:
        """
        Merge framework defaults with organization overrides.
        
        Organization overrides take precedence over framework defaults.
        
        Args:
            org_profile: Organization-specific trust profile
            framework: Base trust framework
        
        Returns:
            Fully resolved trust profile
        """
        # Extract framework defaults from validation_ruleset
        fw_validation = framework.validation_ruleset or {}
        fw_revocation = fw_validation.get("revocation", {})
        fw_time = fw_validation.get("time", {})
        
        # Use org policy if set, otherwise build from framework defaults
        if org_profile.revocation_policy:
            revocation_policy = org_profile.revocation_policy
        else:
            # Build from framework defaults
            revocation_policy = RevocationPolicy(
                check_mode=RevocationCheckMode(fw_revocation.get("check_mode") or fw_revocation.get("mode", "HARD_FAIL")),
                cache_ttl_seconds=int(fw_revocation.get("cache_ttl_seconds", 300)),
            )
        
        # Use org time policy if set, otherwise build from framework defaults
        if org_profile.time_policy:
            time_policy = org_profile.time_policy
        else:
            # Build from framework defaults
            time_policy = TimePolicy(
                clock_skew_seconds=int(fw_time.get("clock_skew_seconds", 300)),
                max_credential_age_seconds=fw_time.get("max_credential_age_seconds"),
                require_freshness=fw_time.get("require_freshness", False),
                freshness_window_seconds=fw_time.get("freshness_window_seconds"),
            )
        
        # Merge allowed algorithms (org overrides or extends framework)
        allowed_algorithms = org_profile.allowed_algorithms or framework.default_algorithms
        
        # Merge allowed formats (org overrides or extends framework)
        allowed_formats = org_profile.allowed_formats or framework.default_formats
        
        # Extract framework type from code or default to CUSTOM
        framework_type_map = {
            "icao": TrustProfileType.ICAO,
            "ICAO": TrustProfileType.ICAO,
            "aamva": TrustProfileType.AAMVA,
            "AAMVA": TrustProfileType.AAMVA,
            "eudi": TrustProfileType.EUDI,
            "EUDI": TrustProfileType.EUDI,
        }
        framework_type = framework_type_map.get(framework.code.lower(), TrustProfileType.CUSTOM)
        
        return ResolvedTrustProfile(
            organization_id=org_profile.organization_id,
            framework_id=framework.id,
            framework_type=framework_type,
            trust_anchor_source=framework.display_name,
            use_custom_anchors=len(org_profile.metadata.get("custom_anchors", [])) > 0,
            revocation_policy=revocation_policy,
            time_policy=time_policy,
            allowed_algorithms=allowed_algorithms,
            min_key_size=fw_validation.get("crypto", {}).get("min_key_size", 2048),
            allowed_formats=allowed_formats,
            jurisdiction_filter=org_profile.jurisdiction_filter,
            issuer_allowlist=org_profile.allowed_issuers,
            issuer_denylist=org_profile.denied_issuers,
            profile_name=org_profile.display_name,
            description=org_profile.description,
        )
    
    def _issuer_allowed(self, profile: ResolvedTrustProfile, issuer_id: str) -> bool:
        """
        Check if an issuer is allowed by this profile.
        
        Logic:
        - If denylist exists and issuer in it → not allowed
        - If allowlist exists and issuer not in it → not allowed
        - Otherwise → allowed
        
        Args:
            profile: Resolved trust profile
            issuer_id: Issuer identifier to check
        
        Returns:
            True if issuer is allowed
        """
        # Check denylist first
        if profile.issuer_denylist and issuer_id in profile.issuer_denylist:
            return False
        
        # Check allowlist if it exists
        if profile.issuer_allowlist:
            return issuer_id in profile.issuer_allowlist
        
        # No filtering → allow
        return True
    
    def _jurisdiction_allowed(self, profile: ResolvedTrustProfile, jurisdiction: str) -> bool:
        """
        Check if a jurisdiction is allowed by this profile.
        
        Args:
            profile: Resolved trust profile
            jurisdiction: Jurisdiction code (e.g., "US", "CA", "EU")
        
        Returns:
            True if jurisdiction is allowed
        """
        if not profile.jurisdiction_filter:
            return True
        
        return jurisdiction.upper() in [j.upper() for j in profile.jurisdiction_filter]
    
    def _select_best_match(
        self,
        candidates: list[ResolvedTrustProfile],
        credential_format: CredentialFormat,
        jurisdiction: str | None = None,
    ) -> ResolvedTrustProfile:
        """
        Select the best-matching profile from candidates.
        
        Priority:
        1. Exact jurisdiction match
        2. Framework type appropriate for format
        3. Custom profiles (more specific)
        4. First match
        
        Args:
            candidates: List of candidate profiles
            credential_format: Credential format being verified
            jurisdiction: Optional jurisdiction for prioritization
        
        Returns:
            Best-matching profile
        """
        if not candidates:
            raise ValueError("No candidates provided")
        
        if len(candidates) == 1:
            return candidates[0]
        
        # Priority 1: Jurisdiction match
        if jurisdiction:
            jurisdiction_matches = [
                p for p in candidates
                if p.jurisdiction_filter and jurisdiction.upper() in [j.upper() for j in p.jurisdiction_filter]
            ]
            if jurisdiction_matches:
                candidates = jurisdiction_matches
        
        # Priority 2: Framework type for format
        format_framework_map = {
            CredentialFormat.MDOC: [TrustProfileType.ICAO, TrustProfileType.AAMVA],
            CredentialFormat.SD_JWT_VC: [TrustProfileType.EUDI, TrustProfileType.CUSTOM],
            CredentialFormat.JWT_VC: [TrustProfileType.CUSTOM],
            CredentialFormat.LDP_VC: [TrustProfileType.EUDI, TrustProfileType.CUSTOM],
        }
        
        preferred_types = format_framework_map.get(credential_format, [])
        if preferred_types:
            type_matches = [
                p for p in candidates
                if p.framework_type in preferred_types
            ]
            if type_matches:
                candidates = type_matches
        
        # Priority 3: Custom profiles (more specific than framework defaults)
        custom_profiles = [p for p in candidates if p.use_custom_anchors]
        if custom_profiles:
            return custom_profiles[0]
        
        # Priority 4: Return first match
        return candidates[0]
    
    async def get_trust_anchor_registry_for_profile(
        self,
        profile: ResolvedTrustProfile,
    ) -> str:
        """
        Determine which trust anchor registry to use for verification.
        
        Mapping:
        - ICAO → ICAO PKD (CSCA/DSC for ePassports)
        - AAMVA → AAMVA IACA (mDL trust roots)
        - EUDI → EUDI LoTL (EU wallet trust list)
        - CUSTOM → Organization custom anchors
        
        Args:
            profile: Resolved trust profile
        
        Returns:
            Registry identifier
        """
        registry_map = {
            TrustProfileType.ICAO: "icao_pkd",
            TrustProfileType.AAMVA: "aamva_iaca",
            TrustProfileType.EUDI: "eudi_lotl",
            TrustProfileType.CUSTOM: "custom_anchors",
        }
        
        return registry_map.get(profile.framework_type, "custom_anchors")
    
    async def validate_algorithm_compatibility(
        self,
        profile: ResolvedTrustProfile,
        algorithm: CryptoAlgorithm,
        key_size: int,
    ) -> bool:
        """
        Validate that a cryptographic algorithm and key size are allowed.
        
        Args:
            profile: Resolved trust profile
            algorithm: Algorithm to check
            key_size: Key size in bits
        
        Returns:
            True if algorithm and key size are allowed
        """
        # Check algorithm allowlist
        if algorithm not in profile.allowed_algorithms:
            return False
        
        # Check minimum key size
        if key_size < profile.min_key_size:
            return False
        
        return True
