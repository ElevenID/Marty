"""Keep the released shared package independent of the retired Python MMF."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1]
SOURCE_ROOT = PACKAGE_ROOT / "marty_common"
RETIRED_CREDENTIAL_KMS = SOURCE_ROOT / "crypto" / "credential_kms.py"
RETIRED_IMPORT_ROOTS = {
    "framework",
    "mmf",
    "marty_msf",
    "marty_microservices_framework",
}


def _retired_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return [module for module in imports if module.partition(".")[0] in RETIRED_IMPORT_ROOTS]


def test_obsolete_python_credential_kms_adapter_is_absent() -> None:
    assert not RETIRED_CREDENTIAL_KMS.exists()


def test_marty_common_does_not_import_python_mmf() -> None:
    violations = {
        str(path.relative_to(PACKAGE_ROOT)): imports
        for path in sorted(SOURCE_ROOT.rglob("*.py"))
        if (imports := _retired_imports(path))
    }

    assert not violations, (
        f"marty-common must consume canonical native implementations, not the retired Python MMF: {violations}"
    )
