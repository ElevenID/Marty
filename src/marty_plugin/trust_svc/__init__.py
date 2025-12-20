"""
Trust Services Microservice

Centralized trust management for Marty including:
- PKD ingestion and master list processing
- Certificate revocation status tracking (CRL/OCSP)
- Trust anchor management and validation
- Immutable trust snapshots with KMS signatures
"""

from __future__ import annotations

__version__ = "1.0.0"
__author__ = "Marty Trust Services Team"
