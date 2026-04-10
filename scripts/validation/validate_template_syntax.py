#!/usr/bin/env python3
"""
Validate Template Syntax and Consistency

This script validates template files for:
- Jinja2 syntax correctness
- Consistent variable usage across templates
- Required template blocks and sections
- Multi-language template consistency
"""

import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Set

logger = logging.getLogger(__name__)


def check_jinja2_syntax() -> list[str]:
    """Check Jinja2 template syntax."""
    issues = []

    template_files = []
    template_files.extend(list(Path("templates").glob("**/*.j2")))
    template_files.extend(list(Path("templates").glob("**/*.jinja")))
    template_files.extend(list(Path("templates").glob("**/*.jinja2")))

    for template_file in template_files:
        if not template_file.exists():
            continue

        try:
            content = template_file.read_text(encoding="utf-8")

            # Check for basic Jinja2 syntax errors
            # Unmatched braces
            open_braces = content.count("{{")
            close_braces = content.count("}}")
            if open_braces != close_braces:
                issues.append(f"{template_file}: Unmatched Jinja2 braces")

            # Unmatched blocks
            block_starts = len(re.findall(r"{%\s*\w+", content))
            block_ends = len(re.findall(r"{%\s*end\w+", content))
            if block_starts != block_ends:
                issues.append(f"{template_file}: Unmatched Jinja2 blocks")

            # Check for undefined variables (basic check)
            variables = re.findall(r"{{\s*(\w+)", content)
            for var in variables:
                if var in ["if", "for", "endif", "endfor"]:  # Skip control structures
                    continue
                # This is a basic check - in practice you'd validate against context

        except Exception as e:
            issues.append(f"{template_file}: Template parsing error: {e}")

    return issues


def check_template_consistency() -> list[str]:
    """Check consistency across multi-language templates."""
    issues = []

    # Group templates by service type
    service_templates = {}

    for template_dir in Path("templates").glob("*-service"):
        if not template_dir.is_dir():
            continue

        service_type = template_dir.name
        service_templates[service_type] = {}

        # Collect all template files by language/type
        for file_path in template_dir.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(template_dir)
                service_templates[service_type][str(relative_path)] = file_path

    # Check that common files exist across service types
    if len(service_templates) > 1:
        # Find common file patterns
        all_files = set()
        for service_files in service_templates.values():
            all_files.update(service_files.keys())

        # Check each service has key files
        required_files = [
            "Dockerfile",
            "README.md",
            "docker-compose.yml",
        ]

        for service_type, files in service_templates.items():
            for required_file in required_files:
                matching_files = [f for f in files.keys() if required_file in f]
                if not matching_files:
                    issues.append(f"{service_type}: Missing {required_file}")

    return issues


def check_variable_consistency() -> list[str]:
    """Check that template variables are used consistently."""
    issues = []

    # Collect all template variables across templates
    template_vars = {}

    for template_file in Path("templates").rglob("*"):
        if not template_file.is_file() or template_file.suffix not in [
            ".py",
            ".go",
            ".js",
            ".yaml",
            ".yml",
            ".j2",
            ".jinja",
            ".jinja2",
        ]:
            continue

        try:
            content = template_file.read_text(encoding="utf-8")

            # Find Jinja2 variables
            jinja_vars = set(re.findall(r"{{\s*(\w+)", content))

            # Find template string variables (Python format strings)
            format_vars = set(re.findall(r"{\s*(\w+)\s*}", content))

            all_vars = jinja_vars.union(format_vars)
            template_vars[template_file] = all_vars

        except Exception:
            logger.warning("Failed to parse template %s", template_file, exc_info=True)
            continue
    common_vars = ["service_name", "service_package", "author", "description"]

    for var in common_vars:
        files_with_var = [f for f, vars in template_vars.items() if var in vars]
        files_without_var = [
            f for f, vars in template_vars.items() if var not in vars and len(vars) > 0
        ]

        # If more than half the templates use a variable, flag missing ones
        if len(files_with_var) > len(files_without_var) and files_without_var:
            for missing_file in files_without_var[:3]:  # Limit output
                issues.append(f"{missing_file}: Missing common variable '{var}'")

    return issues


def check_template_structure() -> list[str]:
    """Check that templates have proper structure."""
    issues = []

    for service_dir in Path("templates").glob("*-service"):
        if not service_dir.is_dir():
            continue

        # Check for required directory structure
        required_dirs = ["src", "tests"]
        for req_dir in required_dirs:
            if not (service_dir / req_dir).exists():
                issues.append(f"{service_dir}: Missing {req_dir} directory")

        # Check for configuration files
        config_files = list(service_dir.glob("**/config*"))
        config_files.extend(list(service_dir.glob("**/*.env*")))
        config_files.extend(list(service_dir.glob("**/*.yaml")))

        if not config_files:
            issues.append(f"{service_dir}: Missing configuration files")

    return issues


def validate_template_syntax() -> bool:
    """Run all template validation checks."""
    print("🔍 Validating Template Syntax and Consistency...")

    all_issues = []

    # Run all checks
    all_issues.extend(check_jinja2_syntax())
    all_issues.extend(check_template_consistency())
    all_issues.extend(check_variable_consistency())
    all_issues.extend(check_template_structure())

    if all_issues:
        print("❌ Template validation failed:")
        for issue in all_issues:
            print(f"  - {issue}")
        return False
    else:
        print("✅ Template syntax and consistency validation passed")
        return True


if __name__ == "__main__":
    success = validate_template_syntax()
    sys.exit(0 if success else 1)
