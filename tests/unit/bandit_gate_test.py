"""Execute the real scanner and maintained hook against clean and hostile inputs."""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="Dedicated Bandit CI installs uv")


@pytest.fixture
def scanner():
    spec = importlib.util.spec_from_file_location("bandit_gate_scanner", ROOT / "scripts/security_scan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def repository(tmp_path):
    shutil.copyfile(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    for directory in ("src", "packages/marty-common/marty_common", "scripts"):
        path = tmp_path / directory
        path.mkdir(parents=True)
        (path / "probe.py").write_text("answer = 42\n", encoding="utf-8")
    return tmp_path


def test_real_clean_scan_and_ephemeral_cleanup(scanner, repository, monkeypatch):
    temporary = scanner.tempfile.TemporaryDirectory
    directories = []

    def record_directory(*args, **kwargs):
        result = temporary(*args, **kwargs)
        directories.append(Path(result.name))
        return result

    monkeypatch.setattr(scanner.tempfile, "TemporaryDirectory", record_directory)
    assert scanner.main(["code", "--ephemeral"], root=repository) == 0
    assert directories and all(not path.exists() for path in directories)
    assert not (repository / "reports").exists()


@pytest.mark.parametrize("directory", ["src", "packages/marty-common/marty_common", "scripts"])
def test_each_source_root_rejects_a_real_tls_finding(scanner, repository, directory, capsys):
    (repository / directory / "probe.py").write_text(
        "import requests\nrequests.get('https://example.invalid', verify=False, timeout=1)\n",
        encoding="utf-8",
    )
    assert scanner.main(["code", "--ephemeral"], root=repository) == 1
    assert "B501" in capsys.readouterr().out


@pytest.mark.parametrize("code,rule", [
    ("listen = '0.0.0.0'\n", "B104"),
    ("password = 'unreviewed-password'\n", "B105"),
    ("try:\n    int('bad')\nexcept Exception:\n    pass\n", "B110"),
    ("import pickle\npickle.loads(b'bad')\n", "B301"),
    ("eval(input())\n", "B307"),
    ("import hashlib\nhashlib.md5(b'bad')\n", "B324"),
    ("assert False\n", "B101"),
    ("login(password='unreviewed-password')\n", "B106"),
    ("cache = '/tmp/unreviewed'\n", "B108"),
    ("for item in range(2):\n    try:\n        int('bad')\n    except Exception:\n        continue\n", "B112"),
    ("import random\nrandom.randint(0, 10)\n", "B311"),
    ("import pickle\n", "B403"),
    ("import subprocess\n", "B404"),
    ("import subprocess\nsubprocess.run([input()])\n", "B603"),
    ("import subprocess\nsubprocess.run(['git'])\n", "B607"),
])
def test_reviewed_local_exceptions_do_not_disable_rules(scanner, repository, code, rule, capsys):
    (repository / "src/probe.py").write_text(code, encoding="utf-8")
    assert scanner.main(["code", "--ephemeral"], root=repository) == 1
    output = capsys.readouterr().out
    assert rule in output
    assert "unreviewed-password" not in output


def test_syntax_error_fails_even_when_bandit_itself_returns_zero(scanner, repository, capsys):
    (repository / "src/probe.py").write_text("def broken(:\n", encoding="utf-8")
    assert scanner.main(["code", "--ephemeral"], root=repository) == 2
    assert "syntax error" in capsys.readouterr().out


@pytest.mark.parametrize("missing", [False, True])
def test_empty_or_missing_source_root_cannot_pass(scanner, repository, missing):
    path = repository / "src/probe.py"
    path.unlink()
    if missing:
        path.parent.rmdir()
    assert scanner.main(["code", "--ephemeral"], root=repository) == 2


def test_nonempty_but_partial_report_cannot_pass(scanner, repository):
    report = repository / "partial.json"
    report.write_text(json.dumps({
        "errors": [], "results": [],
        "metrics": {"_totals": {"loc": 1}, "src/probe.py": {"loc": 1}},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="omitted"):
        scanner.classify("bandit", 0, "", report, root=repository)


@pytest.mark.parametrize("content,expected,selected", [
    ("answer = 42\n", 0, None),
    ("password = 'unreviewed-password'\n", 1, None),
    ("def broken(:\n", 1, None),
    ("def broken(:\n", 1, "pyproject.toml"),
    ("def broken(:\n", 1, ".pre-commit-config.yaml"),
    ("password = 'unreviewed-password'\n", 1, "scripts/probe.py"),
])
def test_actual_precommit_hook_uses_fail_closed_runner(repository, content, expected, selected):
    pytest.importorskip("pre_commit")
    yaml = pytest.importorskip("yaml")
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hook = next(h for repo in config["repos"] for h in repo["hooks"] if h["id"] == "bandit")
    (repository / ".pre-commit-config.yaml").write_text(
        yaml.safe_dump({"repos": [{"repo": "local", "hooks": [hook]}]}), encoding="utf-8",
    )
    shutil.copyfile(ROOT / "scripts/security_scan.py", repository / "scripts/security_scan.py")
    path = "scripts/probe.py" if selected == "scripts/probe.py" else "src/probe.py"
    (repository / path).write_text(content, encoding="utf-8")
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    result = subprocess.run(
        [sys.executable, "-m", "pre_commit", "run", "bandit",
         *(["--files", selected] if selected else ["--all-files"])],
        cwd=repository, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    if "broken" in content:
        assert "syntax error" in result.stdout
