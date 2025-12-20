"""
Test Isolation and Cleanup Utilities

This module provides utilities for ensuring proper test isolation,
cleanup between test runs, and resource management.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TestIsolationManager:
    """Manages test isolation and cleanup operations."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.temp_directories: list[Path] = []
        self.temp_files: list[Path] = []

    def create_temp_directory(self, prefix: str = "marty_test_") -> Path:
        """Create a temporary directory that will be cleaned up."""
        temp_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self.temp_directories.append(temp_dir)
        logger.debug(f"Created temporary directory: {temp_dir}")
        return temp_dir

    def create_temp_file(self, suffix: str = ".tmp", content: str = "") -> Path:
        """Create a temporary file that will be cleaned up."""
        fd, temp_path = tempfile.mkstemp(suffix=suffix)
        temp_file = Path(temp_path)

        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
        except Exception:
            os.close(fd)
            raise

        self.temp_files.append(temp_file)
        logger.debug(f"Created temporary file: {temp_file}")
        return temp_file

    def cleanup_temp_resources(self):
        """Clean up all temporary resources created during tests."""
        # Clean up temporary directories
        for temp_dir in self.temp_directories:
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                    logger.debug(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory {temp_dir}: {e}")

        # Clean up temporary files
        for temp_file in self.temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
                    logger.debug(f"Cleaned up temporary file: {temp_file}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file {temp_file}: {e}")

        # Clear the lists
        self.temp_directories.clear()
        self.temp_files.clear()

    def reset_test_data(self):
        """Reset test data to initial state."""
        test_data_dirs = [
            self.project_root / "tests" / "data" / "mock_csca",
            self.project_root / "tests" / "data" / "csca_standalone",
        ]

        for data_dir in test_data_dirs:
            if data_dir.exists():
                # Remove any generated files but keep the directory structure
                for item in data_dir.rglob("*"):
                    if item.is_file() and item.suffix in [".tmp", ".test", ".generated"]:
                        try:
                            item.unlink()
                            logger.debug(f"Removed generated test file: {item}")
                        except Exception as e:
                            logger.warning(f"Failed to remove test file {item}: {e}")

    def clean_cache_directories(self):
        """Clean up cache directories that may interfere with tests."""
        cache_patterns = [
            "__pycache__",
            "*.pyc",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "*.egg-info",
        ]

        for pattern in cache_patterns:
            if pattern.startswith(("*", ".")):
                # File patterns
                for cache_file in self.project_root.rglob(pattern):
                    try:
                        if cache_file.is_file():
                            cache_file.unlink()
                        elif cache_file.is_dir():
                            shutil.rmtree(cache_file)
                        logger.debug(f"Cleaned cache: {cache_file}")
                    except Exception as e:
                        logger.debug(f"Could not clean cache {cache_file}: {e}")
            else:
                # Directory patterns
                for cache_dir in self.project_root.rglob(pattern):
                    try:
                        if cache_dir.is_dir():
                            shutil.rmtree(cache_dir)
                            logger.debug(f"Cleaned cache directory: {cache_dir}")
                    except Exception as e:
                        logger.debug(f"Could not clean cache directory {cache_dir}: {e}")

    def reset_database(self, database_url: str | None = None):
        """Reset the test database to clean state."""
        if not database_url:
            # Use default test database settings
            database_url = "postgresql://test_user:test_password@localhost:5432/marty_test"

        try:
            # Drop and recreate test database
            logger.info("Resetting test database...")

            # Note: This is a simplified version. In production, you might want
            # to use migrations or more sophisticated database reset mechanisms
            reset_commands = [
                # Connect to postgres database to drop/create test database
                "psql postgresql://test_user:test_password@localhost:5432/postgres -c 'DROP DATABASE IF EXISTS marty_test;'",
                "psql postgresql://test_user:test_password@localhost:5432/postgres -c 'CREATE DATABASE marty_test;'",
            ]

            for cmd in reset_commands:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, check=False
                )
                if result.returncode != 0:
                    logger.warning(f"Database reset command failed: {cmd}")
                    logger.warning(f"stderr: {result.stderr}")

        except Exception as e:
            logger.warning(f"Failed to reset database: {e}")

    def check_resource_usage(self):
        """Check current resource usage and warn if limits are exceeded."""
        try:
            # Check disk space
            disk_usage = shutil.disk_usage(self.project_root)
            free_percent = (disk_usage.free / disk_usage.total) * 100

            if free_percent < 20:  # Less than 20% free space
                logger.warning(f"Low disk space: {free_percent:.1f}% free")

            # Check for large temporary files
            temp_size = 0
            for temp_item in [*self.temp_directories, *self.temp_files]:
                if temp_item.exists():
                    if temp_item.is_file():
                        temp_size += temp_item.stat().st_size
                    elif temp_item.is_dir():
                        temp_size += sum(
                            f.stat().st_size for f in temp_item.rglob("*") if f.is_file()
                        )

            # Convert to MB
            temp_size_mb = temp_size / (1024 * 1024)
            if temp_size_mb > 100:  # More than 100MB of temp data
                logger.warning(f"Large temporary files: {temp_size_mb:.1f}MB")

        except Exception as e:
            logger.debug(f"Could not check resource usage: {e}")

    @contextmanager
    def isolated_test_environment(self):
        """Context manager for isolated test environment."""
        logger.debug("Setting up isolated test environment")

        try:
            # Setup
            self.clean_cache_directories()
            yield self

        finally:
            # Cleanup
            logger.debug("Cleaning up isolated test environment")
            self.cleanup_temp_resources()
            self.reset_test_data()
            self.check_resource_usage()


class DatabaseIsolationManager:
    """Specialized manager for database isolation in tests."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.transaction_stack: list[Any] = []

    @contextmanager
    def isolated_transaction(self):
        """Context manager for database transaction isolation."""
        # This would be implemented with actual database connections
        # For now, it's a placeholder for the concept
        logger.debug("Starting isolated database transaction")
        try:
            # Begin transaction
            yield
        finally:
            # Rollback transaction
            logger.debug("Rolling back isolated database transaction")


# Global isolation manager instance
_isolation_manager = None


def get_isolation_manager(project_root: Path | None = None) -> TestIsolationManager:
    """Get or create the global test isolation manager."""
    global _isolation_manager

    if _isolation_manager is None:
        if project_root is None:
            # Auto-detect project root
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent  # tests/isolation.py -> project_root

        _isolation_manager = TestIsolationManager(project_root)

    return _isolation_manager


# Cleanup function for use in test teardown
def cleanup_all_test_resources():
    """Clean up all test resources."""
    manager = get_isolation_manager()
    manager.cleanup_temp_resources()
    manager.clean_cache_directories()
    manager.reset_test_data()
