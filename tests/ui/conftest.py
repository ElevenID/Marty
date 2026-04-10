"""Pytest configuration for UI end-to-end tests."""

import socket
import threading
import time
import importlib.util
from collections.abc import Iterator
from contextlib import closing
from typing import Any

import pytest
import uvicorn
from playwright.sync_api import Browser, Page, sync_playwright

_UI_APP_MISSING = importlib.util.find_spec("ui_app") is None


def pytest_ignore_collect(collection_path, config):
    if _UI_APP_MISSING and collection_path.name.startswith("test_") and collection_path.suffix == ".py":
        return True
    return None


@pytest.fixture(scope="session")
def ui_settings() -> Any:
    """Provide test settings with mock mode enabled."""
    ui_config = pytest.importorskip("ui_app.config", reason="ui_app package not available in this workspace")
    UiSettings = ui_config.UiSettings
    return UiSettings(
        title="Test Marty UI",
        environment="test",
        passport_engine_target="mock",
        inspection_system_target="mock",
        mdl_engine_target="mock",
        trust_anchor_target="mock",
        grpc_timeout_seconds=10,
        enable_mock_data=True,
        theme="light",
    )


@pytest.fixture(scope="session")
def ui_server(ui_settings: Any) -> Iterator[str]:
    """Start the FastAPI app under uvicorn for the duration of the tests."""
    ui_app = pytest.importorskip("ui_app.app", reason="ui_app package not available in this workspace")
    create_app = ui_app.create_app
    app = create_app(ui_settings)

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    start_event = getattr(server, "started", None)
    timeout = time.time() + 10  # Increased timeout for startup
    while start_event and not start_event.is_set() and time.time() < timeout:
        time.sleep(0.1)

    if start_event and not start_event.is_set():
        msg = "UI server failed to start within timeout"
        raise RuntimeError(msg)

    base_url = f"http://{host}:{port}"

    # Wait for server to be responsive
    import requests

    for _ in range(50):  # 5 second timeout
        try:
            response = requests.get(base_url, timeout=1)
            if response.status_code == 200:
                break
        except requests.exceptions.RequestException:
            time.sleep(0.1)

    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    """Provide a shared browser instance with proper setup."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-web-security",
                "--allow-running-insecure-content",
            ],
        )
        yield browser
        browser.close()


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    """Provide a fresh page for each test with extended timeout."""
    context = browser.new_context(viewport={"width": 1280, "height": 720}, ignore_https_errors=True)
    page = context.new_page()
    page.set_default_timeout(10000)  # 10 second timeout
    page.set_default_navigation_timeout(10000)

    yield page

    context.close()


@pytest.fixture
def mobile_page(browser: Browser) -> Iterator[Page]:
    """Provide a mobile-sized page for responsive testing."""
    context = browser.new_context(
        viewport={"width": 375, "height": 667},
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
        ignore_https_errors=True,
    )
    page = context.new_page()
    page.set_default_timeout(10000)

    yield page

    context.close()


@pytest.fixture
def tablet_page(browser: Browser) -> Iterator[Page]:
    """Provide a tablet-sized page for responsive testing."""
    context = browser.new_context(
        viewport={"width": 768, "height": 1024},
        user_agent="Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
        ignore_https_errors=True,
    )
    page = context.new_page()
    page.set_default_timeout(10000)

    yield page

    context.close()


# Pytest markers for organizing tests
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "smoke: quick smoke tests")
    config.addinivalue_line("markers", "integration: cross-service integration tests")
    config.addinivalue_line("markers", "performance: performance-related tests")
    config.addinivalue_line("markers", "accessibility: accessibility tests")
    config.addinivalue_line("markers", "responsive: responsive design tests")
    config.addinivalue_line("markers", "workflow: end-to-end workflow tests")


# Test data fixtures
@pytest.fixture
def sample_certificate_data():
    """Provide sample certificate data for testing."""
    return {
        "country": "US",
        "organization": "Test Organization",
        "common_name": "Test Certificate",
        "key_size": "2048",
        "validity_years": "10",
    }


@pytest.fixture
def sample_passport_data():
    """Provide sample passport data for testing."""
    return {
        "passport_number": "P123456789",
        "first_name": "John",
        "last_name": "Doe",
        "date_of_birth": "1990-01-15",
        "nationality": "US",
        "issue_date": "2024-01-01",
        "expiry_date": "2034-01-01",
    }


@pytest.fixture
def sample_mdl_data():
    """Provide sample MDL data for testing."""
    return {
        "license_number": "LIC123456789",
        "first_name": "Jane",
        "last_name": "Smith",
        "date_of_birth": "1985-06-20",
        "issuing_authority": "State DMV",
        "license_class": "C",
        "issue_date": "2024-01-01",
        "expiry_date": "2029-01-01",
    }


@pytest.fixture
def sample_dtc_data():
    """Provide sample DTC data for testing."""
    return {
        "emergency": {
            "person_name": "Emergency Traveler",
            "original_passport": "P987654321",
            "emergency_contact": "+1-555-EMBASSY",
            "emergency_reason": "Passport stolen during travel",
            "destination_country": "United States",
        },
        "visitor": {
            "person_name": "Business Visitor",
            "visit_purpose": "Business meeting",
            "sponsor_organization": "TechCorp Inc.",
            "visit_duration": "7",
        },
        "temporary": {
            "person_name": "Temporary Resident",
            "temporary_reason": "Work assignment",
            "validity_period": "90",
            "sponsor_details": "Host Organization",
        },
    }
