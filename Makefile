# Marty Development Environment
# ==============================
#
# One-stop entry point for development, testing, and deployment.
#
# QUICK START:
#   make help        - Show all available commands
#   make dev         - Start development environment
#   make test        - Run E2E tests (full browser matrix)
#   make test-local  - Run fast Chromium-only tests
#
# PREREQUISITES:
#   - Docker & Docker Compose v2
#   - For wallet-simulator: pre-built image or use 'make build-wallet'

.PHONY: help dev test test-local pytest build build-wallet push-wallet clean \
        status logs down up restart shell

# Colors
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m

# Configuration
COMPOSE := docker compose
WALLET_IMAGE := ghcr.io/anthropic/marty-authenticator:local
MARTY_AUTH_PATH := ../marty-authenticator

.DEFAULT_GOAL := help

# =============================================================================
# Help
# =============================================================================
help: ## Show this help message
	@echo "$(BLUE)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(BLUE)  🚀 Marty Development Environment$(NC)"
	@echo "$(BLUE)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo ""
	@echo "$(GREEN)Quick Start:$(NC)"
	@echo "  make dev         Start development environment (API, UI, Keycloak, etc.)"
	@echo "  make test        Run E2E tests with full browser matrix"
	@echo "  make test-local  Run fast Chromium-only E2E tests"
	@echo ""
	@echo "$(GREEN)Available Commands:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-14s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)URLs (when running):$(NC)"
	@echo "  🌐 UI:         http://localhost:9080"
	@echo "  🔗 API:        http://localhost:8000"
	@echo "  🔐 Keycloak:   http://localhost:8180  (admin/admin)"
	@echo "  📧 MailHog:    http://localhost:8025"
	@echo "  📱 Wallet:     http://localhost:9081  (test profile only)"
	@echo ""
	@echo "$(GREEN)Demo Credentials:$(NC)"
	@echo "  Admin:     admin@marty.demo / Admin123!"
	@echo "  Vendor:    vendor@marty.demo / Vendor123!"
	@echo "  Applicant: john.doe@marty.demo / Applicant123!"
	@echo ""

# =============================================================================
# Development
# =============================================================================
dev: ## Start development environment
	@echo "$(BLUE)🚀 Starting development environment...$(NC)"
	$(COMPOSE) --profile dev up -d
	@echo ""
	@echo "$(GREEN)✅ Development environment ready!$(NC)"
	@echo ""
	@echo "  🌐 UI:       http://localhost:9080"
	@echo "  🔗 API:      http://localhost:8000"
	@echo "  🔐 Keycloak: http://localhost:8180"
	@echo "  📧 MailHog:  http://localhost:8025"
	@echo ""
	@echo "$(YELLOW)Tip:$(NC) Run 'make logs' to follow service logs"

up: dev ## Alias for 'dev'

# =============================================================================
# Testing
# =============================================================================
test: _ensure-wallet ## Run E2E tests (full browser matrix)
	@echo "$(BLUE)🧪 Running E2E tests (Chromium, Firefox, WebKit)...$(NC)"
	$(COMPOSE) --profile test up -d postgres redis mailhog keycloak
	@echo "$(BLUE)⏳ Waiting for infrastructure...$(NC)"
	@sleep 5
	$(COMPOSE) --profile test up -d oid4vc-api ui wallet-simulator
	@echo "$(BLUE)⏳ Waiting for services to be healthy...$(NC)"
	@sleep 10
	$(COMPOSE) --profile test up playwright --exit-code-from playwright
	@echo "$(GREEN)✅ E2E tests completed!$(NC)"

test-local: _ensure-wallet ## Run fast Chromium-only E2E tests
	@echo "$(BLUE)🧪 Running Chromium-only E2E tests...$(NC)"
	$(COMPOSE) --profile test-local up -d postgres redis mailhog keycloak
	@echo "$(BLUE)⏳ Waiting for infrastructure...$(NC)"
	@sleep 5
	$(COMPOSE) --profile test-local up -d oid4vc-api ui wallet-simulator
	@echo "$(BLUE)⏳ Waiting for services to be healthy...$(NC)"
	@sleep 10
	$(COMPOSE) --profile test-local up playwright-local --exit-code-from playwright-local
	@echo "$(GREEN)✅ Chromium tests completed!$(NC)"

pytest: ## Run Python unit/integration tests
	@echo "$(BLUE)🧪 Running Python tests...$(NC)"
	$(COMPOSE) --profile pytest up -d postgres-pytest redis-pytest
	@echo "$(BLUE)⏳ Waiting for database...$(NC)"
	@sleep 5
	$(COMPOSE) --profile pytest up pytest --exit-code-from pytest
	@echo "$(GREEN)✅ Python tests completed!$(NC)"

test-report: ## Open Playwright test report
	@echo "$(BLUE)📊 Opening test report...$(NC)"
	@cd marty-ui/tests && npx playwright show-report

# =============================================================================
# Building
# =============================================================================
build: ## Build all service images
	@echo "$(BLUE)🏗️ Building service images...$(NC)"
	$(COMPOSE) --profile dev build
	@echo "$(GREEN)✅ Build completed!$(NC)"

build-wallet: ## Build wallet-simulator image from marty-authenticator
	@echo "$(BLUE)🏗️ Building wallet-simulator image...$(NC)"
	@if [ ! -d "$(MARTY_AUTH_PATH)" ]; then \
		echo "$(RED)❌ marty-authenticator not found at $(MARTY_AUTH_PATH)$(NC)"; \
		echo "$(YELLOW)Clone it alongside this repo or set MARTY_AUTH_PATH$(NC)"; \
		exit 1; \
	fi
	docker build -t $(WALLET_IMAGE) \
		-f $(MARTY_AUTH_PATH)/docker/Dockerfile.flutter.web.test \
		$(MARTY_AUTH_PATH)
	@echo "$(GREEN)✅ Wallet image built: $(WALLET_IMAGE)$(NC)"

push-wallet: ## Push wallet-simulator to ghcr.io
	@echo "$(BLUE)📤 Pushing wallet-simulator image...$(NC)"
	docker push $(WALLET_IMAGE)
	@echo "$(GREEN)✅ Pushed: $(WALLET_IMAGE)$(NC)"

# =============================================================================
# Lifecycle Management
# =============================================================================
down: ## Stop all services
	@echo "$(BLUE)🛑 Stopping all services...$(NC)"
	$(COMPOSE) --profile dev --profile test --profile test-local --profile pytest down
	@echo "$(GREEN)✅ All services stopped$(NC)"

clean: ## Stop services and remove volumes
	@echo "$(BLUE)🧹 Cleaning up...$(NC)"
	$(COMPOSE) --profile dev --profile test --profile test-local --profile pytest down -v --remove-orphans
	@echo "$(GREEN)✅ Cleanup complete$(NC)"

restart: down dev ## Restart development environment

# =============================================================================
# Observability
# =============================================================================
status: ## Show service status
	@echo "$(BLUE)📊 Service Status$(NC)"
	@echo "$(BLUE)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "(marty|keycloak|postgres|redis|mailhog|playwright|wallet)" || echo "No services running"
	@echo ""
	@echo "$(YELLOW)Health checks:$(NC)"
	@curl -sf http://localhost:8000/health >/dev/null 2>&1 && echo "  ✅ API healthy" || echo "  ❌ API not responding"
	@curl -sf http://localhost:9080 >/dev/null 2>&1 && echo "  ✅ UI accessible" || echo "  ❌ UI not accessible"
	@curl -sf http://localhost:8180 >/dev/null 2>&1 && echo "  ✅ Keycloak accessible" || echo "  ❌ Keycloak not accessible"

logs: ## Follow logs from all services
	@echo "$(BLUE)📋 Following logs (Ctrl+C to stop)...$(NC)"
	$(COMPOSE) --profile dev logs -f

logs-api: ## Follow API logs only
	$(COMPOSE) --profile dev logs -f oid4vc-api

logs-ui: ## Follow UI logs only
	$(COMPOSE) --profile dev logs -f ui

logs-keycloak: ## Follow Keycloak logs only
	$(COMPOSE) --profile dev logs -f keycloak

# =============================================================================
# Development Utilities
# =============================================================================
shell-api: ## Open shell in API container
	@echo "$(BLUE)🐚 Opening shell in API container...$(NC)"
	docker exec -it $$(docker ps -qf "name=oid4vc-api") /bin/bash

shell-db: ## Open psql shell in Postgres container
	@echo "$(BLUE)🐚 Opening psql shell...$(NC)"
	docker exec -it $$(docker ps -qf "name=postgres") psql -U postgres

seed: ## Re-run database seeding
	@echo "$(BLUE)🌱 Running database seed...$(NC)"
	$(COMPOSE) --profile dev up seed
	@echo "$(GREEN)✅ Seeding complete$(NC)"

# =============================================================================
# Internal Helpers
# =============================================================================
_ensure-wallet:
	@if ! docker image inspect $(WALLET_IMAGE) >/dev/null 2>&1; then \
		echo "$(YELLOW)⚠️  Wallet image not found: $(WALLET_IMAGE)$(NC)"; \
		echo "$(BLUE)Building wallet-simulator...$(NC)"; \
		$(MAKE) build-wallet; \
	fi

.SILENT: help
