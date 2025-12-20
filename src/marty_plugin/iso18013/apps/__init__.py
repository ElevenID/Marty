"""
ISO/IEC 18013-5 Reference Application Package

This package contains reference implementations for both mDL reader and holder applications
demonstrating complete ISO 18013-5 and 18013-7 protocol flows.

Modules:
- reader: Reference reader application for mDL verification
- holder: Reference holder application (wallet) for mDL presentation
"""

from .holder import ConsentLevel, HolderConfig, HolderMode, ISO18013HolderApp, mDLCredential
from .reader import ISO18013ReaderApp, ReaderConfig, ReaderMode, VerificationLevel

__all__ = [
    # Reader application
    "ISO18013ReaderApp",
    "ReaderConfig",
    "ReaderMode",
    "VerificationLevel",
    # Holder application
    "ISO18013HolderApp",
    "HolderConfig",
    "HolderMode",
    "ConsentLevel",
    "mDLCredential",
]

# Version info
__version__ = "1.0.0"
__author__ = "ISO 18013 Reference Implementation"
__description__ = "Reference reader and holder applications for ISO/IEC 18013-5 mDL"
