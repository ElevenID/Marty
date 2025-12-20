#!/bin/bash
# Docker Test Runner for Document Processing API

set -e

echo "🐳 Running Document Processing API Tests in Docker"
echo "=================================================="

# Function to wait for service to be ready
wait_for_service() {
    echo "⏳ Waiting for service to be ready..."
    max_attempts=30
    attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -s -f http://localhost:8080/api/ping > /dev/null; then
            echo "✅ Service is ready!"
            return 0
        fi
        echo "Attempt $attempt/$max_attempts: Service not ready yet..."
        sleep 2
        attempt=$((attempt + 1))
    done

    echo "❌ Service failed to start within timeout"
    return 1
}

# Function to run tests
run_tests() {
    echo "🧪 Running tests..."

    # Run unit tests
    echo "Running unit tests..."
    python -m pytest tests/unit/ -v --tb=short || return 1

    # Run API verification
    echo "Running API verification..."
    python scripts/verify_api.py || return 1

    # Run E2E tests
    echo "Running E2E tests..."
    python scripts/test_e2e_enhanced.py || return 1

    echo "✅ All tests passed!"
}

# Main execution
if wait_for_service; then
    run_tests
    echo "🎉 Docker tests completed successfully!"
else
    echo "❌ Docker tests failed!"
    exit 1
fi
