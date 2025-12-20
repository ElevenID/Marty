"""UI application package exposing the FastAPI app factory."""

from .app import create_app

__all__ = ["create_app"]
