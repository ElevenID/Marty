# Makefile for Document Processing API
# =====================================

# Configuration
SERVICE_NAME := document-processing
SERVICE_PORT := 8080
SERVICE_HOST := localhost
BASE_URL := http://$(SERVICE_HOST):$(SERVICE_PORT)

# Detect if UV is available, fallback to python
UV := $(shell command -v uv 2> /dev/null)
ifdef UV
    PYTHON := uv run python
    PIP := uv pip
    PYTEST := uv run pytest
else
    PYTHON := python
    PIP := pip
    PYTEST := pytest
endif

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[0;33m
BLUE := \033[0;34m
PURPLE := \033[0;35m
CYAN := \033[0;36m
WHITE := \033[0;37m
NC := \033[0m # No Color

# Default target
.PHONY: help
help:
	@echo "$(CYAN)Document Processing API - Test Interface$(NC)"
	@echo "==========================================="
	@echo ""
	@echo "$(GREEN)🧪 Testing:$(NC)"
	@echo "  test                 - Run all tests (unit + integration + e2e)"
	@echo "  test-unit            - Run unit tests"
	@echo "  test-integration     - Run integration tests"
	@echo "  test-e2e             - Run end-to-end tests"
	@echo "  test-api             - Test live API endpoints"
	@echo "  test-health          - Test health endpoints"
	@echo "  test-coverage        - Run tests with coverage report"
	@echo ""
	@echo "$(BLUE)🐳 Docker Testing:$(NC)"
	@echo "  test-docker          - Run all tests in Docker"
	@echo "  test-docker-unit     - Run unit tests in Docker"
	@echo "  test-docker-e2e      - Run E2E tests in Docker"
	@echo ""
	@echo "$(PURPLE)🚀 Service Management:$(NC)"
	@echo "  start                - Start service locally"
	@echo "  start-docker         - Start service with Docker"
	@echo "  stop                 - Stop all service instances"
	@echo "  restart              - Restart service"
	@echo "  status               - Check service status"
	@echo "  logs                 - View service logs"
	@echo ""
	@echo "$(YELLOW)🔧 Development:$(NC)"
	@echo "  install              - Install dependencies"
	@echo "  lint                 - Run linting tools"
	@echo "  format               - Format code"
	@echo "  clean                - Clean test artifacts"
	@echo "  verify               - Complete verification workflow"
	@echo ""
	@echo "$(WHITE)Service URL: $(BASE_URL)$(NC)"
	@echo "$(WHITE)API Docs:    $(BASE_URL)/docs$(NC)"

# =============================================================================
# TESTING TARGETS
# =============================================================================

.PHONY: test test-unit test-integration test-e2e test-api test-health test-coverage

# Run all tests
test: test-unit test-integration test-e2e
	@echo "$(GREEN)✅ All tests completed successfully!$(NC)"

# Run unit tests
test-unit:
	@echo "$(BLUE)🧪 Running unit tests...$(NC)"
	@$(PYTEST) tests/unit/ -v --tb=short --disable-warnings
	@echo "$(GREEN)✅ Unit tests completed$(NC)"

# Run integration tests (requires running service)
test-integration: check-service-running test-api test-health
	@echo "$(GREEN)✅ Integration tests completed$(NC)"

# Run end-to-end tests
test-e2e:
	@echo "$(BLUE)🎬 Running end-to-end tests...$(NC)"
	@$(PYTHON) scripts/test_e2e_enhanced.py
	@echo "$(GREEN)✅ E2E tests completed$(NC)"

# Test API endpoints with live service
test-api: check-service-running
	@echo "$(BLUE)🔍 Testing API endpoints...$(NC)"
	@$(PYTHON) scripts/verify_api.py

# Test health endpoints with detailed output
test-health: check-service-running
	@echo "$(BLUE)💚 Testing health endpoints...$(NC)"
	@echo "Service URL: $(BASE_URL)"
	@echo ""
	@echo "$(CYAN)=== Health Check Details ===$(NC)"
	@curl -s $(BASE_URL)/api/health | jq '.' || echo "$(RED)❌ Failed to get health details$(NC)"
	@echo ""
	@echo "$(CYAN)=== Service Info ===$(NC)"
	@curl -s $(BASE_URL)/ | jq '.' || echo "$(RED)❌ Failed to get service info$(NC)"
	@echo ""
	@echo "$(CYAN)=== License Info ===$(NC)"
	@curl -s $(BASE_URL)/api/health | jq '.license' || echo "$(RED)❌ Failed to get license info$(NC)"

# Run tests with coverage
test-coverage:
	@echo "$(BLUE)📊 Running tests with coverage...$(NC)"
	@$(PYTEST) tests/unit/ --cov=app --cov-report=html --cov-report=term-missing
	@echo "$(GREEN)✅ Coverage report generated in htmlcov/$(NC)"

# =============================================================================
# DOCKER TESTING TARGETS
# =============================================================================

.PHONY: test-docker test-docker-unit test-docker-e2e

# Run all tests in Docker
test-docker:
	@echo "$(BLUE)🐳 Running all tests in Docker...$(NC)"
	@docker-compose --profile test up --build doc-processing-test

# Run unit tests in Docker
test-docker-unit:
	@echo "$(BLUE)🐳 Running unit tests in Docker...$(NC)"
	@docker-compose run --rm doc-processing-test $(PYTEST) tests/unit/ -v

# Run E2E tests in Docker
test-docker-e2e:
	@echo "$(BLUE)🐳 Running E2E tests in Docker...$(NC)"
	@docker-compose run --rm doc-processing-test python tests/e2e/test_e2e_workflow.py

# =============================================================================
# SERVICE MANAGEMENT
# =============================================================================

.PHONY: start start-docker stop restart status logs check-service-running

# Start service locally
start:
	@echo "$(GREEN)🚀 Starting Document Processing service...$(NC)"
	@echo "Service will be available at: $(BASE_URL)"
	@echo "API Documentation: $(BASE_URL)/docs"
	@echo ""
	@$(PYTHON) -m uvicorn app.main:app --host $(SERVICE_HOST) --port $(SERVICE_PORT) --reload

# Start service with Docker
start-docker:
	@echo "$(GREEN)🐳 Starting Document Processing service with Docker...$(NC)"
	@docker-compose up --build doc-processing
	@echo "Service available at: $(BASE_URL)"

# Start service in background
start-bg:
	@echo "$(GREEN)🚀 Starting Document Processing service in background...$(NC)"
	@$(PYTHON) -m uvicorn app.main:app --host $(SERVICE_HOST) --port $(SERVICE_PORT) --reload > service.log 2>&1 &
	@echo $$! > service.pid
	@sleep 3
	@echo "Service PID: $$(cat service.pid)"
	@echo "Service available at: $(BASE_URL)"
	@echo "Logs: tail -f service.log"

# Stop all service instances
stop:
	@echo "$(YELLOW)🛑 Stopping Document Processing service...$(NC)"
	@pkill -f "uvicorn app.main:app" || echo "No running uvicorn process found"
	@docker-compose down || echo "Docker services stopped"
	@[ -f service.pid ] && kill $$(cat service.pid) && rm service.pid || echo "No background service found"

# Restart service
restart: stop
	@sleep 2
	@$(MAKE) start-bg

# Check service status
status:
	@echo "$(BLUE)📊 Service Status:$(NC)"
	@echo "Local service:"
	@curl -s -f $(BASE_URL)/api/ping > /dev/null && echo "$(GREEN)  ✅ Service is running$(NC)" || echo "$(RED)  ❌ Service is not responding$(NC)"
	@echo "Docker service:"
	@docker-compose ps doc-processing 2>/dev/null || echo "  No Docker service running"

# View service logs
logs:
	@echo "$(BLUE)📋 Service Logs:$(NC)"
	@if [ -f service.log ]; then tail -f service.log; elif docker-compose ps doc-processing >/dev/null 2>&1; then docker-compose logs -f doc-processing; else echo "No logs available"; fi

# Check if service is running (internal target)
check-service-running:
	@curl -s -f $(BASE_URL)/api/ping > /dev/null || (echo "$(RED)❌ Service not running. Start with 'make start' or 'make start-bg'$(NC)" && exit 1)

# =============================================================================
# DEVELOPMENT TARGETS
# =============================================================================

.PHONY: install lint format clean verify

# Install dependencies
install:
	@echo "$(BLUE)📦 Installing dependencies...$(NC)"
ifdef UV
	@uv sync
else
	@pip install -r requirements.txt
endif
	@echo "$(GREEN)✅ Dependencies installed$(NC)"

# Run linting tools
lint:
	@echo "$(BLUE)🔍 Running linting tools...$(NC)"
	@$(PYTHON) -m ruff check app/ tests/ --fix || true
	@$(PYTHON) -m ruff format app/ tests/ || true
	@echo "$(GREEN)✅ Linting completed$(NC)"

# Format code
format: lint
	@echo "$(GREEN)✅ Code formatted$(NC)"

# Clean test artifacts
clean:
	@echo "$(YELLOW)🧹 Cleaning test artifacts...$(NC)"
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@find . -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true
	@rm -rf htmlcov/ .coverage 2>/dev/null || true
	@rm -f service.log service.pid 2>/dev/null || true
	@docker-compose down -v 2>/dev/null || true
	@echo "$(GREEN)✅ Cleanup completed$(NC)"

# Complete verification workflow
verify: clean install start-bg
	@echo "$(CYAN)🔍 Starting complete verification workflow...$(NC)"
	@sleep 5
	@echo ""
	@echo "$(CYAN)Step 1: Unit Tests$(NC)"
	@$(MAKE) test-unit
	@echo ""
	@echo "$(CYAN)Step 2: Integration Tests$(NC)"
	@$(MAKE) test-integration
	@echo ""
	@echo "$(CYAN)Step 3: End-to-End Tests$(NC)"
	@$(MAKE) test-e2e
	@echo ""
	@echo "$(CYAN)Step 4: Docker Tests$(NC)"
	@$(MAKE) test-docker-unit
	@echo ""
	@$(MAKE) stop
	@echo ""
	@echo "$(GREEN)🎉 Complete verification successful! All tests passed.$(NC)"

# =============================================================================
# TEST SCRIPTS
# =============================================================================

# MRZ processing test script
define MRZ_TEST_SCRIPT
import requests
import base64
import json

# Create a simple test request
payload = {
    "processParam": {
        "scenario": "Mrz",
        "resultTypeOutput": ["MrzText", "MrzFields"]
    },
    "List": [
        {
            "ImageData": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        }
    ],
    "tag": "test-session"
}

try:
    response = requests.post(
        "$(BASE_URL)/api/process",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=10
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print("✓ MRZ processing successful")
        exit(0)
    else:
        print(f"✗ MRZ processing failed: {response.text}")
        exit(1)
except Exception as e:
    print(f"✗ MRZ processing error: {e}")
    exit(1)
endef
export MRZ_TEST_SCRIPT

# Default target
.DEFAULT_GOAL := help
