"""
Database Migrations for Digital Identity Module

This package contains Alembic-style migrations for the Digital Identity tables.
"""

from importlib import import_module

_initial = import_module(f"{__name__}.001_digital_identity_initial")
upgrade = _initial.upgrade
downgrade = _initial.downgrade

__all__ = ["upgrade", "downgrade"]
