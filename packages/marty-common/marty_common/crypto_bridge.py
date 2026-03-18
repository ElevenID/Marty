"""
Crypto Bridge - Python wrapper for credential and verification operations.

This module provides access to:
- Credential operations from marty-rs (credentials, keys, status lists)
- Verification operations from marty-verification-py (Open Badges, mDoc, eMRTD, MRZ)

Usage:
    from marty_common.crypto_bridge import verify_jwt, generate_did_key
    from marty_common.crypto_bridge import open_badge_ob2_issue, parse_mrz
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# =============================================================================
# Import marty-rs (credential operations)
# =============================================================================
_marty_rs_available = False
try:
    from _marty_rs import (
        # Key generation
        generate_did_key,
        generate_p256_key,
        generate_p384_key,
        generate_rsa_key,
        # Credential operations
        create_verifiable_credential,
        create_credential_offer,
        generate_offer_uri,
        create_presentation,
        verify_jwt,
        generate_issuer_metadata,
        # Status list operations (from submodule)
        BitstringStatusList,
        TokenStatusList,
        create_bitstring_credential_subject,
        create_status_list_claim,
        # Utility
        check_isomdl,
        get_ssi_version,
        sum_as_string,
    )
    # BBS+ operations (from bbs submodule)
    from _marty_rs.bbs import (
        generate_bls12381_key,
        bbs_sign,
        bbs_verify,
        bbs_create_proof,
        bbs_verify_proof,
    )
    _marty_rs_available = True
    logger.info("marty-rs FFI loaded successfully")
except ImportError as e:
    logger.warning(
        f"marty-rs not available: {e}. "
        "Install marty-credentials[ffi] for credential operations. "
        "Some functionality will be limited."
    )
    # Define stubs for when marty-rs is not available
    generate_did_key = None
    generate_p256_key = None
    generate_p384_key = None
    generate_rsa_key = None
    create_verifiable_credential = None
    create_credential_offer = None
    generate_offer_uri = None
    create_presentation = None
    verify_jwt = None
    generate_issuer_metadata = None
    BitstringStatusList = None
    TokenStatusList = None
    create_bitstring_credential_subject = None
    create_status_list_claim = None
    check_isomdl = None
    get_ssi_version = None
    sum_as_string = None
    # BBS+ stubs
    generate_bls12381_key = None
    bbs_sign = None
    bbs_verify = None
    bbs_create_proof = None
    bbs_verify_proof = None

# =============================================================================
# Import marty-verification-py (verification operations)
# =============================================================================
_marty_verification_available = False
try:
    from _marty_verification import (
        # Open Badges
        open_badge_ob2_issue,
        open_badge_ob2_verify,
        open_badge_ob3_issue,
        open_badge_ob3_verify,
        # MRZ parsing
        parse_mrz,
        # mDoc/mDL verification
        verify_mdoc,
        verify_mdl,
        # eMRTD operations
        verify_emrtd,
        # Certificate operations
        build_self_signed_certificate_with_key,
        certificate_der_to_pem,
        verify_certificate_chain,
        # Crypto operations
        verify_signature,
        hash_data,
    )
    _marty_verification_available = True
    logger.info("marty-verification-py FFI loaded successfully")
except ImportError as e:
    logger.warning(
        f"marty-verification-py not available: {e}. "
        "Install marty-verification-py for verification operations. "
        "Some functionality will be limited."
    )
    # Define stubs for when marty-verification is not available
    open_badge_ob2_issue = None
    open_badge_ob2_verify = None
    open_badge_ob3_issue = None
    open_badge_ob3_verify = None
    parse_mrz = None
    verify_mdoc = None
    verify_mdl = None
    verify_emrtd = None
    build_self_signed_certificate_with_key = None
    certificate_der_to_pem = None
    verify_certificate_chain = None
    verify_signature = None
    hash_data = None

# =============================================================================
# Credential Operations - Direct exports from marty-rs
# =============================================================================

__all__ = [
    # FFI availability
    '_marty_rs_available',
    '_marty_verification_available',
    # Key generation (marty-rs)
    'generate_did_key',
    'generate_p256_key',
    'generate_p384_key',
    'generate_rsa_key',
    # Credential operations (marty-rs)
    'create_verifiable_credential',
    'create_credential_offer',
    'generate_offer_uri',
    'create_presentation',
    'verify_jwt',
    'generate_issuer_metadata',
    # Status list (marty-rs)
    'BitstringStatusList',
    'TokenStatusList',
    'create_bitstring_credential_subject',
    'create_status_list_claim',
    # Utility (marty-rs)
    'check_isomdl',
    'get_ssi_version',
    # BBS+ (marty-rs)
    'generate_bls12381_key',
    'bbs_sign',
    'bbs_verify',
    'bbs_create_proof',
    'bbs_verify_proof',
    # Open Badges (marty-verification)
    'open_badge_ob2_issue',
    'open_badge_ob2_verify',
    'open_badge_ob3_issue',
    'open_badge_ob3_verify',
    # MRZ parsing (marty-verification)
    'parse_mrz',
    # mDoc/mDL verification (marty-verification)
    'verify_mdoc',
    'verify_mdl',
    # eMRTD (marty-verification)
    'verify_emrtd',
    # Certificates (marty-verification)
    'build_self_signed_certificate_with_key',
    'certificate_der_to_pem',
    'verify_certificate_chain',
    # Crypto operations (marty-verification)
    'verify_signature',
    'hash_data',
    # High-level Open Badge Operations
    'verify_open_badge_ob2',
    'verify_open_badge_ob3',
    'issue_open_badge_ob2',
    'issue_open_badge_ob3',
]

# =============================================================================
# High-level Open Badge Operations
# =============================================================================

def verify_open_badge_ob2(payload: dict[str, Any]) -> dict[str, Any]:
    """
    High-level OB2 verification with JSON handling.
    """
    if open_badge_ob2_verify is None:
        raise RuntimeError("marty-verification-py not loaded")
    
    result_json = open_badge_ob2_verify(json.dumps(payload))
    return json.loads(result_json)


def verify_open_badge_ob3(payload: dict[str, Any]) -> dict[str, Any]:
    """
    High-level OB3 verification with JSON handling.
    """
    if open_badge_ob3_verify is None:
        raise RuntimeError("marty-verification-py not loaded")
    
    result_json = open_badge_ob3_verify(json.dumps(payload))
    return json.loads(result_json)


def issue_open_badge_ob2(request: dict[str, Any]) -> dict[str, Any]:
    """
    High-level OB2 issuance with JSON handling.
    """
    if open_badge_ob2_issue is None:
        raise RuntimeError("marty-verification-py not loaded")
    
    result_json = open_badge_ob2_issue(json.dumps(request))
    return json.loads(result_json)


def issue_open_badge_ob3(request: dict[str, Any]) -> dict[str, Any]:
    """
    High-level OB3 issuance with JSON handling.
    """
    if open_badge_ob3_issue is None:
        raise RuntimeError("marty-verification-py not loaded")
    
    result_json = open_badge_ob3_issue(json.dumps(request))
    return json.loads(result_json)
    """
    Check if a specific function is available from either marty-rs or marty-verification.
    
    Args:
        func_name: Name of the function to check
        
    Returns:
        True if the function is available and not None
    """
    return globals().get(func_name) is not None


def get_available_functions() -> dict[str, list[str]]:
    """
    Get list of all available functions organized by module.
    
    Returns:
        Dict with 'marty_rs' and 'marty_verification' keys, each containing list of available functions
    """
    marty_rs_functions = [
        'generate_did_key', 'generate_p256_key', 'generate_p384_key', 'generate_rsa_key',
        'create_verifiable_credential', 'create_credential_offer', 'generate_offer_uri',
        'create_presentation', 'verify_jwt', 'generate_issuer_metadata',
        'BitstringStatusList', 'TokenStatusList', 'create_bitstring_credential_subject',
        'create_status_list_claim', 'check_isomdl', 'get_ssi_version',
    ]
    
    marty_verification_functions = [
        'open_badge_ob2_issue', 'open_badge_ob2_verify', 'open_badge_ob3_issue', 'open_badge_ob3_verify',
        'parse_mrz', 'verify_mdoc', 'verify_mdl', 'verify_emrtd',
        'build_self_signed_certificate_with_key', 'certificate_der_to_pem', 'verify_certificate_chain',
        'verify_signature', 'hash_data',
    ]
    
    return {
        'marty_rs': [name for name in marty_rs_functions if globals().get(name) is not None],
        'marty_verification': [name for name in marty_verification_functions if globals().get(name) is not None],
    }


def get_module_status() -> dict[str, bool]:
    """
    Get availability status of both FFI modules.
    
    Returns:
        Dict with 'marty_rs' and 'marty_verification' keys indicating availability
    """
    return {
        'marty_rs': _marty_rs_available,
        'marty_verification': _marty_verification_available,
    }

