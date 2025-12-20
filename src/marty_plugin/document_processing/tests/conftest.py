"""
Pytest configuration and fixtures for Document Processing tests
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add the project root to Python path using standardized approach
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Add Marty's src to path for imports using standardized approach
marty_src = Path(__file__).parent.parent.parent.parent / "src"
sys.path.insert(0, str(marty_src))

from app.main import app


@pytest.fixture
def client():
    """
    Create a test client for the FastAPI app using standard pattern
    """
    with TestClient(app) as test_client:
        # Set test API key using shared standard
        test_client.headers.update({"X-API-Key": "test_api_key"})
        yield test_client


@pytest.fixture
def sample_mrz_base64() -> str:
    """
    Sample base64 encoded image with MRZ (minimal 1x1 pixel PNG) - standardized
    """
    return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


@pytest.fixture
def sample_process_request():
    """
    Sample process request for testing
    """
    return {
        "processParam": {"scenario": "Mrz", "resultTypeOutput": ["MrzText", "MrzFields"]},
        "List": [
            {
                "ImageData": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
            }
        ],
        "tag": "test-session",
    }
