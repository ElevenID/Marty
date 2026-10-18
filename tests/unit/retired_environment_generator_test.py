"""Retired deployment generation must never emit misleading configuration."""

import os
import subprocess
import sys

import pytest

from marty_common.config.dry_env_generator import (
    EnvironmentConfigGenerator,
    EnvironmentGenerationRetiredError,
)


@pytest.mark.parametrize("method,args", [
    ("generate_service_env_vars", ("production",)),
    ("generate_docker_compose_config", ("production",)),
    ("generate_k8s_service_manifests", ("customer",)),
    ("write_env_file", ("production",)),
])
def test_retired_generation_rejects_without_output(method, args, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(EnvironmentGenerationRetiredError, match="marty-deploy.sh validate"):
        getattr(EnvironmentConfigGenerator(), method)(*args)
    assert list(tmp_path.iterdir()) == []


def test_retired_writer_preserves_existing_configuration(tmp_path):
    target = tmp_path / ".env.production"
    target.write_text("OPERATOR_VALUE=keep\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="generation is retired"):
        EnvironmentConfigGenerator.write_env_file("production", target)
    assert target.read_text(encoding="utf-8") == "OPERATOR_VALUE=keep\n"


@pytest.mark.parametrize("format", ["env", "docker-compose", "k8s"])
def test_retired_cli_exits_nonzero_without_creating_directory(format, tmp_path):
    output = tmp_path / "generated"
    result = subprocess.run(
        [sys.executable, "-m", "marty_common.config.dry_env_generator", "production",
         "--format", format, "--output-dir", str(output)],
        cwd=tmp_path, env=os.environ.copy(), capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert "Python deployment generation is retired" in result.stderr
    assert "marty-deploy.sh validate" in result.stderr
    assert not output.exists()
