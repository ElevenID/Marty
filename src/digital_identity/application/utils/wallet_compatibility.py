"""
Wallet Compatibility Utilities

Derives wallet compatibility information from credential templates
based on format and issuance protocol configuration.
"""

from __future__ import annotations

from typing import Any


# Wallet compatibility mappings
WALLET_COMPATIBILITY_MAP = {
    # Open Badge v3 JWT
    ("VC_JWT", "OID4VCI_PRE_AUTH", "OB3_JWT"): {
        "name": "Open Badge v3 (VC-JWT + OID4VCI)",
        "description": "Compatible with Open Badge v3 wallets supporting W3C Verifiable Credentials (JWT) and OID4VCI pre-authorized code flow",
        "wallets": ["1Edtech Open Badge Passport", "Learning Credentials Wallet", "OID4VCI-compatible wallets"],
        "specifications": [
            "Open Badge v3.0",
            "W3C Verifiable Credentials Data Model v1.1",
            "OpenID for Verifiable Credential Issuance (OID4VCI)",
        ],
    },
    
    # Open Badge v3 JSON-LD
    ("JSON_LD", "OID4VCI_PRE_AUTH", "OB3_JSONLD"): {
        "name": "Open Badge v3 (JSON-LD + OID4VCI)",
        "description": "Compatible with Open Badge v3 wallets supporting W3C Verifiable Credentials (JSON-LD) with Data Integrity proofs and OID4VCI",
        "wallets": ["1Edtech Open Badge Passport", "Learning Credentials Wallet", "DIF Universal Wallet"],
        "specifications": [
            "Open Badge v3.0",
            "W3C Verifiable Credentials Data Model v1.1",
            "W3C Data Integrity",
            "OpenID for Verifiable Credential Issuance (OID4VCI)",
        ],
    },
    
    # SD-JWT VC
    ("SD_JWT_VC", "OID4VCI_PRE_AUTH", None): {
        "name": "SD-JWT VC + OID4VCI",
        "description": "Compatible with wallets supporting Selective Disclosure JWT Verifiable Credentials and OID4VCI",
        "wallets": ["eIDAS-compliant wallets", "EUDI Wallet", "OID4VCI-compatible wallets"],
        "specifications": [
            "SD-JWT VC (draft)",
            "OpenID for Verifiable Credential Issuance (OID4VCI)",
        ],
    },
    
    # mDoc/mDL (ISO 18013-5)
    ("MDOC", "OID4VCI_PRE_AUTH", None): {
        "name": "mDoc (ISO 18013-5) + OID4VCI",
        "description": "Compatible with ISO 18013-5 mobile driving license (mDL) wallets and OID4VCI-enabled readers",
        "wallets": ["Apple Wallet (mDL)", "Google Wallet (mDL)", "ISO-compliant mDL wallets"],
        "specifications": [
            "ISO/IEC 18013-5:2021",
            "OpenID for Verifiable Credential Issuance (OID4VCI)",
        ],
    },
}


def get_wallet_compatibility(
    credential_format: str,
    issuance_protocol: str | None,
    compliance_profile_code: str | None = None,
) -> dict[str, Any]:
    """
    Get wallet compatibility information for a credential template.
    
    Args:
        credential_format: Credential format (VC_JWT, JSON_LD, SD_JWT_VC, MDOC, etc.)
        issuance_protocol: Issuance protocol (OID4VCI_PRE_AUTH, etc.)
        compliance_profile_code: Optional compliance profile code for enhanced matching
    
    Returns:
        Wallet compatibility dictionary with name, description, wallets, and specifications
    """
    # Normalize inputs
    format_normalized = credential_format.upper() if credential_format else None
    protocol_normalized = issuance_protocol.upper() if issuance_protocol else None
    compliance_normalized = compliance_profile_code.upper() if compliance_profile_code else None
    
    # Try exact match with compliance profile
    if compliance_normalized:
        key = (format_normalized, protocol_normalized, compliance_normalized)
        if key in WALLET_COMPATIBILITY_MAP:
            return WALLET_COMPATIBILITY_MAP[key]
    
    # Try match without compliance profile
    key = (format_normalized, protocol_normalized, None)
    if key in WALLET_COMPATIBILITY_MAP:
        return WALLET_COMPATIBILITY_MAP[key]
    
    # Generic fallback
    return {
        "name": f"{credential_format} Credentials",
        "description": f"Credentials in {credential_format} format" + (
            f" issued via {issuance_protocol}" if issuance_protocol else ""
        ),
        "wallets": ["Compatible wallets supporting this format and protocol"],
        "specifications": [],
    }


def get_wallet_compatibility_summary(template_data: dict[str, Any]) -> str:
    """
    Get a human-readable wallet compatibility summary for a credential template.
    
    Args:
        template_data: Credential template data with format, issuance_protocol, compliance_profile_code
    
    Returns:
        Human-readable compatibility summary string
    """
    compat = get_wallet_compatibility(
        credential_format=template_data.get("format"),
        issuance_protocol=template_data.get("issuance_protocol"),
        compliance_profile_code=template_data.get("compliance_profile_code"),
    )
    
    return compat["description"]


def validate_wallet_protocol_compatibility(
    credential_format: str,
    issuance_protocol: str,
) -> tuple[bool, str]:
    """
    Validate that a credential format is compatible with an issuance protocol.
    
    Args:
        credential_format: Credential format
        issuance_protocol: Issuance protocol
    
    Returns:
        Tuple of (is_compatible, reason_if_incompatible)
    """
    # OID4VCI is compatible with most formats
    if issuance_protocol == "OID4VCI_PRE_AUTH":
        supported_formats = {"VC_JWT", "JSON_LD", "SD_JWT_VC", "MDOC", "JWT_VC"}
        if credential_format.upper() in supported_formats:
            return True, ""
        return False, f"Format {credential_format} not supported with OID4VCI"
    
    # Add other protocol validations as needed
    return True, ""
