# Marty Development Environment
# ==============================
#
# One-stop entry point for development, testing, and deployment.
#
# QUICK START (Docker):
#   make help        - Show all available commands
#   make dev         - Start development environment (all in Docker)
#   make test        - Run E2E tests (full browser matrix)
#   make test-local  - Run fast Chromium-only tests
#
# QUICK START (Native - faster feedback):
#   make dev-setup   - One-time: install UV, deps, Playwright browsers
#   make dev-infra   - Start infrastructure (Keycloak, Postgres, Redis)
#   make dev-api     - Start API natively (hot reload)
#   make dev-ui      - Start UI natively (hot reload)
#   make test-native - Run Playwright tests against native services
#
# PREREQUISITES:
#   - Docker & Docker Compose v2 (for infrastructure)
#   - UV (auto-installed by dev-setup)
#   - Node.js 18+ (for UI and Playwright)

.PHONY: help dev test test-local pytest build build-wallet push-wallet clean \
        status logs down up restart shell \
        dev-setup dev-infra dev-api dev-ui wallet \
        test-native test-native-ui test-native-headed test-native-debug

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
UI_PORT ?= 3000
KEYCLOAK_REALM ?= marty

.DEFAULT_GOAL := help

# =============================================================================
# Help
# =============================================================================
help: ## Show this help message
	@echo "$(BLUE)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(BLUE)  🚀 Marty Development Environment$(NC)"
	@echo "$(BLUE)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo ""
	@echo "$(GREEN)Quick Start (Docker):$(NC)"
	@echo "  make dev           Start full environment in Docker"
	@echo "  make dev-sentinel  Start with Redis Sentinel (HA testing)"
	@echo "  make test          Run E2E tests with full browser matrix"
	@echo "  make test-local    Run fast Chromium-only E2E tests"
	@echo ""
	@echo "$(GREEN)Quick Start (Native - faster feedback):$(NC)"
	@echo "  make dev-setup      One-time setup (UV, deps, browsers)"
	@echo "  make dev-infra      Start infrastructure only"
	@echo "  make dev-api        Start API natively (hot reload)"
	@echo "  make dev-ui         Start UI natively (hot reload)"
	@echo "  make test-native    Run Playwright tests"
	@echo "  make test-native-ui Playwright interactive mode"
	@echo ""
	@echo "$(GREEN)Available Commands:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-14s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)URLs (when running):$(NC)"
	@echo "  🌐 UI:         http://localhost:$(UI_PORT)"
	@echo "  🔗 API:        http://localhost:8000"
	@echo "  🔐 Keycloak:   http://localhost:8180  (admin/admin)"
	@echo "  📧 MailHog:    http://localhost:9025"
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
	@echo "  📧 MailHog:  http://localhost:9025"
	@echo ""
	@echo "$(YELLOW)Tip:$(NC) Run 'make logs' to follow service logs"

up: dev ## Alias for 'dev'

dev-sentinel: ## Start development environment with Redis Sentinel (HA testing)
	@echo "$(BLUE)🚀 Starting development environment with Redis Sentinel...$(NC)"
	$(COMPOSE) -f docker-compose.yml -f docker-compose.sentinel.yml --profile dev up -d
	@echo ""
	@echo "$(GREEN)✅ Development environment with Redis Sentinel ready!$(NC)"
	@echo ""
	@echo "  🌐 UI:         http://localhost:9080"
	@echo "  🔗 API:        http://localhost:8000"
	@echo "  🔐 Keycloak:   http://localhost:8180"
	@echo "  📧 MailHog:    http://localhost:9025"
	@echo "  🔴 Redis:      Single instance replaced by Sentinel cluster"
	@echo "  🛡️  Sentinel:  Ports 26379, 26380, 26381"
	@echo ""
	@echo "$(YELLOW)Note:$(NC) Redis Sentinel provides automatic failover for HA testing"
	@echo "$(YELLOW)Tip:$(NC) Run 'make logs' to follow service logs"

dev-cluster: ## Start development environment with Redis Cluster (experimental)
	@echo "$(BLUE)🚀 Starting development environment with Redis Cluster...$(NC)"
	@echo "$(YELLOW)⚠️  Warning: Requires all code to use hash tags {org-id} for multi-key ops$(NC)"
	@echo "$(YELLOW)⚠️  This is experimental - use for testing cluster compatibility only$(NC)"
	@echo ""
	$(COMPOSE) -f docker-compose.yml -f docker-compose.cluster.yml --profile dev up -d
	@echo ""
	@echo "$(GREEN)✅ Redis Cluster environment ready!$(NC)"
	@echo ""
	@echo "  🔴 Redis Nodes: localhost:7000-7002"
	@echo "  🔗 API:         http://localhost:8000"
	@echo "  🌐 UI:          http://localhost:9080"
	@echo ""
	@echo "$(YELLOW)Note:$(NC) Connect to any node - cluster topology auto-discovered"
	@echo "$(YELLOW)Tip:$(NC) Check cluster status: docker exec redis-node-1 redis-cli -p 7000 cluster info"

	@echo "For now, use 'make dev-sentinel' for high availability testing."
	@exit 1

# =============================================================================
# Testing
# =============================================================================
test: _ensure-wallet _check-wallet-build ## Run E2E tests (full browser matrix)
	@echo "$(BLUE)🧪 Running E2E tests (Chromium, Firefox, WebKit)...$(NC)"
	$(COMPOSE) --profile test up -d postgres redis mailhog keycloak
	@echo "$(BLUE)⏳ Waiting for infrastructure...$(NC)"
	@sleep 5
	$(COMPOSE) --profile test up -d oid4vc-api-test ui-test wallet-simulator
	@echo "$(BLUE)⏳ Waiting for services to be healthy...$(NC)"
	@sleep 10
	@echo "$(BLUE)🌱 Seeding demo data...$(NC)"
	@$(COMPOSE) cp marty-ui/scripts/seed_demo_data.py oid4vc-api-test:/tmp/seed_demo_data.py
	@$(COMPOSE) exec -T oid4vc-api-test python /tmp/seed_demo_data.py
	@echo "$(GREEN)✅ Demo data seeded!$(NC)"
	$(COMPOSE) --profile test up playwright --exit-code-from playwright
	@echo "$(GREEN)✅ E2E tests completed!$(NC)"

test-local: _ensure-wallet _check-wallet-build ## Run fast Chromium-only E2E tests
	@echo "$(BLUE)🧪 Running Chromium-only E2E tests...$(NC)"
	$(COMPOSE) --profile test-local up -d postgres redis mailhog keycloak
	@echo "$(BLUE)⏳ Waiting for infrastructure...$(NC)"
	@sleep 5
	$(COMPOSE) --profile test-local up -d oid4vc-api-test ui-test wallet-simulator
	@echo "$(BLUE)⏳ Waiting for services to be healthy...$(NC)"
	@sleep 10
	@echo "$(BLUE)🌱 Seeding demo data...$(NC)"
	@$(COMPOSE) cp marty-ui/scripts/seed_demo_data.py oid4vc-api-test:/tmp/seed_demo_data.py
	@$(COMPOSE) exec -T oid4vc-api-test python /tmp/seed_demo_data.py
	@echo "$(GREEN)✅ Demo data seeded!$(NC)"
	$(COMPOSE) --profile test-local up playwright-local --exit-code-from playwright-local
	@echo "$(GREEN)✅ Chromium tests completed!$(NC)"

test-fast: _ensure-wallet _check-wallet-build ## Run fast Chromium-only E2E tests (skip @slow)
	@echo "$(BLUE)🧪 Running fast Chromium-only E2E tests (skip @slow)...$(NC)"
	$(COMPOSE) --profile test-local up -d postgres redis mailhog keycloak
	@echo "$(BLUE)⏳ Waiting for infrastructure...$(NC)"
	@sleep 5
	$(COMPOSE) --profile test-local up -d oid4vc-api-test ui-test wallet-simulator
	@echo "$(BLUE)⏳ Waiting for services to be healthy...$(NC)"
	@sleep 10
	PW_FAST=1 $(COMPOSE) --profile test-local up playwright-local --exit-code-from playwright-local
	@echo "$(GREEN)✅ Fast Chromium tests completed!$(NC)"

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

_check-wallet-build:
	@if [ -d "$(MARTY_AUTH_PATH)/build/web" ]; then \
		echo "$(GREEN)✅ Flutter wallet build found$(NC)"; \
	else \
		echo "$(RED)❌ Flutter wallet build not found at $(MARTY_AUTH_PATH)/build/web$(NC)"; \
		echo "$(YELLOW)E2E tests require the Flutter web wallet. Run:$(NC)"; \
		echo "  cd $(MARTY_AUTH_PATH) && flutter build web --web-renderer canvaskit"; \
		echo "$(YELLOW)Or build the Docker image:$(NC)"; \
		echo "  make build-wallet"; \
		exit 1; \
	fi

# =============================================================================
# Native Development (Faster Feedback Loop)
# =============================================================================
dev-setup: ## One-time setup: UV, Python deps, Node deps, Playwright browsers
	@echo "$(BLUE)🔧 Setting up native development environment...$(NC)"
	@echo ""
	@echo "$(BLUE)📦 Checking UV installation...$(NC)"
	@if ! command -v uv >/dev/null 2>&1; then \
		echo "$(YELLOW)Installing UV...$(NC)"; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
		echo "$(GREEN)✅ UV installed. You may need to restart your shell or run: source ~/.bashrc$(NC)"; \
	else \
		echo "$(GREEN)✅ UV already installed: $$(uv --version)$(NC)"; \
	fi
	@echo ""
	@echo "$(BLUE)🐍 Setting up Python environment for API...$(NC)"
	cd marty-ui/src && uv venv .venv && uv pip install -r requirements.txt
	@echo "$(GREEN)✅ Python environment ready$(NC)"
	@echo ""
	@echo "$(BLUE)📦 Installing UI dependencies...$(NC)"
	cd marty-ui/ui && npm install
	@echo "$(GREEN)✅ UI dependencies ready$(NC)"
	@echo ""
	@echo "$(BLUE)🎭 Installing Playwright and browsers...$(NC)"
	cd marty-ui/tests && npm install && npx playwright install --with-deps
	@echo "$(GREEN)✅ Playwright browsers installed$(NC)"
	@echo ""
	@echo "$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(GREEN)✅ Native development environment ready!$(NC)"
	@echo "$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo ""
	@echo "$(YELLOW)Next: Run 'make dev-infra' to start infrastructure$(NC)"

dev-infra: ## Start infrastructure only (Keycloak, Postgres, Redis, MailHog)
	@echo "$(BLUE)🏗️ Starting infrastructure services...$(NC)"
	UI_BASE_URL=http://localhost:$(UI_PORT) $(COMPOSE) up -d postgres redis mailhog keycloak
	@echo "$(BLUE)⏳ Waiting for Keycloak to be healthy (this may take ~60s on first run)...$(NC)"
	@until curl -sf http://localhost:8180/realms/marty >/dev/null 2>&1; do \
		printf "."; \
		sleep 3; \
	done
	@echo ""
	@echo ""
	@echo "$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(GREEN)✅ Infrastructure ready!$(NC)"
	@echo "$(GREEN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo ""
	@echo "  🔐 Keycloak: http://localhost:8180  (admin/admin)"
	@echo "  🗄️  Postgres: localhost:5433"
	@echo "  📦 Redis:    localhost:6379"
	@echo "  📧 MailHog:  http://localhost:9025"
	@echo ""
	@echo "$(YELLOW)Next steps (in separate terminals):$(NC)"
	@echo "  make dev-api        Start API (Terminal 2)"
	@echo "  make dev-ui         Start UI (Terminal 3)"
	@echo "  make test-native-ui Run tests (Terminal 4)"

dev-api: ## Start API natively with hot reload (requires dev-infra)
	@echo "$(BLUE)🚀 Starting API natively on http://localhost:8000...$(NC)"
	@echo "$(YELLOW)Tip: Ensure infrastructure is running: make dev-infra$(NC)"
	@echo ""
	cd marty-ui/src && \
		. .venv/bin/activate && \
		export PYTHONPATH="$(CURDIR)/marty-microservices-framework:$$PYTHONPATH" && \
		ADAPTER_MODE=spruceid \
		STORAGE_MODE=memory \
		TEST_MODE=true \
		DATABASE_URL=postgresql+asyncpg://marty:marty@localhost:5433/marty_applicants \
		APPLICANT_DB_URL=postgresql+asyncpg://marty:marty@localhost:5433/marty_applicants \
		STATUS_LIST_MASTER_KEY=KYeUP5FYR0hrh76AUWELevVgfMQgGY9MrOuhGNtmWGQ= \
		OIDC_ISSUER_URL=http://localhost:8180/realms/$(KEYCLOAK_REALM) \
		OIDC_BACKEND_ISSUER_URL=http://localhost:8180/realms/$(KEYCLOAK_REALM) \
		OIDC_CLIENT_ID=marty-ui \
		OIDC_REDIRECT_URI=http://localhost:$(UI_PORT)/auth/callback \
		OIDC_POST_LOGOUT_REDIRECT_URI=http://localhost:$(UI_PORT) \
		KEYCLOAK_URL=http://localhost:8180 \
		KEYCLOAK_ADMIN_CLIENT_ID=admin-cli \
		REDIS_URL=redis://localhost:6379/0 \
		SESSION_SECRET=dev-session-secret-change-in-production \
		COOKIE_SECURE=false \
		COOKIE_SAMESITE=lax \
		python -m uvicorn oid4vc_api:app --reload --host 0.0.0.0 --port 8000

dev-ui: ## Start UI natively with hot reload (requires dev-api)
	@echo "$(BLUE)🚀 Starting UI natively on http://localhost:$(UI_PORT)...$(NC)"
	@echo "$(YELLOW)Tip: Ensure API is running: make dev-api$(NC)"
	@echo ""
	cd marty-ui/ui && \
		PORT=$(UI_PORT) \
		REACT_APP_API_URL=http://localhost:8000 \
		REACT_APP_KEYCLOAK_URL=http://localhost:8180 \
		REACT_APP_KEYCLOAK_REALM=$(KEYCLOAK_REALM) \
		REACT_APP_KEYCLOAK_CLIENT_ID=marty-ui \
		npm start

wallet: ## Start wallet-simulator in Docker (needed for issuance flows)
	@echo "$(BLUE)📱 Starting wallet-simulator on http://localhost:9081...$(NC)"
	$(MAKE) _ensure-wallet
	$(COMPOSE) up -d wallet-simulator
	@echo "$(GREEN)✅ Wallet available at http://localhost:9081$(NC)"

test-native: ## Run Playwright tests against native services
	@echo "$(BLUE)🧪 Running Playwright tests natively...$(NC)"
	@echo "$(YELLOW)Ensure services are running: dev-infra, dev-api, dev-ui$(NC)"
	@echo ""
	cd marty-ui/tests && \
		BASE_URL=http://localhost:$(UI_PORT) \
		API_URL=http://localhost:8000 \
		KEYCLOAK_URL=http://localhost:8180 \
		WALLET_URL=http://localhost:9081 \
		MAILHOG_URL=http://localhost:9025 \
		npx playwright test

test-native-ui: ## Run Playwright with interactive UI mode
	@echo "$(BLUE)🎭 Opening Playwright UI mode...$(NC)"
	cd marty-ui/tests && \
		BASE_URL=http://localhost:$(UI_PORT) \
		API_URL=http://localhost:8000 \
		KEYCLOAK_URL=http://localhost:8180 \
		WALLET_URL=http://localhost:9081 \
		MAILHOG_URL=http://localhost:9025 \
		npx playwright test --ui

test-native-headed: ## Run Playwright tests with visible browser
	@echo "$(BLUE)🧪 Running tests with visible browser...$(NC)"
	cd marty-ui/tests && \
		BASE_URL=http://localhost:$(UI_PORT) \
		API_URL=http://localhost:8000 \
		KEYCLOAK_URL=http://localhost:8180 \
		WALLET_URL=http://localhost:9081 \
		MAILHOG_URL=http://localhost:9025 \
		npx playwright test --headed

test-native-debug: ## Run Playwright tests in debug mode
	@echo "$(BLUE)🐛 Running tests in debug mode...$(NC)"
	cd marty-ui/tests && \
		BASE_URL=http://localhost:$(UI_PORT) \
		API_URL=http://localhost:8000 \
		KEYCLOAK_URL=http://localhost:8180 \
		WALLET_URL=http://localhost:9081 \
		MAILHOG_URL=http://localhost:9025 \
		npx playwright test --debug

.SILENT: help
