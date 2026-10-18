"""Offline fixture generation must not claim an unsupported trust-store import."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/generate_synthetic_data.py"


def run_generator(output, *arguments):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(output), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=45,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


@pytest.mark.parametrize("arguments", [("--database-insert",), ("--database-insert", "--master-list-only")])
def test_database_mode_rejects_before_creating_output(tmp_path, arguments):
    output = tmp_path / "must-not-exist"
    result = run_generator(output, *arguments)
    assert result.returncode != 0
    assert not output.exists()
    assert "Data inserted" not in result.stdout
    assert "unsupported" in result.stderr or "mutually exclusive" in result.stderr
    if len(arguments) == 1:
        assert result.returncode == 2
        assert "Rust-owned trust import" in result.stderr


def test_programmatic_database_mode_rejects_before_creating_output(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", sys.path.copy())
    spec = importlib.util.spec_from_file_location("synthetic_generator_probe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="Rust-owned trust import"):
        module.SyntheticDataGenerator(output, database_insert=True)
    assert not output.exists()


@pytest.mark.parametrize("master_only", [False, True])
def test_offline_modes_still_write_fixture_datasets(tmp_path, master_only):
    output = tmp_path / "offline"
    arguments = ["--countries", "1", "--passports", "1", "--mdl", "1", "--mdoc", "1", "--dtc", "1"]
    if master_only:
        arguments.append("--master-list-only")
    result = run_generator(output, *arguments)
    assert result.returncode == 0, result.stderr
    assert "Data inserted" not in result.stdout
    data = json.loads((output / "synthetic_test_data.json").read_text(encoding="utf-8"))
    assert (output / "data_summary.json").is_file()
    if master_only:
        assert len(data["masterLists"]) == 1
        assert (output / "master_lists.json").is_file()
    else:
        assert len(data["passports"]) == 1
        assert all(len(data["credentials"][name]) == 1 for name in ("mdl", "mdoc", "dtc"))
