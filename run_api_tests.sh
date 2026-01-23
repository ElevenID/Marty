#!/bin/bash
# Quick script to run API integration tests

echo "🧪 Marty API Integration Tests"
echo "================================"
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "❌ pytest not found. Installing dependencies..."
    pip install pytest pytest-asyncio httpx respx sqlalchemy[asyncio] aiosqlite
fi

# Parse command line arguments
VERBOSE=""
FILTER=""
SPECIFIC=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose)
            VERBOSE="-v"
            shift
            ;;
        -vv|--very-verbose)
            VERBOSE="-vv"
            shift
            ;;
        -k)
            FILTER="-k $2"
            shift 2
            ;;
        -s|--specific)
            SPECIFIC="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Run tests
if [ -n "$SPECIFIC" ]; then
    echo "Running specific test: $SPECIFIC"
    pytest "tests/api/$SPECIFIC" $VERBOSE
elif [ -n "$FILTER" ]; then
    echo "Running filtered tests: $FILTER"
    pytest tests/api/ -m api_integration $FILTER $VERBOSE
else
    echo "Running all API integration tests..."
    pytest tests/api/ -m api_integration $VERBOSE
fi

echo ""
echo "✅ Test run complete!"
