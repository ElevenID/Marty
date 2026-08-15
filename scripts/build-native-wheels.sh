#!/usr/bin/env bash
set -euo pipefail

core_directory="${1:-marty-core}"
destination="${2:-native-wheels}"

if [ ! -f "$core_directory/Cargo.toml" ]; then
  echo "Marty Core checkout not found at $core_directory" >&2
  exit 1
fi

mkdir -p "$destination"

python -m pip install --upgrade pip
python -m pip install 'maturin[patchelf]==1.14.1'

maturin build --release --compatibility off \
  --manifest-path "$core_directory/marty-bindings/Cargo.toml" \
  --out "$destination"
maturin build --release --compatibility off \
  --manifest-path "$core_directory/marty-verification/Cargo.toml" \
  --features 'pyo3/extension-module,python,csca,eudi,cert-builder' \
  --out "$destination"
maturin build --release --compatibility off \
  --manifest-path "$core_directory/marty-iso18013/Cargo.toml" \
  --out "$destination"

require_one_wheel() {
  local package="$1"
  shopt -s nullglob
  local matches=("$destination"/${package}-*.whl)
  shopt -u nullglob
  if [ "${#matches[@]}" -ne 1 ]; then
    echo "Expected exactly one $package wheel, found ${#matches[@]}" >&2
    exit 1
  fi
}

require_one_wheel marty_rs
require_one_wheel marty_verification_py
require_one_wheel marty_iso18013
