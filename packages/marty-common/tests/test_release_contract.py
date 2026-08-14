"""Release metadata and checksum assembly contracts for marty-common."""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "packages" / "marty-common"


def test_package_and_runtime_versions_match() -> None:
    metadata = tomllib.loads((PACKAGE / "pyproject.toml").read_text(encoding="utf-8"))
    module = ast.parse(
        (PACKAGE / "marty_common" / "__init__.py").read_text(encoding="utf-8")
    )
    runtime_version = next(
        ast.literal_eval(statement.value)
        for statement in module.body
        if isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in statement.targets
        )
    )

    assert metadata["project"]["version"] == runtime_version


def test_checksum_manifest_cannot_include_itself() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-pypi.yml").read_text(
        encoding="utf-8"
    )
    checksum_command = re.search(
        r"run: (?P<command>find \. -type f[^\n]+> SHA256SUMS)",
        workflow,
    )

    assert checksum_command is not None
    assert "! -name SHA256SUMS" in checksum_command.group("command")


def test_release_verifies_immutability_and_exact_asset_digests_after_publish() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-pypi.yml").read_text(
        encoding="utf-8"
    )

    assert "repos/$GITHUB_REPOSITORY/immutable-releases" not in workflow
    assert 'gh release view "$TAG"' in workflow
    assert 'gh release create "$TAG" release/*' in workflow
    assert "--verify-tag" in workflow
    assert "repos/$GITHUB_REPOSITORY/releases/tags/$TAG" in workflow
    assert ".draft == false and .prerelease == false and .immutable == true" in workflow
    assert ".assets[] | select(.name == $name and .digest == $digest)" in workflow
    assert "softprops/action-gh-release" not in workflow
