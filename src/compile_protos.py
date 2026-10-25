#!/usr/bin/env python3
"""Compile the canonical protobuf implementation and legacy import aliases."""

import logging
import re
import subprocess  # nosec B404 -- Reviewed tool invocations below use argv without a shell.
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROTO_DIR = PROJECT_ROOT / "proto" / "v1"
OUTPUT_DIR = PROJECT_ROOT / "src" / "marty_plugin" / "proto" / "v1"
COMPAT_DIR = PROJECT_ROOT / "src" / "proto" / "v1"


def finalize_modules() -> None:
    """Use package-relative imports and retain both shipped module namespaces."""
    modules = sorted(OUTPUT_DIR.glob("*_pb2*.py"))
    COMPAT_DIR.mkdir(parents=True, exist_ok=True)
    for module in modules:
        content = re.sub(
            r"^import (\w+_pb2) as (\w+)$",
            r"from . import \1 as \2",
            module.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
        # Generated message classes must remain pickleable after package install.
        if module.name.endswith("_pb2.py"):
            content = content.replace(
                f"'{module.stem}', _globals",
                f"'marty_plugin.proto.v1.{module.stem}', _globals",
            )
        module.write_text(content, encoding="utf-8", newline="\n")
        alias = (
            '"""Compatibility alias; implementation lives in marty_plugin.proto.v1."""\n'
            "from importlib import import_module\n"
            "import sys\n\n"
            f'sys.modules[__name__] = import_module("marty_plugin.proto.v1.{module.stem}")\n'
        )
        (COMPAT_DIR / module.name).write_text(alias, encoding="utf-8", newline="\n")
    init = '"""Protobuf modules; regenerate with src/compile_protos.py."""\n\n'
    init += "".join(f"from . import {module.stem}\n" for module in modules)
    for directory in (OUTPUT_DIR, COMPAT_DIR):
        (directory / "__init__.py").write_text(init, encoding="utf-8", newline="\n")


def main() -> bool:
    """Generate Python messages and gRPC bindings together, failing on errors."""
    try:
        import grpc_tools

        files = sorted(PROTO_DIR.glob("*.proto"))
        if not files:
            logger.error("No protocol definitions found in %s", PROTO_DIR)
            return False
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(  # nosec B603 -- Validated compiler/scanner argv; shell is disabled.
            [
                sys.executable, "-m", "grpc_tools.protoc",
                f"--proto_path={PROTO_DIR}",
                f"--proto_path={Path(grpc_tools.__path__[0]) / '_proto'}",
                f"--python_out={OUTPUT_DIR}",
                f"--grpc_python_out={OUTPUT_DIR}",
                *map(str, files),
            ],
            check=True,
        )
        finalize_modules()
    except (ImportError, OSError, subprocess.CalledProcessError):
        logger.exception("Protocol generation failed; install grpcio-tools==1.76.0")
        return False
    return True


def compile_all_protos() -> None:
    """Checkout command: successful generation exits with status zero."""
    if not main():
        raise SystemExit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    compile_all_protos()
