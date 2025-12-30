#!/bin/bash
# End-to-End Testing Strategy for Marty UI

# This script provides a comprehensive testing strategy that ensures proper ser    echo "🧯 Cleaning up services..."
    docker-compose -f docker/docker-compose.yml down --volumes --remove-orphansce setup
# and realistic test expectations for the current UI implementation.

set -e

echo "🚀 Setting up E2E testing environment for Marty UI..."

# Function to check if a service is running on a given port
check_service() {
    local port=$1
    local service_name=$2

    if nc -z localhost $port 2>/dev/null; then
        echo "✅ $service_name is running on port $port"
        return 0
    else
        echo "❌ $service_name is not running on port $port"
        return 1
    fi
}

# Function to start services using docker-compose
start_services() {
    echo "🔧 Starting required backend services..."

    # Start core services that UI depends on
    docker-compose -f docker/docker-compose.yml up -d postgres

    # Wait for postgres to be ready
    echo "⏳ Waiting for PostgreSQL to be ready..."
    timeout=30
    while ! docker-compose -f docker/docker-compose.yml exec -T postgres pg_isready -U martyuser -d martydb >/dev/null 2>&1; do
        sleep 1
        timeout=$((timeout - 1))
        if [ $timeout -le 0 ]; then
            echo "❌ PostgreSQL failed to start within 30 seconds"
            exit 1
        fi
    done
    echo "✅ PostgreSQL is ready"

    # Start services in dependency order
    echo "🔧 Starting trust-anchor service..."
    docker-compose -f docker/docker-compose.yml up -d trust-anchor

    echo "🔧 Starting CSCA service..."
    docker-compose -f docker/docker-compose.yml up -d csca-service

    echo "🔧 Starting document signer..."
    docker-compose -f docker/docker-compose.yml up -d document-signer

    echo "🔧 Starting inspection system..."
    docker-compose -f docker/docker-compose.yml up -d inspection-system

    echo "🔧 Starting passport engine..."
    docker-compose -f docker/docker-compose.yml up -d passport-engine

    echo "🔧 Starting MDL engine..."
    docker-compose -f docker/docker-compose.yml up -d mdl-engine

    echo "🔧 Starting mDoc engine..."
    docker-compose -f docker/docker-compose.yml up -d mdoc-engine

    echo "🔧 Starting DTC engine..."
    docker-compose -f docker/docker-compose.yml up -d dtc-engine

    echo "🔧 Starting Open Badges service..."
    docker-compose -f docker/docker-compose.yml up -d open-badges

    # Wait for all services to be healthy
    echo "⏳ Waiting for services to be healthy..."
    sleep 30

    # Check service health
    services_ready=true
    check_service 8080 "Trust Anchor" || services_ready=false
    check_service 8081 "CSCA Service" || services_ready=false
    check_service 8082 "Document Signer" || services_ready=false
    check_service 8083 "Inspection System" || services_ready=false
    check_service 8084 "Passport Engine" || services_ready=false
    check_service 8085 "MDL Engine" || services_ready=false
    check_service 8086 "mDoc Engine" || services_ready=false
    check_service 8087 "DTC Engine" || services_ready=false
    check_service 8091 "Open Badges Service" || services_ready=false

    if [ "$services_ready" = true ]; then
        echo "✅ All services are running and healthy"
    else
        echo "⚠️  Some services are not ready. Tests may run in mock mode."
    fi
}

# Function to run tests with different strategies
run_tests() {
    local test_mode=$1

    case $test_mode in
        "smoke")
            echo "🧪 Running smoke tests (basic UI functionality)..."
            uv run pytest tests/ui/test_smoke.py -v
            ;;
        "integration")
            echo "🧪 Running integration tests with live services..."
            export UI_ENABLE_MOCK_DATA=false
            export UI_PASSPORT_ENGINE_ADDR=localhost:8084
            export UI_INSPECTION_SYSTEM_ADDR=localhost:8083
            export UI_MDL_ENGINE_ADDR=localhost:8085
            export UI_TRUST_ANCHOR_ADDR=localhost:8080
            uv run pytest tests/ui/test_new_ui_e2e.py -v --tb=short -k "not test_advanced"
            ;;
        "mock")
            echo "🧪 Running tests in mock mode (no service dependencies)..."
            export UI_ENABLE_MOCK_DATA=true
            export UI_PASSPORT_ENGINE_ADDR=mock
            export UI_INSPECTION_SYSTEM_ADDR=mock
            export UI_MDL_ENGINE_ADDR=mock
            export UI_TRUST_ANCHOR_ADDR=mock
            uv run pytest tests/ui/test_smoke.py -v
            ;;
        "full")
            echo "🧪 Running full test suite..."
            # Start with smoke tests
            run_tests "smoke"
            # Then integration tests
            run_tests "integration"
            ;;
        *)
            echo "❌ Unknown test mode: $test_mode"
            echo "Available modes: smoke, integration, mock, full"
            exit 1
            ;;
    esac
}

# Function to clean up services
cleanup_services() {
    echo "🧹 Cleaning up services..."
    docker-compose down --volumes --remove-orphans
}

# Main execution
case "${1:-help}" in
    "start-services")
        start_services
        ;;
    "test-smoke")
        run_tests "smoke"
        ;;
    "test-integration")
        start_services
        run_tests "integration"
        ;;
    "test-mock")
        run_tests "mock"
        ;;
    "test-full")
        start_services
        run_tests "full"
        cleanup_services
        ;;
    "cleanup")
        cleanup_services
        ;;
    "help"|*)
        echo "Marty UI E2E Testing Strategy"
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  start-services     Start all backend services"
        echo "  test-smoke         Run smoke tests only"
        echo "  test-integration   Start services and run integration tests"
        echo "  test-mock          Run tests in mock mode (no service dependencies)"
        echo "  test-full          Run complete test suite with cleanup"
        echo "  cleanup            Stop and remove all services"
        echo "  help               Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0 test-smoke                    # Quick smoke tests"
        echo "  $0 test-integration             # Full integration testing"
        echo "  $0 test-mock                    # Test without backend services"
        echo "  $0 test-full                    # Complete test suite"
        ;;
esac
