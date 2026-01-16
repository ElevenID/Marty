"""
Trust Profile Adapters

Concrete implementations of TrustProfilePort that wrap existing trust systems:
- ICAO: Wraps CSCATrustStore and Rust CscaRegistry
- AAMVA: Wraps Rust IacaRegistry for mDL verification
- EUDI: Placeholder for EU Digital Identity Wallet trust
- Custom: Configurable trust sources
"""

from digital_identity.infrastructure.trust.icao import IcaoTrustProfile
from digital_identity.infrastructure.trust.aamva import AamvaTrustProfile
from digital_identity.infrastructure.trust.eudi import EudiTrustProfile
from digital_identity.infrastructure.trust.custom import CustomTrustProfile

__all__ = [
    "IcaoTrustProfile",
    "AamvaTrustProfile",
    "EudiTrustProfile",
    "CustomTrustProfile",
]
