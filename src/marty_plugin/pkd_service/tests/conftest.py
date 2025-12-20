"""
Pytest configuration and fixtures for PKD service tests
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Add the app directory to the Python path so we can import the app modules
sys.path.insert(0, str((Path(__file__).parent / "..").resolve()))

from app.main import app as pkd_app
from app.services.crl_service import CRLService
from app.services.deviationlist_service import DeviationListService
from app.services.dsclist_service import DSCListService
from app.services.masterlist_service import MasterListService
from app.services.sync_service import SyncService


@pytest.fixture
def app() -> FastAPI:
    """
    Return the FastAPI app for testing
    """
    return pkd_app


@pytest.fixture
def client(app: FastAPI) -> Generator:
    """
    Return a TestClient for interacting with the FastAPI app using standard pattern
    """
    with TestClient(app) as client:
        # Set test API key using shared standard
        client.headers.update({"X-API-Key": "test_api_key"})
        yield client


# Service mocks
@pytest.fixture
def mock_masterlist_service() -> MasterListService:
    """
    Return a MasterListService instance for testing
    """
    return MasterListService()


@pytest.fixture
def mock_dsclist_service() -> DSCListService:
    """
    Return a DSCListService instance for testing
    """
    return DSCListService()


@pytest.fixture
def mock_crl_service() -> CRLService:
    """
    Return a CRLService instance for testing
    """
    return CRLService()


@pytest.fixture
def mock_deviationlist_service() -> DeviationListService:
    """
    Return a DeviationListService instance for testing
    """
    return DeviationListService()


@pytest.fixture
def mock_sync_service() -> SyncService:
    """
    Return a SyncService instance for testing
    """
    return SyncService()


# Pytest event loop fixture for async tests
@pytest.fixture(scope="session")
def event_loop():
    """
    Create an instance of the default event loop for each test.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
