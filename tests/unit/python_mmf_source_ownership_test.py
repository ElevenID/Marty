"""Prevent parity-gated Python MMF compatibility packages from returning."""

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
