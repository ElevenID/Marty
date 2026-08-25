"""Prevent parity-gated Python MMF compatibility packages from returning."""

import ast

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RETIRED_PATHS = (
    ROOT
    / "packages"
    / "marty-common"
    / "marty_common"
    / "crypto"
    / "credential_kms.py",
    ROOT / "src" / "notifications",
    ROOT / "src" / "marty_plugin" / "csca_service",
)

HISTORICAL_GUIDES = (
    ROOT / "docs" / "guides" / "CERTIFICATE_MANAGEMENT_MIGRATION_PLAN.md",
    ROOT / "docs" / "guides" / "CONFIGURATION_CONSOLIDATION_GUIDE.md",
    ROOT / "docs" / "guides" / "NATIVE_DEVELOPMENT.md",
)


def test_parity_gated_python_mmf_sources_are_absent() -> None:
    violations = []
    for path in RETIRED_PATHS:
        if path.is_file() or (path.is_dir() and any(path.rglob("*.py"))):
            violations.append(path.relative_to(ROOT))

    assert not violations


def test_retired_root_mmf_plugin_delivery_surface_is_absent() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "marty-msf" not in pyproject
    assert 'entry-points."mmf.plugins"' not in pyproject

    retired_files = (
        "src/marty_plugin/plugin.py",
        "src/marty_plugin/config.py",
        "src/marty_plugin/runtime.py",
        "src/marty_plugin/services.py",
        "src/marty_plugin/trust_anchor/modern_trust_anchor.py",
        "docker/mmf-plugin.Dockerfile",
        "docker-compose.yml",
        ".github/workflows/cd.yml",
        ".github/workflows/warm-ci-caches.yml",
        "config/plugins/marty.yaml",
    )
    returned = [path for path in retired_files if (ROOT / path).exists()]
    assert not returned, f"retired root MMF delivery files returned: {returned}"

    assert not any(path.is_file() for path in (ROOT / "deploy/helm/marty").rglob("*"))
    assert not any(path.is_file() for path in (ROOT / "k8s").rglob("*"))


def test_retained_trust_api_has_no_transitive_server_import() -> None:
    api = ROOT / "src/marty_plugin/trust_svc/api.py"
    module = ast.parse(api.read_text(encoding="utf-8"), filename=str(api))
    top_level_imports = {
        alias.name
        for node in module.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert "uvicorn" not in top_level_imports


def test_compatibility_source_has_no_legacy_framework_imports() -> None:
    retired_roots = {"framework", "mmf", "marty_msf"}
    violations: list[str] = []

    for source_root in (ROOT / "src", ROOT / "scripts"):
        for path in source_root.rglob("*.py"):
            module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    imports = (alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports = (node.module.split(".", 1)[0],)
                else:
                    continue
                for imported in imports:
                    if imported in retired_roots:
                        relative = path.relative_to(ROOT).as_posix()
                        violations.append(f"{relative}:{node.lineno}:{imported}")

    assert not violations, f"retired Python framework imports returned: {violations}"


def test_consumer_zero_framework_adapters_remain_absent() -> None:
    retired = (
        "packages/marty-common/marty_common/config_migration.py",
        "scripts/validate_observability_migration.py",
        "src/marty_plugin/trust_svc/config_unified.py",
        "src/marty_plugin/trust_anchor/modern_grpc_service.py",
        "src/marty_plugin/trust_anchor/observable_grpc_service.py",
    )

    returned = [path for path in retired if (ROOT / path).exists()]
    assert not returned, f"consumer-zero framework adapters returned: {returned}"


def test_retained_python_mmf_guides_are_explicitly_historical() -> None:
    for guide in HISTORICAL_GUIDES:
        introduction = " ".join(
            line.lstrip("> ")
            for line in guide.read_text(encoding="utf-8").splitlines()[:16]
        )
        assert "Historical record" in introduction, guide
        assert "not a supported" in introduction or "not a current" in introduction, (
            guide
        )
        assert "Do not" in introduction, guide


def test_retired_framework_is_not_a_build_context() -> None:
    for ignore_file in (ROOT / ".dockerignore", ROOT / ".gitignore"):
        assert "marty-microservices-framework/" not in ignore_file.read_text(
            encoding="utf-8"
        )
