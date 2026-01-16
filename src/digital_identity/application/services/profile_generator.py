"""
Trust Profile Auto-Generation Service

Maps business-focused use cases and acceptance types to technical trust profiles.
Abstracts ICAO/AAMVA/EUDI complexity from non-technical users.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class ComplianceStatus(str, Enum):
    """Compliance status for trust profiles."""
    COMPLIANT = "COMPLIANT"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    SETUP_REQUIRED = "SETUP_REQUIRED"


@dataclass
class GeneratedProfile:
    """Generated trust profile configuration."""
    name: str
    display_name: str
    profile_type: str  # ICAO, AAMVA, EUDI, CUSTOM
    description: str
    use_case_tags: List[str]
    acceptance_types: List[str]
    auto_generated: bool
    compliance_status: ComplianceStatus
    config: Dict  # Type-specific configuration (PKD URLs, trust anchors, etc.)


class ProfileGeneratorService:
    """
    Service that maps business use cases to trust profiles.
    
    Example mappings:
    - Travel Documents + Border Control → Passports-ICAO, DTC-ICAO profiles
    - Driver's Licenses + Law Enforcement → mDL-AAMVA profile
    - EU Credentials + EU Services → EuWallet-EUDI profile
    - Custom use cases → Custom X.509 profiles
    """

    # Mapping from use cases to trust profile types
    USE_CASE_TO_PROFILE_TYPE: Dict[str, str] = {
        "travel_documents": "ICAO",
        "driver_licenses": "AAMVA",
        "eu_credentials": "EUDI",
        "employee_ids": "CUSTOM",
        "student_ids": "CUSTOM",
        "access_badges": "CUSTOM",
    }

    # Display names for business-friendly UI
    USE_CASE_DISPLAY_NAMES: Dict[str, str] = {
        "travel_documents": "Travel Documents",
        "driver_licenses": "Driver's Licenses",
        "eu_credentials": "EU Digital Credentials",
        "employee_ids": "Employee IDs",
        "student_ids": "Student IDs",
        "access_badges": "Access Badges",
    }

    # Default configurations per profile type
    DEFAULT_CONFIGS: Dict[str, Dict] = {
        "ICAO": {
            "pkd_url": "https://pkddownloadsg.icao.int",
            "validate_aa": True,
            "validate_pa": True,
            "enable_csca_download": True,
        },
        "AAMVA": {
            "trust_anchor_url": "https://certificates.aamva.org",
            "enable_barcode_fallback": True,
            "require_state_verification": True,
        },
        "EUDI": {
            "trust_list_url": "https://eudi.ec.europa.eu/trust-list",
            "enable_mdl_support": True,
            "enable_pid_support": True,
        },
        "CUSTOM": {
            "require_root_ca": True,
            "enable_crl_checks": True,
            "enable_ocsp": False,
        },
    }

    def __init__(self):
        """Initialize the profile generator service."""
        pass

    def generate_profiles(
        self,
        organization_id: str,
        use_cases: List[str],
        acceptance_types: List[str],
        jurisdiction: str,
        manual_profiles: Optional[List[Dict]] = None,
    ) -> List[GeneratedProfile]:
        """
        Generate trust profiles based on business selections.
        
        Args:
            organization_id: Organization ID for scoping profiles
            use_cases: Selected use cases (e.g., ['travel_documents', 'driver_licenses'])
            acceptance_types: Selected acceptance types (e.g., ['border_control', 'law_enforcement'])
            jurisdiction: Operating jurisdiction (e.g., 'US', 'EU', 'US-CA')
            manual_profiles: Optional manually configured profiles from advanced mode
        
        Returns:
            List of generated profile configurations
        """
        profiles = []

        # If manual profiles provided, skip auto-generation
        if manual_profiles:
            for manual in manual_profiles:
                profiles.append(
                    GeneratedProfile(
                        name=manual.get("name", "Manual-Profile"),
                        display_name=manual.get("name", "Manual Profile"),
                        profile_type=manual.get("profile_type", "CUSTOM"),
                        description=manual.get("description", "Manually configured profile"),
                        use_case_tags=["manual"],
                        acceptance_types=acceptance_types,
                        auto_generated=False,
                        compliance_status=ComplianceStatus.SETUP_REQUIRED,
                        config=self._extract_manual_config(manual),
                    )
                )
            return profiles

        # Auto-generate profiles based on use cases
        for use_case in use_cases:
            profile_type = self.USE_CASE_TO_PROFILE_TYPE.get(use_case, "CUSTOM")
            display_name = self.USE_CASE_DISPLAY_NAMES.get(use_case, use_case.replace("_", " ").title())

            # Generate profile name with jurisdiction context
            profile_name = self._generate_profile_name(use_case, profile_type, jurisdiction)

            # Determine if this profile is relevant for selected acceptance types
            if self._is_profile_relevant(use_case, acceptance_types):
                profiles.append(
                    GeneratedProfile(
                        name=profile_name,
                        display_name=display_name,
                        profile_type=profile_type,
                        description=self._generate_description(use_case, acceptance_types),
                        use_case_tags=[use_case],
                        acceptance_types=acceptance_types,
                        auto_generated=True,
                        compliance_status=self._determine_initial_compliance(profile_type),
                        config=self._generate_config(profile_type, jurisdiction, use_case),
                    )
                )

            # Special case: Travel documents need multiple profiles (Passport + DTC)
            if use_case == "travel_documents" and "border_control" in acceptance_types:
                profiles.append(
                    GeneratedProfile(
                        name=f"DTC-ICAO-{jurisdiction}",
                        display_name="Digital Travel Credentials",
                        profile_type="ICAO",
                        description="ICAO Digital Travel Credential verification",
                        use_case_tags=["travel_documents", "dtc"],
                        acceptance_types=acceptance_types,
                        auto_generated=True,
                        compliance_status=ComplianceStatus.SETUP_REQUIRED,
                        config=self._generate_config("ICAO", jurisdiction, "dtc"),
                    )
                )

        return profiles

    def _generate_profile_name(self, use_case: str, profile_type: str, jurisdiction: str) -> str:
        """Generate a unique profile name."""
        use_case_part = use_case.replace("_", "-").title()
        jurisdiction_part = jurisdiction.replace("_", "-")
        return f"{use_case_part}-{profile_type}-{jurisdiction_part}"

    def _generate_description(self, use_case: str, acceptance_types: List[str]) -> str:
        """Generate a human-readable description."""
        use_case_display = self.USE_CASE_DISPLAY_NAMES.get(use_case, use_case)
        if acceptance_types:
            acceptance_display = ", ".join([t.replace("_", " ").title() for t in acceptance_types[:2]])
            return f"{use_case_display} for {acceptance_display}"
        return f"{use_case_display} verification"

    def _is_profile_relevant(self, use_case: str, acceptance_types: List[str]) -> bool:
        """Check if profile is relevant for selected acceptance types."""
        # Simple relevance check - can be expanded with more sophisticated logic
        relevance_map = {
            "travel_documents": ["airports", "border_control", "embassies"],
            "driver_licenses": ["law_enforcement", "age_restricted", "vehicle_rental"],
            "eu_credentials": ["eu_services", "border_control"],
        }
        
        relevant_types = relevance_map.get(use_case, [])
        return any(acc_type in relevant_types for acc_type in acceptance_types) or not relevant_types

    def _determine_initial_compliance(self, profile_type: str) -> ComplianceStatus:
        """Determine initial compliance status based on profile type."""
        # Auto-generated ICAO, AAMVA, EUDI profiles need setup
        # Custom profiles always need manual configuration
        if profile_type in ["ICAO", "AAMVA", "EUDI"]:
            return ComplianceStatus.SETUP_REQUIRED
        return ComplianceStatus.SETUP_REQUIRED

    def _generate_config(self, profile_type: str, jurisdiction: str, use_case: str) -> Dict:
        """Generate type-specific configuration."""
        base_config = self.DEFAULT_CONFIGS.get(profile_type, {}).copy()
        
        # Add jurisdiction-specific configuration
        if profile_type == "AAMVA" and jurisdiction.startswith("US-"):
            state = jurisdiction.split("-")[1]
            base_config["state_code"] = state
            base_config["state_specific_validation"] = True
        
        elif profile_type == "EUDI" and "EU" in jurisdiction:
            base_config["eu_member_state"] = jurisdiction
        
        elif profile_type == "ICAO":
            # Add country code from jurisdiction
            country_code = jurisdiction.split("-")[0] if "-" in jurisdiction else jurisdiction
            base_config["issuing_country"] = country_code
        
        return base_config

    def _extract_manual_config(self, manual_profile: Dict) -> Dict:
        """Extract configuration from manually configured profile."""
        config = {}
        
        profile_type = manual_profile.get("profile_type", "CUSTOM")
        
        if profile_type == "ICAO":
            if manual_profile.get("pkd_url"):
                config["pkd_url"] = manual_profile["pkd_url"]
        
        elif profile_type == "AAMVA":
            if manual_profile.get("trust_anchor"):
                config["trust_anchor_url"] = manual_profile["trust_anchor"]
        
        elif profile_type == "EUDI":
            if manual_profile.get("trust_list_url"):
                config["trust_list_url"] = manual_profile["trust_list_url"]
        
        elif profile_type == "CUSTOM":
            if manual_profile.get("root_certificate"):
                config["root_certificate"] = manual_profile["root_certificate"]
            if manual_profile.get("validation_url"):
                config["validation_url"] = manual_profile["validation_url"]
        
        return config

    def calculate_compliance_status(
        self,
        profile: GeneratedProfile,
        certificate_expiry_days: Optional[int] = None,
        trust_list_age_hours: Optional[int] = None,
        has_valid_config: bool = False,
    ) -> ComplianceStatus:
        """
        Calculate current compliance status for a profile.
        
        Args:
            profile: The profile to check
            certificate_expiry_days: Days until certificate expiration
            trust_list_age_hours: Hours since trust list update
            has_valid_config: Whether profile has valid configuration
        
        Returns:
            Current compliance status
        """
        if not has_valid_config:
            return ComplianceStatus.SETUP_REQUIRED
        
        # Certificate expiring soon
        if certificate_expiry_days is not None and certificate_expiry_days < 30:
            return ComplianceStatus.NEEDS_ATTENTION
        
        # Trust list stale
        if trust_list_age_hours is not None and trust_list_age_hours > 48:
            return ComplianceStatus.NEEDS_ATTENTION
        
        # All good
        if has_valid_config and (
            certificate_expiry_days is None or certificate_expiry_days >= 30
        ):
            return ComplianceStatus.COMPLIANT
        
        return ComplianceStatus.SETUP_REQUIRED
