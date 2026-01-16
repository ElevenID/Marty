"""
Database Migrations for Digital Identity Module

This package contains Alembic-style migrations for the Digital Identity tables.
"""

from .001_digital_identity_initial import upgrade, downgrade

__all__ = ["upgrade", "downgrade"]
