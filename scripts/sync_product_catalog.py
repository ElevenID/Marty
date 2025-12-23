"""Sync product versions into the product-catalog repo.

Reads local manifests/changelogs and updates the cloned product-catalog
working tree. Intended to be run from CI; see the workflow for triggers.
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import List, Optional

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG_ROOT = ROOT / "product-catalog"


def read_pyproject_version(path: pathlib.Path) -> str:
    import tomllib

    with path.open("rb") as f:
        data = tomllib.load(f)
    return str(data["project"]["version"])


def parse_changelog(path: pathlib.Path):
    """Parse the topmost changelog entry (Keep a Changelog format)."""
    text = path.read_text(encoding="utf-8")
    header_match = re.search(r"## \\[(?P<version>[^\\]]+)\\]\\s+-\\s+(?P<date>\\d{4}-\\d{2}-\\d{2})", text)
    if not header_match:
        return None, None, []

    version = header_match.group("version")
    date = header_match.group("date")

    # Grab bullet lines until the next header
    section_start = header_match.end()
    rest = text[section_start:]
    next_header = rest.find("## [")
    body = rest if next_header == -1 else rest[: next_header]
    highlights = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("-"):
            highlights.append(stripped.lstrip("-").strip())
    return version, date, highlights[:5]


def read_cargo_workspace_version(path: pathlib.Path) -> Optional[str]:
    import tomllib

    with path.open("rb") as f:
        data = tomllib.load(f)
    workspace = data.get("workspace", {})
    package = workspace.get("package", {})
    version = package.get("version")
    return str(version) if version else None


def update_versions_file(
    path: pathlib.Path,
    version: str,
    released: Optional[str],
    highlights: List[str],
    status: str,
    source: str,
) -> bool:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    existing_versions = {entry.get("version") for entry in data.get("releases", [])}
    if version in existing_versions:
        return False

    for entry in data.get("releases", []):
        if entry.get("status") == "current":
            entry["status"] = "previous"

    entry = {
        "version": version,
        "released": released,
        "status": status,
        "highlights": highlights,
        "source": source,
    }
    releases = data.get("releases", [])
    releases.insert(0, entry)
    data["releases"] = releases
    data["latest"] = version

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return True


def main():
    changes = []

    # Verification API (Python)
    pyproject_version = read_pyproject_version(ROOT / "pyproject.toml")
    changelog_version, changelog_date, changelog_highlights = parse_changelog(ROOT / "docs" / "CHANGELOG.md")
    verification_version = changelog_version or pyproject_version
    verification_highlights = changelog_highlights or [
        "Verification API release",
    ]
    if update_versions_file(
        CATALOG_ROOT / "products" / "verification-api" / "versions.json",
        verification_version,
        changelog_date,
        verification_highlights,
        "current",
        "docs/CHANGELOG.md",
    ):
        changes.append(f"verification-api {verification_version}")

    # Kiosk (Tauri/Rust)
    kiosk_version = read_cargo_workspace_version(ROOT / "marty-verifier" / "Cargo.toml")
    kiosk_highlights = [
        "Offline-first kiosk with SQLCipher storage and keychain integration",
        "Supports mDL, eMRTD, OID4VP, SD-JWT",
        "Hardware tiers for camera-only vs NFC/BLE/biometrics with TPM-bound licensing",
    ]
    if kiosk_version and update_versions_file(
        CATALOG_ROOT / "products" / "kiosk" / "versions.json",
        kiosk_version,
        None,
        kiosk_highlights,
        "preview",
        "marty-verifier/README.md",
    ):
        changes.append(f"kiosk {kiosk_version}")

    # Issuance API (placeholder until dedicated versioning is wired)
    issuance_version = "0.1.0"
    issuance_highlights = [
        "Issuance flows for mDL/mDoc/DTC credentials (OIDC4VCI)",
        "Document signer service with audit trails and policy controls",
    ]
    if update_versions_file(
        CATALOG_ROOT / "products" / "issuance-api" / "versions.json",
        issuance_version,
        None,
        issuance_highlights,
        "planning",
        "src/document_signer",
    ):
        changes.append(f"issuance-api {issuance_version}")

    print("changes:", ", ".join(changes) if changes else "none")


if __name__ == "__main__":
    main()
