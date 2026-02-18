"""
Open Badge v3 Validation Service

Validates that Credential Templates comply with OBv3 requirements
when using OBv3 compliance profiles.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Required OBv3 claim fields
OBV3_REQUIRED_CLAIMS = {
    "achievement": {
        "required": True,
        "data_type": "object",
        "required_nested_fields": ["type", "name", "description", "criteria"],
        "description": "The achievement being recognized by this badge",
    },
    "criteria": {
        "required": True,
        "data_type": "object",
        "required_nested_fields": ["narrative"],
        "description": "Criteria for achieving the badge",
    },
    "issuer": {
        "required": True,
        "data_type": "object",
        "required_nested_fields": ["type", "name", "id"],
        "description": "Entity that issued the credential",
    },
    "issuedOn": {
        "required": True,
        "data_type": "datetime",
        "description": "Timestamp when the credential was issued",
    },
}


# OBv3 compliance profile codes
OBV3_COMPLIANCE_CODES = ("OB3_JWT", "OB3_JSONLD", "OB2_COMPATIBILITY")


class OBv3ValidationError(ValueError):
    """Raised when OBv3 validation fails."""
    pass


class OBv3ValidationService:
    """
    Validates Open Badge v3 compliance for credential templates.
    
    This service ensures that credential templates using OBv3 compliance
    profiles include all required fields and nested structures.
    """
    
    def validate_claims_schema(
        self,
        claims_schema: list[dict[str, Any]],
        compliance_profile_code: str,
    ) -> tuple[bool, list[str]]:
        """
        Validate that claims schema meets OBv3 requirements.
        
        Args:
            claims_schema: List of claim definitions
            compliance_profile_code: Code of the compliance profile (e.g., OB3_JWT)
        
        Returns:
            Tuple of (is_valid, list of validation errors)
        """
        # Only validate if it's an OBv3 profile
        if compliance_profile_code not in OBV3_COMPLIANCE_CODES:
            return True, []
        
        errors = []
        
        # Convert claims schema to dict for easier lookup
        claims_by_name = {claim.get("claim_name"): claim for claim in claims_schema}
        
        # Check each required OBv3 claim
        for claim_name, requirements in OBV3_REQUIRED_CLAIMS.items():
            if claim_name not in claims_by_name:
                errors.append(
                    f"Missing required OBv3 claim '{claim_name}': {requirements['description']}"
                )
                continue
            
            claim_def = claims_by_name[claim_name]
            
            # Validate data type if specified
            expected_type = requirements.get("data_type")
            if expected_type:
                actual_type = claim_def.get("data_type") or claim_def.get("type")
                if actual_type != expected_type:
                    errors.append(
                        f"Claim '{claim_name}' must have data_type '{expected_type}', "
                        f"got '{actual_type}'"
                    )
            
            # Validate nested fields for object types
            if requirements.get("required_nested_fields"):
                nested_fields = claim_def.get("nested_fields") or claim_def.get("properties") or {}
                
                # Handle both list and dict formats for nested fields
                if isinstance(nested_fields, list):
                    nested_field_names = {f.get("name") for f in nested_fields if isinstance(f, dict)}
                elif isinstance(nested_fields, dict):
                    nested_field_names = set(nested_fields.keys())
                else:
                    nested_field_names = set()
                
                for required_nested in requirements["required_nested_fields"]:
                    if required_nested not in nested_field_names:
                        errors.append(
                            f"Claim '{claim_name}' missing required nested field '{required_nested}'"
                        )
        
        is_valid = len(errors) == 0
        
        if not is_valid:
            logger.warning(
                f"OBv3 validation failed for compliance profile '{compliance_profile_code}': "
                f"{len(errors)} error(s)"
            )
        
        return is_valid, errors
    
    def validate_full_template(
        self,
        template_data: dict[str, Any],
        compliance_profile: dict[str, Any] | None = None,
    ) -> tuple[bool, list[str]]:
        """
        Validate a complete credential template for OBv3 compliance.
        
        Args:
            template_data: Full credential template data
            compliance_profile: Optional compliance profile data
        
        Returns:
            Tuple of (is_valid, list of validation errors)
        """
        errors = []
        
        # Get compliance profile code
        if compliance_profile:
            compliance_code = compliance_profile.get("code")
        else:
            compliance_code = template_data.get("compliance_profile_code")
        
        if not compliance_code:
            # No compliance profile, skip validation
            return True, []
        
        # Only validate OBv3 profiles
        if compliance_code not in OBV3_COMPLIANCE_CODES:
            return True, []
        
        # Validate claims schema
        claims_schema = template_data.get("claims") or []
        claims_valid, claims_errors = self.validate_claims_schema(
            claims_schema,
            compliance_code,
        )
        errors.extend(claims_errors)
        
        # Validate format matches compliance profile
        if compliance_profile:
            expected_format = compliance_profile.get("credential_format")
            actual_format = template_data.get("format")
            
            if expected_format and actual_format and expected_format != actual_format:
                errors.append(
                    f"Credential format '{actual_format}' does not match compliance profile "
                    f"expected format '{expected_format}'"
                )
        
        # Validate issuer artifacts
        if compliance_code in ("OB3_JWT", "OB3_JSONLD"):
            has_issuer_artifact = any([
                template_data.get("issuer_key_id"),
                template_data.get("issuer_did"),
                template_data.get("issuer_certificate_chain_pem"),
            ])
            
            if not has_issuer_artifact:
                errors.append(
                    "OBv3 credentials require at least one issuer artifact: "
                    "issuer_key_id, issuer_did, or issuer_certificate_chain_pem"
                )
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    def get_suggested_claims_schema(self, compliance_profile_code: str) -> list[dict[str, Any]]:
        """
        Get a suggested claims schema for an OBv3 compliance profile.
        
        Useful for template cloning and quick setup.
        
        Args:
            compliance_profile_code: OBv3 compliance profile code
        
        Returns:
            List of claim definitions with OBv3 required fields
        """
        if compliance_profile_code not in OBV3_COMPLIANCE_CODES:
            return []
        
        suggested_claims = []
        
        for claim_name, requirements in OBV3_REQUIRED_CLAIMS.items():
            claim_def = {
                "claim_name": claim_name,
                "data_type": requirements["data_type"],
                "required": requirements["required"],
                "description": requirements["description"],
            }
            
            # Add nested fields for object types
            if requirements.get("required_nested_fields"):
                claim_def["nested_fields"] = [
                    {"name": field_name, "type": "string", "required": True}
                    for field_name in requirements["required_nested_fields"]
                ]
            
            suggested_claims.append(claim_def)
        
        return suggested_claims
