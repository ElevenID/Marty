"""
Playwright configuration for E2E tests of the Marty UI application.
"""

import os
from pathlib import Path

# Test configuration
BASE_URL = os.getenv("MARTY_BASE_URL", "http://localhost:8090")
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30000"))  # 30 seconds
NAVIGATION_TIMEOUT = int(os.getenv("NAVIGATION_TIMEOUT", "15000"))  # 15 seconds

# Screenshot and video settings
SCREENSHOTS_DIR = Path("tests/e2e/screenshots")
VIDEOS_DIR = Path("tests/e2e/videos")
TRACES_DIR = Path("tests/e2e/traces")

# Ensure directories exist
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
TRACES_DIR.mkdir(parents=True, exist_ok=True)

# Playwright browser configuration
BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-web-security",
    "--allow-running-insecure-content",
    "--ignore-certificate-errors",
]

VIEWPORT_SIZE = {"width": 1280, "height": 720}
MOBILE_VIEWPORT = {"width": 375, "height": 667}
TABLET_VIEWPORT = {"width": 768, "height": 1024}

# Test data
TEST_PASSPORT_ID = "IS1BA9DA00"  # Known test passport from data
TEST_UPLOAD_FILES = {
    "passport_image": "tests/test_data/passport_sample.jpg",
    "mdl_image": "tests/test_data/mdl_sample.jpg",
}

# Service endpoints for direct testing (using centralized registry)
from marty_plugin.common.service_registry import ServiceRegistry

SERVICES = ServiceRegistry.get_service_endpoints("local")
# Override UI service to use configured BASE_URL
SERVICES["ui"] = BASE_URL


class TestConfig:
    """Configuration class for contract testing."""

    # Use centralized service registry for all port mappings
    SERVICE_PORTS = ServiceRegistry.get_service_ports()
    GRPC_PORTS = ServiceRegistry.get_grpc_ports()
    METRICS_PORTS = ServiceRegistry.get_metrics_ports()

    def get_service_port(self, service_name: str) -> int:
        """Get HTTP port for a service."""
        return self.SERVICE_PORTS.get(service_name, 8080)

    def get_grpc_port(self, service_name: str) -> int:
        """Get gRPC port for a service."""
        return self.GRPC_PORTS.get(service_name, 9090)

    def get_metrics_port(self, service_name: str) -> int:
        """Get metrics port for a service."""
        return self.METRICS_PORTS.get(service_name, 8081)
