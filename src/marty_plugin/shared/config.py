"""
Placeholder for configuration settings.
"""

from __future__ import annotations


class Settings:
    DOCUMENT_SIGNER_SERVICE_URL: str | None = "localhost:50052"  # Example URL
    GRPC_TIMEOUT_SECONDS: int = 10  # Example timeout
    # Add other settings as needed, e.g.:
    # DATABASE_URL = "postgresql://user:password@host:port/database"


settings = Settings()
