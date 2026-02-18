"""
Utility functions for credential template operations.
"""

from .wallet_compatibility import (
    get_wallet_compatibility,
    get_wallet_compatibility_summary,
    validate_wallet_protocol_compatibility,
    WALLET_COMPATIBILITY_MAP,
)

__all__ = [
    "get_wallet_compatibility",
    "get_wallet_compatibility_summary",
    "validate_wallet_protocol_compatibility",
    "WALLET_COMPATIBILITY_MAP",
]
