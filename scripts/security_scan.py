#!/usr/bin/env python3
"""Run explicitly selected security checks without treating missing scans as passes."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    "code": ("bandit",),
    "deps": ("pip-audit",),
    "secrets": ("detect-secrets",),
    "containers": ("syft", "grype"),
}
OPTIONAL = {
    "code": ("semgrep",),
    "deps": ("safety",),
    "secrets": ("trufflehog", "git-secrets"),
    "containers": ("hadolint",),
}


def bandit_command(root: Path, output: Path) -> list[str]:
    """Use the maintained hook's exact version, source scope and rule selection."""
    import yaml

    config = yaml.safe_load((root / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    repository = next(r for r in config["repos"] if r["repo"] == "https://github.com/PyCQA/bandit")
    hook = next(h for h in repository["hooks"] if h["id"] == "bandit")
    return ["uv", "run", "--no-project", "--with", f"bandit=={repository['rev']}",
            "bandit", *hook["args"], "-f", "json", "-o", str(output)]


def command_for(tool: str, root: Path, output: Path, args) -> list[str]:
    if tool == "bandit":
        return bandit_command(root, output)
    if tool == "pip-audit":
        # Audit the installed project environment, not a freshly created tool-only venv.
        if not any(_installed(name) for name in ("marty-identity-compat", "marty-common")):
            raise ValueError("Install the current project in this interpreter before dependency auditing")
        return [sys.executable, "-m", "pip_audit", "--format=json"]
    if tool == "safety":
        return ["safety", "check", "--json"]
    if tool == "semgrep":
        return ["semgrep", "scan", "--config=auto", "--json", "--error",
                "src", "packages/marty-common/marty_common"]
    if tool == "detect-secrets":
        # No baseline is silently created or approved; scan tracked files locally.
        return ["detect-secrets", "scan", "--no-verify"]
    if tool == "trufflehog":
        return ["trufflehog", "filesystem", str(root), "--json", "--fail",
                "--no-update", "--no-verification"]
    if tool == "git-secrets":
        return ["git", "secrets", "--scan"]
    if tool == "hadolint":
        if not args.dockerfile:
            raise ValueError("hadolint requires explicit --dockerfile paths")
        paths = [(root / path).resolve() for path in args.dockerfile]
        if not all(path.is_file() for path in paths):
            raise ValueError("Every --dockerfile path must identify an existing file")
        return ["hadolint", "--format", "json", *map(str, paths)]
    if args.image:
        target = args.image
        if not re.fullmatch(r"(?:[^\s@-][^\s@]*@)?sha256:[0-9a-fA-F]{64}", target):
            raise ValueError("Supply a digest-pinned --image, or use --filesystem explicitly")
    elif args.filesystem:
        directory = Path(args.filesystem).resolve()
        if not directory.is_dir():
            raise ValueError("Filesystem scan directory does not exist")
        target = "dir:" + str(directory)
    else:
        raise ValueError("Container checks require --image or --filesystem; no local images are auto-selected")
    return [tool, target, "-o", "spdx-json" if tool == "syft" else "json"]


def _installed(name: str) -> bool:
    try:
        importlib.metadata.distribution(name)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


def classify(tool: str, returncode: int, stdout: str, report: Path) -> str:
    """Require a recognizable result; malformed output and scan errors are incomplete."""
    if tool == "git-secrets":
        return "passed" if returncode == 0 else "error"
    if tool == "trufflehog":
        if returncode not in (0, 183):
            return "error"
        rows = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        if returncode == 183 and not rows:
            return "error"
        return "findings" if rows else "passed"
    data = json.loads(report.read_text(encoding="utf-8") if tool == "bandit" else stdout)
    if tool == "bandit":
        if returncode not in (0, 1) or data["errors"] or not data["metrics"].get("_totals", {}).get("loc"):
            return "error"
        findings = data["results"]
    elif tool == "pip-audit":
        if returncode not in (0, 1) or not data["dependencies"] or any(d.get("skip_reason") for d in data["dependencies"]):
            return "error"
        findings = [v for dependency in data["dependencies"] for v in dependency["vulns"]]
    elif tool == "detect-secrets":
        if returncode != 0:
            return "error"
        findings = [finding for values in data["results"].values() for finding in values]
    elif tool == "semgrep":
        if returncode not in (0, 1) or data["errors"] or not data["paths"]["scanned"]:
            return "error"
        findings = data["results"]
    elif tool == "grype":
        if returncode != 0 or not data.get("source"):
            return "error"
        findings = data["matches"]
    elif tool == "syft":
        return "passed" if returncode == 0 and data.get("spdxVersion") and "packages" in data else "error"
    elif tool == "hadolint":
        if returncode not in (0, 1) or not isinstance(data, list):
            return "error"
        findings = data
    else:  # Safety JSON formats vary; never convert an unrecognized result into a pass.
        if returncode not in (0, 64) or not isinstance(data, dict):
            return "error"
        findings = data["vulnerabilities"]
    if not isinstance(findings, list):
        return "error"
    if returncode and not findings:
        return "error"
    return "findings" if findings else "passed"


def run_check(tool: str, args, root: Path, directory: Path) -> dict:
    report = directory / f"{tool}.json"
    result = {"tool": tool, "status": "error"}
    try:
        command = command_for(tool, root, report, args)
        if shutil.which(command[0]) is None:
            result.update(status="unavailable", reason=f"Required executable unavailable: {command[0]}")
            return result
        if tool == "git-secrets":
            policy = subprocess.run(["git", "config", "--get-all", "secrets.patterns"],
                                    cwd=root, capture_output=True, text=True, encoding="utf-8",
                                    errors="replace", timeout=args.timeout, check=False)
            if policy.returncode != 0 or not policy.stdout.strip():
                result["reason"] = "git-secrets requires configured prohibited patterns"
                return result
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=args.timeout, check=False)
        (directory / f"{tool}.stdout").write_text(completed.stdout, encoding="utf-8")
        (directory / f"{tool}.stderr").write_text(completed.stderr, encoding="utf-8")
        result.update(returncode=completed.returncode,
                      status=classify(tool, completed.returncode, completed.stdout, report))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration, ImportError, subprocess.TimeoutExpired) as exc:
        result["reason"] = f"{type(exc).__name__}: {exc}"
    return result


def main(argv=None, *, root: Path = ROOT) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["help"]:
        argv = ["--help"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="full",
                        choices=["full", "code", "deps", "dependencies", "secrets", "containers", "compliance"])
    parser.add_argument("--tool", action="append", choices=sorted({t for ts in [*GROUPS.values(), *OPTIONAL.values()] for t in ts}))
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--image")
    target.add_argument("--filesystem")
    parser.add_argument("--dockerfile", action="append")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    action = "deps" if args.action == "dependencies" else args.action
    groups = list(GROUPS) if action == "full" else [action]
    allowed = {tool for group in groups for tool in GROUPS.get(group, ()) + OPTIONAL.get(group, ())}
    if args.tool and not set(args.tool).issubset(allowed):
        parser.error("Selected tool does not belong to this action")
    tools = list(dict.fromkeys(args.tool or [tool for group in groups for tool in GROUPS.get(group, ())]))
    directory = args.output_dir or root / "reports/generated/security" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    )
    directory = directory.resolve()
    # A new directory prevents stale output from being interpreted as a new scan.
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        parser.error(f"Cannot create a fresh report directory: {exc}")
    results = [run_check(tool, args, root, directory) for tool in tools]
    if action == "compliance":
        results.append({"tool": "compliance", "status": "manual",
                        "reason": "Source counts are not compliance evidence; see docs/SECURITY.md"})
    exit_code = (2 if any(r["status"] not in {"passed", "findings"} for r in results)
                 else 1 if any(r["status"] == "findings" for r in results) else 0)
    (directory / "summary.json").write_text(json.dumps({
        "action": action, "selected_checks": tools, "results": results, "exit_code": exit_code,
        "scope": "Selected automated checks only; not compliance or release qualification",
    }, indent=2) + "\n", encoding="utf-8")
    for result in results:
        print(f"{result['tool']}: {result['status']}")
    print(f"Reports: {directory}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
