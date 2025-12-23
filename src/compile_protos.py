#!/usr/bin/env python3
"""
Protocol buffer compilation script for Marty gRPC services.
"""

import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
PROTO_DIR = PROJECT_ROOT / "proto" / "v1"
OUTPUT_DIR = PROJECT_ROOT / "src" / "proto" / "v1"


def fix_grpc_imports() -> None:
    """Fix import statements in generated gRPC and protobuf files to use relative imports."""
    # Fix imports in gRPC files
    grpc_files = list(OUTPUT_DIR.glob("*_pb2_grpc.py"))
    for grpc_file in grpc_files:
        content = grpc_file.read_text()

        # Replace absolute imports with relative imports for _pb2 modules
        import_lines = []
        for line in content.split("\n"):
            if line.startswith("import ") and "_pb2 as " in line:
                # Convert "import module_pb2 as alias" to "from . import module_pb2 as alias"
                parts = line.split(" as ")
                module_name = parts[0].replace("import ", "")
                alias = parts[1]
                new_line = f"from . import {module_name} as {alias}"
                import_lines.append(new_line)
                logger.info(f"Fixed import in {grpc_file.name}: {line} -> {new_line}")
            else:
                import_lines.append(line)

        # Write back the fixed content
        grpc_file.write_text("\n".join(import_lines))

    logger.info("Fixed imports in %d gRPC files", len(grpc_files))

    # Fix imports in pb2 files
    pb2_files = list(OUTPUT_DIR.glob("*_pb2.py"))
    for pb2_file in pb2_files:
        content = pb2_file.read_text()

        # Replace absolute imports with relative imports for other _pb2 modules
        import_lines = []
        for line in content.split("\n"):
            if line.startswith("import ") and "_pb2 as " in line:
                # Convert "import module_pb2 as alias" to "from . import module_pb2 as alias"
                parts = line.split(" as ")
                module_name = parts[0].replace("import ", "")
                alias = parts[1]
                new_line = f"from . import {module_name} as {alias}"
                import_lines.append(new_line)
                logger.info(f"Fixed import in {pb2_file.name}: {line} -> {new_line}")
            else:
                import_lines.append(line)

        # Write back the fixed content
        pb2_file.write_text("\n".join(import_lines))

    logger.info("Fixed imports in %d pb2 files", len(pb2_files))


def create_init_file() -> None:
    """Create __init__.py file in the proto output directory."""
    init_file = OUTPUT_DIR / "__init__.py"

    pb2_files = list(OUTPUT_DIR.glob("*_pb2.py"))
    grpc_files = list(OUTPUT_DIR.glob("*_pb2_grpc.py"))

    imports = []
    for pb2_file in sorted(pb2_files):
        module_name = pb2_file.stem
        imports.append(f"from . import {module_name}")

    for grpc_file in sorted(grpc_files):
        module_name = grpc_file.stem
        imports.append(f"from . import {module_name}")

    init_content = '"""Generated protobuf modules."""\n\n'
    init_content += "\n".join(imports) + "\n"

    with init_file.open("w", encoding="utf-8") as f:
        f.write(init_content)

    logger.info("Created/updated %s", init_file)


def main() -> bool:
    """Main compilation function."""
    logger.info("Starting protobuf compilation process...")
    logger.info("Project Root: %s", PROJECT_ROOT)
    logger.info("Proto Source Directory: %s", PROTO_DIR)
    logger.info("Output Directory: %s", OUTPUT_DIR)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    proto_files = list(PROTO_DIR.glob("*.proto"))
    if not proto_files:
        logger.warning("No .proto files found in %s", PROTO_DIR)
        return True

    logger.info("Compiling %d proto files...", len(proto_files))

    try:
        import grpc_tools

        grpc_tools_proto_path = str(Path(grpc_tools.__path__[0]) / "_proto")

        cmd = [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"--proto_path={PROTO_DIR}",
            f"--proto_path={grpc_tools_proto_path}",
            f"--python_out={OUTPUT_DIR}",
            f"--grpc_python_out={OUTPUT_DIR}",
            *[str(proto_file) for proto_file in proto_files],
        ]

        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError, ModuleNotFoundError) as e:
        logger.warning("grpc_tools.protoc failed, trying system protoc: %s", e)
    else:
        logger.info("Successfully compiled proto files using grpc_tools.protoc")
        fix_grpc_imports()
        create_init_file()
        return True

    # Fallback to system protoc
    try:
        cmd_python = [
            "protoc",
            f"--proto_path={PROTO_DIR}",
            f"--python_out={OUTPUT_DIR}",
            *[str(proto_file) for proto_file in proto_files],
        ]

        subprocess.run(cmd_python, check=True, capture_output=True, text=True)

        cmd_grpc = [
            "protoc",
            f"--proto_path={PROTO_DIR}",
            f"--grpc_python_out={OUTPUT_DIR}",
            *[str(proto_file) for proto_file in proto_files],
        ]

        try:
            subprocess.run(cmd_grpc, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            logger.warning("gRPC generation failed, only Python protobuf files")

    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        logger.exception("System protoc also failed")
        return False
    else:
        logger.info("Successfully compiled proto files using system protoc")
        fix_grpc_imports()
        create_init_file()
        return True

    return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
