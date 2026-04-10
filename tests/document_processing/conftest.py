"""
Pytest configuration and fixtures for Document Processing tests
"""

from __future__ import annotations

import sys
import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except ModuleNotFoundError:
        return False

# Add the project root to Python path using standardized approach
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Add document processing service to path using standardized approach
doc_processing_src = project_root / "src" / "document_processing"
sys.path.insert(0, str(doc_processing_src))

_DOC_PROCESSING_APP_MISSING = not _module_available("app.main")


def pytest_ignore_collect(collection_path, config):
    if (
        _DOC_PROCESSING_APP_MISSING
        and collection_path.name.startswith("test_")
        and collection_path.suffix == ".py"
    ):
        return True
    return None

if not _DOC_PROCESSING_APP_MISSING:
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
def sample_mrz_base64():
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
