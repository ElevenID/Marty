from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.retire_oci_packages import RetirementError, load_manifest, retire_packages


ROOT = Path(__file__).resolve().parents[2]


class FakeApi:
    def __init__(self, versions: dict[tuple[str, int], dict]) -> None:
        self.versions = versions
        self.deleted: list[tuple[str, str, int]] = []

    def version(self, owner: str, package: str, version_id: int) -> dict | None:
        assert owner == "ElevenID"
        return self.versions.get((package, version_id))

    def delete_version(self, owner: str, package: str, version_id: int) -> None:
        self.deleted.append((owner, package, version_id))


def manifest() -> dict:
    return load_manifest(
        ROOT / "release" / "retired-oci-packages.json", "ElevenID/Marty"
    )


def test_manifest_is_exact_complete_and_recovery_bound() -> None:
    document = manifest()
    assert document["recovery_bundle_sha256"] == (
        "BD460B770D24A92ECDAD535222854C5D512E93E4EE4A3B4E433FD15B73976A6B"
    )
    assert [package["name"] for package in document["packages"]] == [
        "marty",
        "charts/marty",
    ]
    assert sum(len(package["versions"]) for package in document["packages"]) == 9


def test_retirement_verifies_every_live_identity_before_deleting() -> None:
    document = manifest()
    versions = {}
    for package in document["packages"]:
        for version in package["versions"]:
            versions[(package["name"], version["id"])] = {
                "id": version["id"],
                "name": version["digest"],
                "metadata": {"container": {"tags": list(reversed(version["tags"]))}},
            }
    api = FakeApi(versions)

    result = retire_packages(document, api)

    assert len(result["deleted"]) == 9
    assert result["already_absent"] == []
    assert len(api.deleted) == 9


def test_retirement_is_resumable_for_absent_versions() -> None:
    result = retire_packages(manifest(), FakeApi({}))

    assert result["deleted"] == []
    assert len(result["already_absent"]) == 9


@pytest.mark.parametrize("field,value", [("name", "sha256:wrong"), ("id", 1)])
def test_retirement_fails_closed_on_live_identity_mismatch(field: str, value: object) -> None:
    document = manifest()
    version = document["packages"][0]["versions"][0]
    live = {
        "id": version["id"],
        "name": version["digest"],
        "metadata": {"container": {"tags": version["tags"]}},
    }
    live[field] = value
    api = FakeApi({("marty", version["id"]): live})

    with pytest.raises(RetirementError, match="identity does not match"):
        retire_packages(document, api)
    assert api.deleted == []


def test_manifest_rejects_a_different_repository(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest()), encoding="utf-8")

    with pytest.raises(RetirementError, match="repository does not match"):
        load_manifest(path, "ElevenID/other")
