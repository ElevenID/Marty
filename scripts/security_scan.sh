#!/usr/bin/env bash
# Compatibility entry point; the portable runner owns selection and exit status.
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${PYTHON:-python3}" "$script_dir/security_scan.py" "$@"
