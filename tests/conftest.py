"""Pytest hooks and environment shared by active compatibility tests."""

import os

import pytest


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "k8s: mark test as requiring Kubernetes")
    config.addinivalue_line("markers", "external: mark test as requiring external services")
    config.addinivalue_line("markers", "mrz: mark test as MRZ related")
    config.addinivalue_line("markers", "ocr: mark test as OCR related")
    config.addinivalue_line("markers", "pdf: mark test as PDF related")
    config.addinivalue_line(
        "markers", "document_processing: mark test as document processing service related"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers."""
    for item in items:
        # Add unit marker to unit tests
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)

        # Add integration marker to integration tests
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)

        # Add k8s marker to Kubernetes tests
        if "k8s" in str(item.fspath) or "kubernetes" in str(item.fspath):
            item.add_marker(pytest.mark.k8s)

        # Add document processing marker
        if "document_processing" in str(item.fspath):
            item.add_marker(pytest.mark.document_processing)

        # Add specific markers based on file names
        if "mrz" in item.name.lower():
            item.add_marker(pytest.mark.mrz)
        if "ocr" in item.name.lower():
            item.add_marker(pytest.mark.ocr)
        if "pdf" in item.name.lower():
            item.add_marker(pytest.mark.pdf)


@pytest.fixture(scope="session", autouse=True)
def test_environment_setup():
    """Set up test environment."""

    # Set test environment variables
    original_env = os.environ.copy()

    os.environ["MARTY_ENV"] = "testing"
    os.environ["MARTY_LOG_LEVEL"] = "DEBUG"
    os.environ["MARTY_DATABASE_URL"] = "postgresql://test:test@localhost:5432/test_martydb"

    yield

    # Restore environment
    os.environ.clear()
    os.environ.update(original_env)


def pytest_runtest_setup(item):
    """Skip tests based on availability of dependencies."""

    # Skip docker tests if docker not available
    if item.get_closest_marker("docker"):
        import subprocess

        try:
            subprocess.run(["docker", "version"], capture_output=True, check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            pytest.skip("Docker not available")


def pytest_report_teststatus(report, config):
    """Custom test status reporting."""
    if report.when == "call":
        if report.outcome == "passed":
            return report.outcome, "P", f"PASSED {report.nodeid}"
        if report.outcome == "failed":
            return report.outcome, "F", f"FAILED {report.nodeid}"
        if report.outcome == "skipped":
            return report.outcome, "S", f"SKIPPED {report.nodeid}"
    return None
