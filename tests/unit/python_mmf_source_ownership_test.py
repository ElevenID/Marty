"""Prevent parity-gated Python MMF compatibility packages from returning."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RETIRED_PATHS = (
    ROOT / "packages" / "marty-common" / "marty_common" / "crypto" / "credential_kms.py",
    ROOT / "src" / "notifications",
)


def test_parity_gated_python_mmf_sources_are_absent() -> None:
    violations = []
    for path in RETIRED_PATHS:
        if path.is_file() or (path.is_dir() and any(path.rglob("*.py"))):
            violations.append(path.relative_to(ROOT))

    assert not violations
