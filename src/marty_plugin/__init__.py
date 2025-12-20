"""
Marty MMF Plugin

This module implements Marty as a plugin for the Marty Microservices Framework (MMF).
It integrates Marty's trust, PKI, and document processing services with the MMF 
infrastructure for unified configuration, observability, and deployment.
"""

__version__ = "1.0.0"
__author__ = "Marty Development Team"

from .plugin import MartyPlugin
from .config import MartyTrustPKIConfig
from .services import (
    TrustAnchorService,
    PKDService,
    DocumentSignerService,
    CSCAService
)

# Rust bindings are required - let ImportError propagate naturally
from . import _marty_rs

__all__ = [
    "MartyPlugin",
    "MartyTrustPKIConfig",
    "TrustAnchorService",
    "PKDService",
    "DocumentSignerService",
    "CSCAService",
    "_marty_rs"
]