"""
Configuration for the Document Processing API service
"""

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings for the Document Processing service"""

    # API configuration
    API_ROOT_PATH: str = ""  # Root path for the API
    PROJECT_NAME: str = "Document Processing MRZ API"
    PROJECT_DESCRIPTION: str = """
    Generic OpenAPI for MRZ verification endpoint for document processing.
    Focuses on the POST /api/process flow with scenario: "Mrz",
    plus lightweight health endpoints. Includes API Key auth you can disable if you deploy in a DMZ.
    """
    VERSION: str = "0.1.0"

    # Server configuration
    HOST: str = os.getenv("HOST", "localhost")
    PORT: int = int(os.getenv("PORT", "8080"))

    # Environment configuration
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = ENVIRONMENT == "development"

    # Security configuration
    USE_API_KEY: bool = os.getenv("USE_API_KEY", "true").lower() == "true"
    API_KEY: str = os.getenv("API_KEY", "")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")

    # CORS configuration
    CORS_ORIGINS: list[str] = ["*"]

    # License configuration (for mock license info)
    LICENSE_ID: str = "4d43a2af-e321-496c-9a4e-5a8f3d26df0e"
    LICENSE_SERIAL: str = "OL70786"
    LICENSE_TYPE: str = "Transactional"
    LICENSE_VALID_UNTIL: str = "9999-12-31T23:59:59Z"

    # Core library version
    CORE_VERSION: str = "1.2.3"

    # Supported scenarios
    SUPPORTED_SCENARIOS: list[str] = ["Mrz"]

    # Service integration configuration
    USE_REAL_SERVICES: bool = os.getenv("USE_REAL_SERVICES", "false").lower() == "true"

    # Service endpoints
    PASSPORT_ENGINE_HOST: str = os.getenv("PASSPORT_ENGINE_HOST", "localhost")
    PASSPORT_ENGINE_PORT: int = int(os.getenv("PASSPORT_ENGINE_PORT", "8084"))

    INSPECTION_SYSTEM_HOST: str = os.getenv("INSPECTION_SYSTEM_HOST", "localhost")
    INSPECTION_SYSTEM_PORT: int = int(os.getenv("INSPECTION_SYSTEM_PORT", "8083"))

    DOCUMENT_SIGNER_HOST: str = os.getenv("DOCUMENT_SIGNER_HOST", "localhost")
    DOCUMENT_SIGNER_PORT: int = int(os.getenv("DOCUMENT_SIGNER_PORT", "8082"))

    class Config:
        env_file = ".env"


settings = Settings()
