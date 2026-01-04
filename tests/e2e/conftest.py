"""
Pytest configuration for E2E tests using Playwright.
"""

import socket
import threading
import time
from collections.abc import AsyncGenerator
from contextlib import closing

import pytest
import requests
import uvicorn
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    ViewportSize,
    async_playwright,
)

from marty_plugin.legacy_apps.ui_app.app import create_app
from marty_plugin.legacy_apps.ui_app.config import UiSettings

from . import config


def is_port_open(host: str, port: int) -> bool:
    """Check if a port is open on the given host."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        return sock.connect_ex((host, port)) == 0


def wait_for_service(url: str, timeout: int = 30) -> bool:
    """Wait for a service to become available."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{url}/health", timeout=2)
            if response.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


@pytest.fixture
def ui_server():
    """Start the UI server for testing."""
    if wait_for_service(config.BASE_URL, timeout=5):
        yield config.BASE_URL
        return

    # Start UI server in a separate thread
    ui_config = UiSettings()
    app = create_app(ui_config)

    def run_server():
        uvicorn.run(app, host="0.0.0.0", port=8090, log_level="error")

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    # Wait for server to start
    if wait_for_service(config.BASE_URL):
        yield config.BASE_URL
    else:
        pytest.skip("UI server failed to start")


@pytest.fixture
async def playwright_instance():
    """Create Playwright instance."""
    async with async_playwright() as playwright:
        yield playwright


@pytest.fixture
async def browser(playwright_instance: Playwright) -> AsyncGenerator[Browser, None]:
    """Launch browser with consistent settings."""
    browser = await playwright_instance.chromium.launch(
        headless=config.HEADLESS,
        args=config.BROWSER_ARGS,
    )
    yield browser
    await browser.close()


@pytest.fixture
async def browser_context(browser: Browser) -> AsyncGenerator[BrowserContext, None]:
    """Create browser context with video recording."""
    context = await browser.new_context(
        viewport=ViewportSize(**config.VIEWPORT_SIZE),
        record_video_dir=str(config.VIDEOS_DIR),
        record_video_size={"width": 1920, "height": 1080},
    )
    yield context
    await context.close()


@pytest.fixture
async def page(browser_context: BrowserContext) -> AsyncGenerator[Page, None]:
    """Create a new page with tracing enabled."""
    page = await browser_context.new_page()

    # Start tracing
    trace_path = config.TRACES_DIR / f"trace-{int(time.time())}.zip"
    await browser_context.tracing.start(screenshots=True, snapshots=True, sources=True)

    # Set timeouts
    page.set_default_timeout(config.BROWSER_TIMEOUT)
    page.set_default_navigation_timeout(config.NAVIGATION_TIMEOUT)

    yield page

    # Stop tracing and save
    await browser_context.tracing.stop(path=str(trace_path))
    await page.close()


@pytest.fixture
async def authenticated_page(page: Page, ui_server: str) -> Page:
    """Provide a page that's navigated to the UI and ready for testing."""
    # Navigate to the UI
    await page.goto(ui_server)

    # Wait for the page to be ready
    await page.wait_for_load_state("networkidle")

    return page


@pytest.fixture
def mobile_viewport() -> ViewportSize:
    """Mobile viewport size for responsive testing."""
    return ViewportSize(**config.MOBILE_VIEWPORT)


@pytest.fixture
def tablet_viewport() -> ViewportSize:
    """Tablet viewport size for responsive testing."""
    return ViewportSize(**config.TABLET_VIEWPORT)


@pytest.fixture
def desktop_viewport() -> ViewportSize:
    """Desktop viewport size for responsive testing."""
    return ViewportSize(**config.VIEWPORT_SIZE)


@pytest.fixture
async def mobile_context(
    browser: Browser, mobile_viewport: ViewportSize
) -> AsyncGenerator[BrowserContext, None]:
    """Create browser context with mobile viewport."""
    context = await browser.new_context(
        viewport=mobile_viewport,
        record_video_dir=str(config.VIDEOS_DIR),
        record_video_size={"width": 1920, "height": 1080},
    )
    yield context
    await context.close()


@pytest.fixture
async def tablet_context(
    browser: Browser, tablet_viewport: ViewportSize
) -> AsyncGenerator[BrowserContext, None]:
    """Create browser context with tablet viewport."""
    context = await browser.new_context(
        viewport=tablet_viewport,
        record_video_dir=str(config.VIDEOS_DIR),
        record_video_size={"width": 1920, "height": 1080},
    )
    yield context
    await context.close()


@pytest.fixture(autouse=True)
def ensure_directories():
    """Ensure test directories exist."""
    config.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    config.VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    config.TRACES_DIR.mkdir(parents=True, exist_ok=True)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Hook to capture screenshots on test failure."""
    outcome = yield
    rep = outcome.get_result()

    # Add screenshot path to report for failed tests
    if rep.when == "call" and rep.failed:
        # Get page fixture if available
        page = getattr(item, "_playwright_page", None)
        if page and hasattr(item.function, "__self__"):
            test_name = f"{item.function.__self__.__class__.__name__}_{item.function.__name__}"
            screenshot_name = f"failure_{test_name}_{int(time.time())}.png"
            screenshot_path = config.SCREENSHOTS_DIR / screenshot_name

            try:
                # Schedule screenshot capture (will be done async)
                page.screenshot(path=str(screenshot_path))
                rep.screenshot_path = str(screenshot_path)
            except Exception:
                print(f"Failed to capture screenshot for {test_name}")

    return rep
