"""
Reusable validation utilities for DRY validation patterns
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
from typing import Any


class ModuleValidator:
    """Utility class for validating Python modules, classes, and functions."""

    def __init__(self, src_path: str = "src") -> None:
        """
        Initialize the module validator.

        Args:
            src_path: Path to the source directory
        """
        self.src_path = Path(src_path)

    def validate_module_exists(self, module_path: str) -> bool:
        """
        Check if a module exists and can be imported.

        Args:
            module_path: Dotted module path (e.g., 'src.module.submodule')

        Returns:
            True if module exists and can be imported, False otherwise
        """
        try:
            spec = importlib.util.find_spec(module_path)
            return spec is not None
        except (ImportError, ValueError, ModuleNotFoundError):
            return False

    def validate_class_exists(self, module_path: str, class_name: str) -> bool:
        """
        Check if a class exists in the specified module.

        Args:
            module_path: Dotted module path
            class_name: Name of the class to validate

        Returns:
            True if class exists in module, False otherwise
        """
        try:
            module = importlib.import_module(module_path)
            return hasattr(module, class_name) and inspect.isclass(getattr(module, class_name))
        except (ImportError, AttributeError, ModuleNotFoundError):
            return False

    def validate_function_exists(self, module_path: str, function_name: str) -> bool:
        """
        Check if a function exists in the specified module.

        Args:
            module_path: Dotted module path
            function_name: Name of the function to validate

        Returns:
            True if function exists in module, False otherwise
        """
        try:
            module = importlib.import_module(module_path)
            attr = getattr(module, function_name, None)
            return callable(attr)
        except (ImportError, AttributeError, ModuleNotFoundError):
            return False

    def get_module_methods(self, module_path: str, class_name: str) -> list[str]:
        """
        Get all public methods of a class in a module.

        Args:
            module_path: Dotted module path
            class_name: Name of the class

        Returns:
            List of public method names (excluding private methods starting with _)
        """
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            return [
                name
                for name, method in inspect.getmembers(cls, predicate=inspect.ismethod)
                if not name.startswith("_")
            ]
        except (ImportError, AttributeError, ModuleNotFoundError):
            return []

    def validate_module_attributes(
        self, module_path: str, attributes: list[str]
    ) -> dict[str, bool]:
        """
        Validate multiple attributes (classes, functions) in a module.

        Args:
            module_path: Dotted module path
            attributes: List of attribute names to validate

        Returns:
            Dictionary mapping attribute names to existence status
        """
        results = {}

        try:
            module = importlib.import_module(module_path)
            for attr_name in attributes:
                results[attr_name] = hasattr(module, attr_name)
        except (ImportError, ModuleNotFoundError):
            for attr_name in attributes:
                results[attr_name] = False

        return results


class FeatureValidator:
    """High-level feature validation using module validators."""

    def __init__(self, src_path: str = "src") -> None:
        """
        Initialize the feature validator.

        Args:
            src_path: Path to the source directory
        """
        self.module_validator = ModuleValidator(src_path)
        self.results: dict[str, Any] = {}

    def validate_feature_set(
        self, feature_specs: dict[str, dict[str, Any]], result_key: str, description: str = ""
    ) -> dict[str, Any]:
        """
        Validate a complete set of features based on specifications.

        Args:
            feature_specs: Dictionary of feature specifications
            result_key: Key to store results under
            description: Human-readable description for logging

        Returns:
            Dictionary of validation results
        """
        if description:
            print(f"🔍 Validating {description}...")

        results = {}

        for feature_name, spec in feature_specs.items():
            result = self._validate_single_feature(spec)
            results[feature_name] = result

            # Log result
            completion = result.get("completion_score", 0)
            if result.get("module_exists", False):
                print(f"  ✅ {feature_name}: {completion:.1f}% complete")
            else:
                print(f"  ❌ {feature_name}: Module not found")

        self.results[result_key] = results
        return results

    def _validate_single_feature(self, spec: dict[str, Any]) -> dict[str, Any]:
        """
        Validate a single feature based on its specification.

        Args:
            spec: Feature specification with module, classes, and functions

        Returns:
            Validation result dictionary
        """
        module_path = spec["module"]

        result = {
            "module_exists": self.module_validator.validate_module_exists(module_path),
            "classes_found": [],
            "functions_found": [],
            "completion_score": 0,
        }

        if not result["module_exists"]:
            return result

        # Validate classes
        for class_name in spec.get("classes", []):
            if self.module_validator.validate_class_exists(module_path, class_name):
                result["classes_found"].append(class_name)

        # Validate functions
        for func_name in spec.get("functions", []):
            if self.module_validator.validate_function_exists(module_path, func_name):
                result["functions_found"].append(func_name)

        # Calculate completion score
        total_features = len(spec.get("classes", [])) + len(spec.get("functions", []))
        found_features = len(result["classes_found"]) + len(result["functions_found"])

        if total_features > 0:
            result["completion_score"] = (found_features / total_features) * 100
        else:
            result["completion_score"] = 100  # Nothing to validate means 100% complete

        return result

    def get_overall_completion(self) -> float:
        """
        Calculate overall completion percentage across all validated features.

        Returns:
            Overall completion percentage
        """
        total_score = 0
        feature_count = 0

        for result_set in self.results.values():
            if isinstance(result_set, dict):
                for feature_result in result_set.values():
                    if isinstance(feature_result, dict) and "completion_score" in feature_result:
                        total_score += feature_result["completion_score"]
                        feature_count += 1

        return (total_score / feature_count) if feature_count > 0 else 0

    def get_missing_features(self) -> list[str]:
        """
        Get list of features that are missing or incomplete.

        Returns:
            List of missing feature names
        """
        missing = []

        for result_key, result_set in self.results.items():
            if isinstance(result_set, dict):
                for feature_name, feature_result in result_set.items():
                    if isinstance(feature_result, dict):
                        if not feature_result.get("module_exists", False):
                            missing.append(f"{result_key}.{feature_name} (module missing)")
                        elif feature_result.get("completion_score", 0) < 100:
                            missing.append(f"{result_key}.{feature_name} (incomplete)")

        return missing


class QualityMetricsAnalyzer:
    """Analyzer for code quality metrics from various tools."""

    def __init__(self) -> None:
        """Initialize the quality metrics analyzer."""
        self.metrics: dict[str, Any] = {}

    def analyze_ruff_report(self, report_path: str = "ruff_report.json") -> dict[str, Any]:
        """
        Analyze Ruff linting report.

        Args:
            report_path: Path to the Ruff report file

        Returns:
            Dictionary with Ruff metrics
        """
        metrics = {"issues_count": 0, "error": None}

        if not os.path.exists(report_path):
            metrics["error"] = "Report file not found"
            return metrics

        try:
            with open(report_path) as f:
                ruff_data = json.load(f)
                if isinstance(ruff_data, list):
                    metrics["issues_count"] = len(ruff_data)

                    # Categorize issues by type
                    categories = {}
                    for issue in ruff_data:
                        category = issue.get("code", "unknown")
                        categories[category] = categories.get(category, 0) + 1

                    metrics["categories"] = categories
                else:
                    metrics["issues_count"] = 0

        except (json.JSONDecodeError, OSError) as e:
            metrics["error"] = str(e)

        self.metrics["ruff"] = metrics
        return metrics

    def analyze_mypy_report(self, report_path: str = "mypy_report.txt") -> dict[str, Any]:
        """
        Analyze MyPy type checking report.

        Args:
            report_path: Path to the MyPy report file

        Returns:
            Dictionary with MyPy metrics
        """
        metrics = {"errors_count": 0, "error": None}

        if not os.path.exists(report_path):
            metrics["error"] = "Report file not found"
            return metrics

        try:
            with open(report_path) as f:
                content = f.read()

                # Extract error count from MyPy output
                import re

                error_pattern = r"Found (\d+) errors? in"
                match = re.search(error_pattern, content)

                if match:
                    metrics["errors_count"] = int(match.group(1))

        except OSError as e:
            metrics["error"] = str(e)

        self.metrics["mypy"] = metrics
        return metrics

    def analyze_test_coverage(self, report_path: str = "coverage.json") -> dict[str, Any]:
        """
        Analyze test coverage report.

        Args:
            report_path: Path to the coverage report file

        Returns:
            Dictionary with coverage metrics
        """
        metrics = {"total_coverage": 0, "error": None}

        if not os.path.exists(report_path):
            metrics["error"] = "Coverage report not found"
            return metrics

        try:
            with open(report_path) as f:
                coverage_data = json.load(f)

                totals = coverage_data.get("totals", {})
                metrics["total_coverage"] = totals.get("percent_covered", 0)
                metrics["lines_covered"] = totals.get("covered_lines", 0)
                metrics["lines_total"] = totals.get("num_statements", 0)

                # Per-file breakdown
                files = coverage_data.get("files", {})
                metrics["file_coverage"] = {
                    file_path: file_data.get("summary", {}).get("percent_covered", 0)
                    for file_path, file_data in files.items()
                }

        except (json.JSONDecodeError, OSError, KeyError) as e:
            metrics["error"] = str(e)

        self.metrics["coverage"] = metrics
        return metrics

    def get_quality_summary(self) -> dict[str, Any]:
        """
        Get overall quality summary.

        Returns:
            Summary of all quality metrics
        """
        return {
            "ruff_issues": self.metrics.get("ruff", {}).get("issues_count", "unknown"),
            "mypy_errors": self.metrics.get("mypy", {}).get("errors_count", "unknown"),
            "test_coverage": self.metrics.get("coverage", {}).get("total_coverage", "unknown"),
            "quality_score": self._calculate_quality_score(),
        }

    def _calculate_quality_score(self) -> float:
        """Calculate overall quality score based on available metrics."""
        scores = []

        # Ruff score (fewer issues = better)
        ruff_issues = self.metrics.get("ruff", {}).get("issues_count")
        if isinstance(ruff_issues, int):
            # Assume 100 issues = 0% score, 0 issues = 100% score
            ruff_score = max(0, 100 - ruff_issues)
            scores.append(ruff_score)

        # MyPy score (fewer errors = better)
        mypy_errors = self.metrics.get("mypy", {}).get("errors_count")
        if isinstance(mypy_errors, int):
            # Assume 50 errors = 0% score, 0 errors = 100% score
            mypy_score = max(0, 100 - (mypy_errors * 2))
            scores.append(mypy_score)

        # Coverage score (direct percentage)
        coverage = self.metrics.get("coverage", {}).get("total_coverage")
        if isinstance(coverage, (int, float)):
            scores.append(coverage)

        return sum(scores) / len(scores) if scores else 0
