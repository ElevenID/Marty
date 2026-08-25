#!/usr/bin/env python3
"""Delete only archived OCI package versions declared by exact ID and digest."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RetirementError(RuntimeError):
    """Raised when retirement evidence or live package state is unsafe."""


@dataclass(frozen=True)
class GitHubPackagesApi:
    token: str
    api_url: str = "https://api.github.com"

    def _request(self, method: str, path: str) -> Any | None:
        request = urllib.request.Request(
            f"{self.api_url.rstrip('/')}/{path.lstrip('/')}",
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status == 204:
                    return {}
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            message = ""
            try:
                error_payload = json.loads(exc.read().decode("utf-8"))
                if isinstance(error_payload, dict) and isinstance(
                    error_payload.get("message"), str
                ):
                    message = f": {error_payload['message']}"
            except (UnicodeDecodeError, json.JSONDecodeError, OSError):
                pass
            raise RetirementError(
                f"GitHub API returned {exc.code} for {method} {path}{message}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RetirementError(f"GitHub API request failed for {path}: {exc}") from exc
        return payload

    def version(self, owner: str, package: str, version_id: int) -> dict[str, Any] | None:
        encoded = urllib.parse.quote(package, safe="")
        payload = self._request(
            "GET", f"orgs/{owner}/packages/container/{encoded}/versions/{version_id}"
        )
        if payload is not None and not isinstance(payload, dict):
            raise RetirementError(f"GitHub API returned a non-object for {package}@{version_id}")
        return payload

    def versions(self, owner: str, package: str) -> list[dict[str, Any]]:
        encoded = urllib.parse.quote(package, safe="")
        versions: list[dict[str, Any]] = []
        for page in range(1, 101):
            payload = self._request(
                "GET",
                f"orgs/{owner}/packages/container/{encoded}/versions?per_page=100&page={page}",
            )
            if payload is None:
                return []
            if not isinstance(payload, list) or not all(
                isinstance(version, dict) for version in payload
            ):
                raise RetirementError(
                    f"GitHub API returned an invalid version inventory for {package}"
                )
            versions.extend(payload)
            if len(payload) < 100:
                return versions
        raise RetirementError(f"package version inventory exceeds safety limit: {package}")

    def delete_package(self, owner: str, package: str) -> None:
        encoded = urllib.parse.quote(package, safe="")
        result = self._request("DELETE", f"orgs/{owner}/packages/container/{encoded}")
        if result is None:
            raise RetirementError(f"package disappeared during deletion: {package}")


def load_manifest(path: Path, repository: str) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetirementError(f"cannot read retirement manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise RetirementError("retirement manifest schema_version must be 1")
    if manifest.get("repository") != repository:
        raise RetirementError("retirement manifest repository does not match the workflow")
    if manifest.get("deletion_mode") != "complete-packages-after-exact-inventory":
        raise RetirementError("retirement manifest does not authorize complete-package deletion")
    if not manifest.get("recovery_bundle_sha256"):
        raise RetirementError("retirement manifest has no recovery bundle checksum")
    packages = manifest.get("packages")
    if not isinstance(packages, list) or not packages:
        raise RetirementError("retirement manifest has no packages")
    return manifest


def _expected_versions(manifest: dict[str, Any]) -> list[tuple[str, int, str, list[str]]]:
    expected: list[tuple[str, int, str, list[str]]] = []
    seen: set[tuple[str, int]] = set()
    for package in manifest["packages"]:
        if not isinstance(package, dict) or not isinstance(package.get("name"), str):
            raise RetirementError("retirement manifest contains an invalid package")
        name = package["name"]
        versions = package.get("versions")
        if not isinstance(versions, list) or not versions:
            raise RetirementError(f"retirement package {name} has no versions")
        for version in versions:
            if not isinstance(version, dict):
                raise RetirementError(f"retirement package {name} has an invalid version")
            version_id = version.get("id")
            digest = version.get("digest")
            tags = version.get("tags")
            if (
                not isinstance(version_id, int)
                or version_id <= 0
                or not isinstance(digest, str)
                or not digest.startswith("sha256:")
                or not isinstance(tags, list)
                or not all(isinstance(tag, str) for tag in tags)
            ):
                raise RetirementError(f"retirement package {name} has invalid evidence")
            identity = (name, version_id)
            if identity in seen:
                raise RetirementError(f"duplicate retirement version: {name}@{version_id}")
            seen.add(identity)
            expected.append((name, version_id, digest, sorted(tags)))
    return expected


def retire_packages(
    manifest: dict[str, Any], api: GitHubPackagesApi
) -> dict[str, list[str]]:
    owner, _, _ = str(manifest["repository"]).partition("/")
    result: dict[str, list[str]] = {
        "deleted": [],
        "deleted_packages": [],
        "already_absent": [],
    }
    expected = _expected_versions(manifest)
    expected_by_package: dict[str, dict[int, tuple[str, list[str]]]] = {}
    verified_by_package: dict[str, list[int]] = {}
    for package, version_id, digest, tags in expected:
        expected_by_package.setdefault(package, {})[version_id] = (digest, tags)
        identity = f"{package}@{version_id}"
        live = api.version(owner, package, version_id)
        if live is None:
            result["already_absent"].append(identity)
            continue
        live_tags = live.get("metadata", {}).get("container", {}).get("tags")
        if live.get("id") != version_id or live.get("name") != digest:
            raise RetirementError(f"live package identity does not match {identity}")
        if not isinstance(live_tags, list) or sorted(live_tags) != tags:
            raise RetirementError(f"live package tags do not match {identity}")
        verified_by_package.setdefault(package, []).append(version_id)

    # Prove the manifest covers the complete live package inventory before the
    # first package-level deletion. This prevents a newly published or omitted
    # version from being swept up by complete-package retirement.
    for package, expected_versions in expected_by_package.items():
        inventory = api.versions(owner, package)
        inventory_ids: set[int] = set()
        for live in inventory:
            version_id = live.get("id")
            if not isinstance(version_id, int) or version_id not in expected_versions:
                raise RetirementError(
                    f"live package inventory contains an undeclared version: {package}@{version_id}"
                )
            digest, tags = expected_versions[version_id]
            live_tags = live.get("metadata", {}).get("container", {}).get("tags")
            if live.get("name") != digest or not isinstance(live_tags, list):
                raise RetirementError(
                    f"live package inventory does not match {package}@{version_id}"
                )
            if sorted(live_tags) != tags:
                raise RetirementError(
                    f"live package inventory tags do not match {package}@{version_id}"
                )
            inventory_ids.add(version_id)
        if inventory_ids != set(verified_by_package.get(package, [])):
            raise RetirementError(f"package inventory changed during verification: {package}")

    for package in expected_by_package:
        live_ids = verified_by_package.get(package, [])
        if not live_ids:
            continue
        api.delete_package(owner, package)
        result["deleted_packages"].append(package)
        result["deleted"].extend(f"{package}@{version_id}" for version_id in live_ids)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--token", default=os.getenv("GH_TOKEN", ""))
    parser.add_argument("--api-url", default=os.getenv("GITHUB_API_URL", "https://api.github.com"))
    parser.add_argument("--result", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.token:
        raise SystemExit("GH_TOKEN is required")
    try:
        manifest = load_manifest(args.manifest, args.repository)
        result = retire_packages(manifest, GitHubPackagesApi(args.token, args.api_url))
        args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (OSError, RetirementError) as exc:
        failure = {"status": "failed", "error": str(exc)}
        try:
            args.result.write_text(
                json.dumps(failure, indent=2) + "\n", encoding="utf-8"
            )
        except OSError:
            pass
        raise SystemExit(f"OCI package retirement failed: {exc}") from exc
    print(
        f"OCI retirement complete: {len(result['deleted_packages'])} packages and "
        f"{len(result['deleted'])} live versions deleted, "
        f"{len(result['already_absent'])} already absent."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
