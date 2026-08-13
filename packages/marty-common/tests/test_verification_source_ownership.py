"""Enforce the canonical native ownership boundary for document verification."""

from __future__ import annotations

from pathlib import Path

VERIFICATION_ROOT = Path(__file__).parents[1] / "marty_common" / "verification"
RETIRED_PYTHON_VERIFIERS = (
    VERIFICATION_ROOT / "unified_verification.py",
    VERIFICATION_ROOT / "unified_verification_simple.py",
)


def test_retired_python_verification_engines_are_absent() -> None:
    assert not [path for path in RETIRED_PYTHON_VERIFIERS if path.exists()]


def test_verification_sources_cannot_report_placeholder_success() -> None:
    offenders = []
    for path in VERIFICATION_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8").lower()
        if "verification placeholder" in source:
            offenders.append(path.name)

    assert not offenders, (
        "Document verification must use the canonical Rust backend; "
        f"placeholder verification found in: {', '.join(sorted(offenders))}"
    )
