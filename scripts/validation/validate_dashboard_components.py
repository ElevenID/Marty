#!/usr/bin/env python3
"""
Validate Dashboard and UI Components

This script validates dashboard and UI components:
- Component structure and organization
- Asset management
- Configuration files
- API integration points
"""

import logging
import sys
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


def check_dashboard_structure() -> list[str]:
    """Check dashboard directory structure."""
    issues = []

    # Look for dashboard/UI directories
    ui_dirs = []
    for pattern in ["dashboard", "ui", "frontend", "web"]:
        ui_dirs.extend(list(Path(".").glob(f"**/{pattern}")))

    if not ui_dirs:
        # No dashboard found - this might be okay
        print("ℹ️  No dashboard/UI directories found - skipping dashboard validation")
        return []

    for ui_dir in ui_dirs:
        if not ui_dir.is_dir():
            continue

        # Check for common web app structure
        expected_dirs = ["src", "public", "assets", "components"]
        missing_dirs = []

        for expected_dir in expected_dirs:
            if not (ui_dir / expected_dir).exists():
                missing_dirs.append(expected_dir)

        if missing_dirs:
            issues.append(f"{ui_dir}: Missing directories: {', '.join(missing_dirs)}")

        # Check for package.json or equivalent
        package_files = ["package.json", "requirements.txt", "Pipfile", "pyproject.toml"]
        has_package_file = any((ui_dir / pf).exists() for pf in package_files)

        if not has_package_file:
            issues.append(f"{ui_dir}: Missing package management file")

    return issues


def check_asset_management() -> list[str]:
    """Check asset management and build configuration."""
    issues = []

    # Look for build configuration files
    for ui_dir in Path(".").glob("**/dashboard"):
        if not ui_dir.is_dir():
            continue

        # Check for build tools
        build_files = [
            "webpack.config.js",
            "vite.config.js",
            "rollup.config.js",
            "Makefile",
            "build.sh",
        ]

        has_build_config = any((ui_dir / bf).exists() for bf in build_files)

        if not has_build_config:
            issues.append(f"{ui_dir}: Missing build configuration")

        # Check for static asset organization
        static_dirs = ["static", "assets", "public"]
        has_static_dir = any((ui_dir / sd).exists() for sd in static_dirs)

        if not has_static_dir:
            issues.append(f"{ui_dir}: Missing static assets directory")

    return issues


def check_component_organization() -> list[str]:
    """Check UI component organization."""
    issues = []

    for ui_dir in Path(".").glob("**/dashboard"):
        components_dir = ui_dir / "components"
        if not components_dir.exists():
            continue

        # Check for component files
        component_files = list(components_dir.glob("**/*.js"))
        component_files.extend(list(components_dir.glob("**/*.jsx")))
        component_files.extend(list(components_dir.glob("**/*.ts")))
        component_files.extend(list(components_dir.glob("**/*.tsx")))
        component_files.extend(list(components_dir.glob("**/*.vue")))

        if not component_files:
            issues.append(f"{components_dir}: No component files found")
            continue

        # Check for component naming conventions
        for comp_file in component_files:
            if comp_file.name.startswith("component"):
                # Generic naming - should be more specific
                issues.append(f"{comp_file}: Generic component naming")

    return issues


def check_api_integration() -> list[str]:
    """Check API integration configuration."""
    issues = []

    for ui_dir in Path(".").glob("**/dashboard"):
        if not ui_dir.is_dir():
            continue

        # Look for API configuration
        config_files = list(ui_dir.glob("**/config*.js"))
        config_files.extend(list(ui_dir.glob("**/config*.json")))
        config_files.extend(list(ui_dir.glob("**/.env*")))

        # Check for API endpoint configuration
        has_api_config = False
        for config_file in config_files:
            if not config_file.exists():
                continue

            try:
                content = config_file.read_text(encoding="utf-8")

                # Look for API-related configuration
                api_patterns = ["api", "endpoint", "baseUrl", "API_URL"]
                if any(pattern in content for pattern in api_patterns):
                    has_api_config = True
                    break

            except Exception:
                logger.warning("Failed to read config %s", config_file, exc_info=True)
                continue

        # Also check JavaScript/TypeScript files for API calls
        if not has_api_config:
            js_files = list(ui_dir.glob("**/*.js"))
            js_files.extend(list(ui_dir.glob("**/*.ts")))

            for js_file in js_files:
                if not js_file.exists():
                    continue

                try:
                    content = js_file.read_text(encoding="utf-8")

                    # Look for API calls
                    api_calls = ["fetch(", "axios.", "http.", "$.ajax", "XMLHttpRequest"]
                    if any(call in content for call in api_calls):
                        has_api_config = True
                        break

                except Exception:
                    logger.warning("Failed to read JS/TS file %s", js_file, exc_info=True)
                    continue
            issues.append(f"{ui_dir}: Missing API integration configuration")

    return issues


def validate_dashboard_components() -> bool:
    """Run all dashboard and UI component checks."""
    print("🔍 Validating Dashboard and UI Components...")

    all_issues = []

    # Run all checks
    all_issues.extend(check_dashboard_structure())
    all_issues.extend(check_asset_management())
    all_issues.extend(check_component_organization())
    all_issues.extend(check_api_integration())

    if all_issues:
        print("❌ Dashboard and UI component validation failed:")
        for issue in all_issues:
            print(f"  - {issue}")
        return False
    else:
        print("✅ Dashboard and UI component validation passed")
        return True


if __name__ == "__main__":
    success = validate_dashboard_components()
    sys.exit(0 if success else 1)
