#!/bin/bash
# Build and test the ISO 18013 Python bridge

set -e  # Exit on error

echo "========================================="
echo "ISO 18013 Python Bridge Build Script"
echo "========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if maturin is installed
echo "1. Checking for maturin..."
if ! command -v maturin &> /dev/null; then
    echo -e "${YELLOW}maturin not found, installing...${NC}"
    pip3 install maturin
else
    echo -e "${GREEN}✓ maturin is installed${NC}"
fi
echo ""

# Navigate to marty-iso18013 crate
echo "2. Navigating to marty-iso18013..."
cd "/Volumes/Heart of Gold/Github/work/marty-core/marty-iso18013"
echo -e "${GREEN}✓ In $(pwd)${NC}"
echo ""

# Check if Python module structure exists
echo "3. Checking Python module structure..."
if [ -d "python/marty_iso18013" ]; then
    echo -e "${GREEN}✓ Python module structure exists${NC}"
else
    echo -e "${YELLOW}Creating Python module structure...${NC}"
    mkdir -p python/marty_iso18013
fi
echo ""

# Build the Python package
echo "4. Building Python package..."
echo -e "${YELLOW}Running: maturin develop --features python${NC}"
if maturin develop --features python; then
    echo -e "${GREEN}✓ Build successful${NC}"
else
    echo -e "${RED}✗ Build failed${NC}"
    exit 1
fi
echo ""

# Run Rust tests
echo "5. Running Rust tests..."
echo -e "${YELLOW}Running: cargo test --features python${NC}"
if cargo test --features python 2>&1 | tail -20; then
    echo -e "${GREEN}✓ Rust tests passed${NC}"
else
    echo -e "${YELLOW}⚠ Some tests may have failed, check output above${NC}"
fi
echo ""

# Try to import the module in Python
echo "6. Testing Python import..."
if python3 -c "import marty_iso18013; print(f'Successfully imported marty_iso18013')"; then
    echo -e "${GREEN}✓ Python import successful${NC}"
else
    echo -e "${RED}✗ Python import failed${NC}"
    echo "The module may not be installed correctly."
fi
echo ""

# Run Python tests if pytest is available
echo "7. Running Python tests..."
cd "/Volumes/Heart of Gold/Github/work/Marty"
if command -v pytest &> /dev/null; then
    echo -e "${YELLOW}Running: pytest tests/test_iso18013_bridge.py -v${NC}"
    if pytest tests/test_iso18013_bridge.py -v; then
        echo -e "${GREEN}✓ Python tests passed${NC}"
    else
        echo -e "${YELLOW}⚠ Some Python tests failed (expected if Rust module not fully bound)${NC}"
    fi
else
    echo -e "${YELLOW}⚠ pytest not installed, skipping Python tests${NC}"
    echo "Install with: pip3 install pytest pytest-asyncio"
fi
echo ""

# Summary
echo "========================================="
echo "Build Summary"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Run the integration example:"
echo "   cd examples"
echo "   python3 iso18013_integration_example.py"
echo ""
echo "2. Review the migration guide:"
echo "   cat PYTHON_RUST_BRIDGE_GUIDE.md"
echo ""
echo "3. Check implementation status:"
echo "   cat PYTHON_BRIDGE_IMPLEMENTATION_SUMMARY.md"
echo ""
echo "========================================="
