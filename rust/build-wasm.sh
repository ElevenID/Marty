#!/bin/bash
# Build script for marty-rs WASM target
# Outputs to marty-authenticator/local_wasm_overrides/marty_rs/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUST_DIR="$SCRIPT_DIR"
OUTPUT_DIR="$SCRIPT_DIR/../../marty-authenticator/local_wasm_overrides/marty_rs"

echo "Building marty-rs WASM..."

# Navigate to the marty-rs crate
cd "$RUST_DIR/marty-rs"

# Check if wasm-pack is installed
if ! command -v wasm-pack &> /dev/null; then
    echo "wasm-pack not found. Installing..."
    cargo install wasm-pack
fi

# Build for web target with wasm feature, excluding python
wasm-pack build \
    --target web \
    --no-default-features \
    --features wasm \
    --release

# Copy to output directory
echo "Copying to $OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"
cp -r pkg/* "$OUTPUT_DIR/"

# Clean up unnecessary files
rm -f "$OUTPUT_DIR/.gitignore"

echo "WASM build complete!"
echo "Output: $OUTPUT_DIR"

# List output files
echo ""
echo "Generated files:"
ls -la "$OUTPUT_DIR"
