#!/usr/bin/env python3
"""
Migration script for updating MRZ usage to enhanced parser.

This script analyzes the codebase for MRZ usage patterns and provides
automated migration suggestions or patches to use the enhanced MRZ parser
while maintaining backward compatibility.

Usage:
    python scripts/migrate_mrz_usage.py --analyze
    python scripts/migrate_mrz_usage.py --migrate --dry-run
    python scripts/migrate_mrz_usage.py --migrate --apply
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class MRZUsage(NamedTuple):
    """Represents an MRZ usage pattern found in the code."""

    file_path: str
    line_number: int
    line_content: str
    usage_type: str  # 'import', 'instantiate', 'method_call', 'function_call'
    pattern: str
    suggestion: str


class MRZMigrationAnalyzer:
    """Analyzes MRZ usage patterns and suggests migrations."""

    def __init__(self, root_path: Path):
        self.project_root = root_path
        self.usages: list[MRZUsage] = []

        # Define patterns to search for
        self.import_patterns = [
            r"from\s+.*mrz_utils.*import\s+([^#\n]+)",
            r"import\s+.*mrz_utils.*",
            r"from\s+.*\.mrz_utils\s+import\s+([^#\n]+)",
        ]

        self.usage_patterns = [
            (
                r"MRZParser\(\)",
                "instantiate",
                "Replace with MRZParser(use_hardened=True) for enhanced features",
            ),
            (
                r"MRZParser\.parse_td3_mrz\(",
                "method_call",
                "Consider using parse_mrz_with_validation() for better error handling",
            ),
            (
                r"MRZParser\.parse_td2_mrz\(",
                "method_call",
                "Consider using parse_mrz_with_validation() for better error handling",
            ),
            (
                r"MRZParser\.parse_td1_mrz\(",
                "method_call",
                "Consider using parse_mrz_with_validation() for better error handling",
            ),
            (
                r"MRZParser\.parse_mrz\(",
                "method_call",
                "Consider using parse_mrz_with_validation() for better error handling",
            ),
            (r"parse_td3_mrz\(", "function_call", "Update import to use enhanced parser"),
            (r"parse_td2_mrz\(", "function_call", "Update import to use enhanced parser"),
            (r"parse_td1_mrz\(", "function_call", "Update import to use enhanced parser"),
        ]

    def analyze_file(self, file_path: Path) -> list[MRZUsage]:
        """Analyze a single file for MRZ usage patterns."""
        usages = []

        try:
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()
        except (UnicodeDecodeError, FileNotFoundError):
            return usages

        # Check imports
        for line_num, line in enumerate(lines, 1):
            line_content = line.strip()

            # Skip comments and empty lines
            if not line_content or line_content.startswith("#"):
                continue

            # Check import patterns
            for pattern in self.import_patterns:
                if re.search(pattern, line_content):
                    usages.append(
                        MRZUsage(
                            file_path=str(file_path),
                            line_number=line_num,
                            line_content=line_content,
                            usage_type="import",
                            pattern=pattern,
                            suggestion="Update to import from mrz_enhanced for enhanced features",
                        )
                    )

            # Check usage patterns
            for pattern, usage_type, suggestion in self.usage_patterns:
                if re.search(pattern, line_content):
                    usages.append(
                        MRZUsage(
                            file_path=str(file_path),
                            line_number=line_num,
                            line_content=line_content,
                            usage_type=usage_type,
                            pattern=pattern,
                            suggestion=suggestion,
                        )
                    )

        return usages

    def analyze_project(self) -> list[MRZUsage]:
        """Analyze the entire project for MRZ usage patterns."""
        self.usages = []

        # Define directories to search
        search_dirs = [
            self.project_root / "src",
            self.project_root / "tests",
        ]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            for file_path in search_dir.rglob("*.py"):
                # Skip generated files and migrations
                if any(skip in str(file_path) for skip in ["__pycache__", ".pyc", "migration"]):
                    continue

                file_usages = self.analyze_file(file_path)
                self.usages.extend(file_usages)

        return self.usages

    def generate_migration_patches(self) -> dict[str, list[str]]:
        """Generate migration patches for each file."""
        patches = {}

        for usage in self.usages:
            file_path = usage.file_path
            if file_path not in patches:
                patches[file_path] = []

            if usage.usage_type == "import":
                # Suggest import updates
                if "mrz_utils" in usage.line_content:
                    new_line = usage.line_content.replace("mrz_utils", "mrz_enhanced")
                    patches[file_path].append(
                        f"Line {usage.line_number}: {usage.line_content.strip()}"
                    )
                    patches[file_path].append(f"  Suggested: {new_line.strip()}")

            elif usage.usage_type == "instantiate":
                # Suggest enhanced instantiation
                if "MRZParser()" in usage.line_content:
                    new_line = usage.line_content.replace(
                        "MRZParser()", "MRZParser(use_hardened=True)"
                    )
                    patches[file_path].append(
                        f"Line {usage.line_number}: {usage.line_content.strip()}"
                    )
                    patches[file_path].append(f"  Suggested: {new_line.strip()}")

            else:
                # General suggestions
                patches[file_path].append(f"Line {usage.line_number}: {usage.line_content.strip()}")
                patches[file_path].append(f"  Suggestion: {usage.suggestion}")

        return patches

    def generate_report(self) -> str:
        """Generate a comprehensive migration report."""
        if not self.usages:
            return "No MRZ usage patterns found."

        # Group usages by file
        files_by_usage = {}
        for usage in self.usages:
            file_path = usage.file_path
            if file_path not in files_by_usage:
                files_by_usage[file_path] = []
            files_by_usage[file_path].append(usage)

        # Generate report
        report_lines = [
            "MRZ Usage Migration Analysis Report",
            "=" * 50,
            "",
            f"Total MRZ usage patterns found: {len(self.usages)}",
            f"Files with MRZ usage: {len(files_by_usage)}",
            "",
        ]

        # Usage type summary
        usage_types = {}
        for usage in self.usages:
            usage_types[usage.usage_type] = usage_types.get(usage.usage_type, 0) + 1

        report_lines.extend(
            [
                "Usage Type Summary:",
                "-" * 20,
            ]
        )

        for usage_type, count in sorted(usage_types.items()):
            report_lines.append(f"  {usage_type}: {count}")

        report_lines.extend(["", "Files Analysis:", "-" * 15, ""])

        # File-by-file analysis
        for file_path in sorted(files_by_usage.keys()):
            rel_path = os.path.relpath(file_path, self.project_root)
            usages = files_by_usage[file_path]

            report_lines.extend(
                [
                    f"File: {rel_path}",
                    f"  Usage count: {len(usages)}",
                ]
            )

            for usage in usages:
                report_lines.append(
                    f"  Line {usage.line_number}: {usage.usage_type} - {usage.line_content.strip()}"
                )
                if usage.suggestion:
                    report_lines.append(f"    → {usage.suggestion}")

            report_lines.append("")

        return "\n".join(report_lines)


def create_migration_templates() -> dict[str, str]:
    """Create migration templates for common patterns."""
    return {
        "import_mrz_utils": """
# Before:
from marty_backend_common.utils.mrz_utils import MRZParser, MRZException

# After (with backward compatibility):
from marty_backend_common.utils.mrz_enhanced import MRZParser, MRZException

# Or (for enhanced features):
from marty_backend_common.utils.mrz_enhanced import MRZParser, MRZException, validate_mrz
""",
        "instantiate_parser": """
# Before:
parser = MRZParser()

# After (with enhanced features):
parser = MRZParser(use_hardened=True, strict_mode=True)

# Or (backward compatible):
parser = MRZParser(use_hardened=False)
""",
        "parse_with_validation": """
# Before:
try:
    mrz_data = parser.parse_mrz(mrz_string)
    # Basic error handling
except MRZException as e:
    logger.error(f"MRZ parsing failed: {e}")

# After (with enhanced validation):
result = parser.parse_mrz_with_validation(mrz_string)
if result.is_valid:
    mrz_data = result.get_mrz_data()
    logger.info(f"MRZ parsed successfully with confidence: {result.confidence}")
else:
    for error in result.errors:
        logger.error(f"MRZ error [{error.code}]: {error.message}")
        if error.suggestion:
            logger.info(f"Suggestion: {error.suggestion}")
""",
        "migration_helper": """
# Use migration helper to test compatibility:
from marty_backend_common.utils.mrz_enhanced import MRZMigrationHelper

# Test your MRZ samples
mrz_samples = ["P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<", ...]
results = MRZMigrationHelper.test_compatibility(mrz_samples)
report = MRZMigrationHelper.generate_migration_report(results)
print(report)
""",
    }


def main():
    """Main migration script entry point."""
    parser = argparse.ArgumentParser(description="MRZ usage migration tool")
    parser.add_argument("--analyze", action="store_true", help="Analyze MRZ usage patterns")
    parser.add_argument("--migrate", action="store_true", help="Generate migration patches")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")
    parser.add_argument("--apply", action="store_true", help="Apply migration patches")
    parser.add_argument("--templates", action="store_true", help="Show migration templates")
    parser.add_argument("--output", help="Output file for report")

    args = parser.parse_args()

    if not any([args.analyze, args.migrate, args.templates]):
        parser.print_help()
        return

    project_root = PROJECT_ROOT
    analyzer = MRZMigrationAnalyzer(project_root)

    if args.templates:
        templates = create_migration_templates()
        print("MRZ Migration Templates")
        print("=" * 30)

        for name, template in templates.items():
            print(f"\n{name.upper()}:")
            print(template)

        return

    if args.analyze or args.migrate:
        print("Analyzing MRZ usage patterns...")
        analyzer.analyze_project()

        if args.analyze:
            report = analyzer.generate_report()

            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(report)
                print(f"Report saved to {args.output}")
            else:
                print(report)

        if args.migrate:
            patches = analyzer.generate_migration_patches()

            print("\nMigration Patches")
            print("=" * 20)

            for file_path, file_patches in patches.items():
                rel_path = os.path.relpath(file_path, project_root)
                print(f"\nFile: {rel_path}")
                print("-" * len(rel_path))

                for patch in file_patches:
                    print(patch)

            if args.apply and not args.dry_run:
                print("\nWARNING: Automatic application not implemented yet.")
                print("Please review and apply patches manually.")
            elif args.dry_run:
                print("\nDry run complete. Review patches above.")


if __name__ == "__main__":
    main()
