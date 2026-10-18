"""Retirement shim for the obsolete Python deployment generator.

The module and public call signatures remain importable for existing callers.
No legacy environment, Compose, or Kubernetes output is generated.
"""

from pathlib import Path
from typing import Any, NoReturn


_RETIREMENT = (
    "Python deployment generation is retired: its service paths and defaults "
    "do not describe the Rust runtime. Use the marty-ui deployment catalog and "
    "`sh scripts/marty-deploy.sh validate` / `plan <stack>` in that checkout. "
    "Migration and output limitations: "
    "https://github.com/ElevenID/Marty/blob/main/docs/features/compatibility-tooling-ownership.md"
)


class EnvironmentGenerationRetiredError(RuntimeError):
    """The retired generator cannot produce supported deployment configuration."""


def _retired() -> NoReturn:
    raise EnvironmentGenerationRetiredError(_RETIREMENT)


class EnvironmentConfigGenerator:
    """Import-compatible rejection of unsupported legacy deployment generation."""

    @classmethod
    def generate_service_env_vars(cls, environment: str = "development") -> dict[str, str]:
        _retired()

    @classmethod
    def generate_docker_compose_config(cls, environment: str = "development") -> dict[str, Any]:
        _retired()

    @classmethod
    def generate_k8s_service_manifests(cls, namespace: str = "marty") -> dict[str, dict[str, Any]]:
        _retired()

    @classmethod
    def write_env_file(cls, environment: str, output_path: Path | None = None) -> Path:
        _retired()


def main():
    """Reject the former CLI without creating deployment files."""
    raise SystemExit(_RETIREMENT)


if __name__ == "__main__":
    main()
