#!/bin/bash
# setup_environment.sh - Script to set up development environment for Marty

set -e

echo "Setting up Marty development environment..."

# Check if UV is installed
if ! command -v uv &> /dev/null; then
    echo "Installing UV package manager..."
    pip install uv
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    uv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
if [[ "$OSTYPE" == "darwin"* ]] || [[ "$OSTYPE" == "linux-gnu"* ]]; then
    source .venv/bin/activate
elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
    source .venv/Scripts/activate
fi

# Install dependencies
echo "Installing project dependencies..."
uv pip install -e .

# Compile protobuf files
echo "Compiling protobuf files..."
python -m src.compile_protos

# Create necessary directories
echo "Creating necessary directories if they don't exist..."
mkdir -p logs
mkdir -p data/csca
mkdir -p data/ds
mkdir -p data/passport
mkdir -p data/inspection
mkdir -p data/trust

echo "Environment setup complete!"
echo "Run 'uv run pytest' to validate the retained compatibility package."
echo "Deploy supported Rust services from the marty-ui release artifacts."
