# Marty UI - Makefile
# Build, deploy, and test automation

.PHONY: help build deploy start stop clean test test-ui test-ci status logs shell check-deps install-deps

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m # No Color

# Configuration
CLUSTER_NAME := marty-ui
NAMESPACE := default
UI_PORT := 80
API_PORT := 8000

help: ## Show this help message
	@echo "$(BLUE)🏗️  OpenWallet Foundation mDoc/mDL Demo$(NC)"
	@echo "$(BLUE)==========================================$(NC)"
	@echo ""
	@echo "$(GREEN)Quick Start:$(NC)"
	@echo "  make start    - Build and deploy the complete demo"
	@echo "  make stop     - Stop and cleanup the demo"
	@echo "  make test     - Run comprehensive E2E tests"
	@echo ""
	@echo "$(GREEN)Available commands:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Demo URLs:$(NC)"
	@echo "  🌐 Demo UI:     http://localhost:9080"
	@echo "  🔗 Issuer API:  http://localhost:9080/api/issuer"
	@echo "  ✅ Verifier API: http://localhost:9080/api/verifier"
	@echo "  💳 Wallet API:  http://localhost:9080/api/wallet"

check-deps: ## Check if required dependencies are installed
	@echo "$(BLUE)🔍 Checking dependencies...$(NC)"
	@command -v docker >/dev/null 2>&1 || { echo "$(RED)❌ Docker is required but not installed$(NC)"; exit 1; }
	@command -v kind >/dev/null 2>&1 || { echo "$(RED)❌ Kind is required but not installed$(NC)"; exit 1; }
	@command -v kubectl >/dev/null 2>&1 || { echo "$(RED)❌ kubectl is required but not installed$(NC)"; exit 1; }
	@echo "$(GREEN)✅ All dependencies satisfied$(NC)"

install-deps: ## Install required dependencies (macOS with Homebrew)
	@echo "$(BLUE)📦 Installing dependencies...$(NC)"
	@if command -v brew >/dev/null 2>&1; then \
		brew install kind kubectl; \
		echo "$(GREEN)✅ Dependencies installed$(NC)"; \
	else \
		echo "$(YELLOW)⚠️  Homebrew not found. Please install manually:$(NC)"; \
		echo "  - Docker: https://docs.docker.com/desktop/mac/"; \
		echo "  - Kind: https://kind.sigs.k8s.io/docs/user/quick-start/"; \
		echo "  - kubectl: https://kubernetes.io/docs/tasks/tools/"; \
	fi

# Alternative: Docker Compose deployment
start-compose: build ## Start demo using Docker Compose (alternative to Kind)
	@echo "$(BLUE)🐳 Starting demo with Docker Compose...$(NC)"
	@docker-compose up -d
	@echo "$(GREEN)✅ Demo started with Docker Compose!$(NC)"
	@echo ""
	@echo "$(BLUE)🌐 Demo is available at: http://localhost$(NC)"
	@echo "$(BLUE)📊 Services:$(NC)"
	@echo "  - UI: http://localhost"
	@echo "  - Issuer API: http://localhost:8001"
	@echo "  - Verifier API: http://localhost:8002"
	@echo "  - Wallet API: http://localhost:8003"

stop-compose: ## Stop Docker Compose demo
	@echo "$(BLUE)🛑 Stopping Docker Compose demo...$(NC)"
	@docker-compose down
	@echo "$(GREEN)✅ Docker Compose demo stopped$(NC)"

logs-compose: ## Show Docker Compose logs
	@echo "$(BLUE)📝 Docker Compose Logs$(NC)"
	@docker-compose logs --tail=20

restart-compose: stop-compose start-compose ## Restart Docker Compose demo

build: check-deps ## Build all demo service containers
	@echo "$(BLUE)🏗️  Building demo services...$(NC)"
	@chmod +x build.sh
	@./build.sh
	@echo "$(GREEN)✅ Build completed$(NC)"

deploy: ## Deploy services to Kind cluster
	@echo "$(BLUE)🚀 Deploying to Kind cluster...$(NC)"
	@chmod +x deploy-k8s.sh
	@./deploy-k8s.sh
	@echo "$(GREEN)✅ Deployment completed$(NC)"
	@echo ""
	@echo "$(GREEN)🌐 Demo is available at: http://localhost:9080$(NC)"

start: build deploy ## Complete demo startup (build + deploy)
	@echo "$(GREEN)🎉 Demo started successfully!$(NC)"
	@echo ""
	@echo "$(BLUE)Next steps:$(NC)"
	@echo "  1. Open http://localhost:9080 in your browser"
	@echo "  2. Try the Basic Demo tabs (Issuer, Verifier, Wallet)"
	@echo "  3. Explore Enhanced features for advanced capabilities"
	@echo "  4. Run 'make test' to validate all functionality"

stop: ## Stop the demo and cleanup resources
	@echo "$(BLUE)🛑 Stopping demo...$(NC)"
	@chmod +x cleanup.sh
	@./cleanup.sh
	@echo "$(GREEN)✅ Demo stopped and cleaned up$(NC)"

clean: stop ## Complete cleanup (stop + remove containers)
	@echo "$(BLUE)🧹 Performing deep cleanup...$(NC)"
	@docker system prune -f --volumes || true
	@kind delete cluster --name $(CLUSTER_NAME) || true
	@echo "$(GREEN)✅ Deep cleanup completed$(NC)"

restart: stop start ## Restart the demo (stop + start)
	@echo "$(GREEN)🔄 Demo restarted$(NC)"

status: ## Show demo status and health
	@echo "$(BLUE)📊 Demo Status$(NC)"
	@echo "$(BLUE)==============$(NC)"
	@echo ""
	@echo "$(YELLOW)Kind cluster:$(NC)"
	@kind get clusters 2>/dev/null | grep -q "$(CLUSTER_NAME)" && echo "  ✅ Cluster '$(CLUSTER_NAME)' is running" || echo "  ❌ Cluster '$(CLUSTER_NAME)' not found"
	@echo ""
	@echo "$(YELLOW)Kubernetes pods:$(NC)"
	@kubectl get pods --namespace $(NAMESPACE) 2>/dev/null || echo "  ❌ Cannot connect to cluster"
	@echo ""
	@echo "$(YELLOW)Services:$(NC)"
	@kubectl get services --namespace $(NAMESPACE) 2>/dev/null || echo "  ❌ Cannot connect to cluster"
	@echo ""
	@echo "$(YELLOW)Demo accessibility:$(NC)"
	@curl -f http://localhost:9080/ >/dev/null 2>&1 && echo "  ✅ Demo UI is accessible at http://localhost:9080" || echo "  ❌ Demo UI is not accessible"
	@curl -f http://localhost:9080/api/issuer/health >/dev/null 2>&1 && echo "  ✅ Issuer API is healthy" || echo "  ❌ Issuer API is not responding"
	@curl -f http://localhost:9080/api/verifier/health >/dev/null 2>&1 && echo "  ✅ Verifier API is healthy" || echo "  ❌ Verifier API is not responding"
	@curl -f http://localhost:9080/api/wallet/health >/dev/null 2>&1 && echo "  ✅ Wallet API is healthy" || echo "  ❌ Wallet API is not responding"

logs: ## Show logs from all demo services
	@echo "$(BLUE)📝 Demo Service Logs$(NC)"
	@echo "$(BLUE)===================$(NC)"
	@echo ""
	@echo "$(YELLOW)Issuer Service:$(NC)"
	@kubectl logs -l app=issuer-service --tail=20 --namespace $(NAMESPACE) 2>/dev/null || echo "  ❌ Cannot get issuer logs"
	@echo ""
	@echo "$(YELLOW)Verifier Service:$(NC)"
	@kubectl logs -l app=verifier-service --tail=20 --namespace $(NAMESPACE) 2>/dev/null || echo "  ❌ Cannot get verifier logs"
	@echo ""
	@echo "$(YELLOW)Wallet Service:$(NC)"
	@kubectl logs -l app=wallet-service --tail=20 --namespace $(NAMESPACE) 2>/dev/null || echo "  ❌ Cannot get wallet logs"
	@echo ""
	@echo "$(YELLOW)Demo UI:$(NC)"
	@kubectl logs -l app=demo-ui --tail=20 --namespace $(NAMESPACE) 2>/dev/null || echo "  ❌ Cannot get UI logs"

shell: ## Open a shell in the issuer service pod
	@echo "$(BLUE)🐚 Opening shell in issuer service...$(NC)"
	@kubectl exec -it deployment/issuer-service --namespace $(NAMESPACE) -- /bin/bash

debug: ## Show detailed debug information
	@echo "$(BLUE)🔍 Debug Information$(NC)"
	@echo "$(BLUE)===================$(NC)"
	@echo ""
	@echo "$(YELLOW)Docker images:$(NC)"
	@docker images | grep -E "(marty-ui)" || echo "  ❌ No marty-ui images found"
	@echo ""
	@echo "$(YELLOW)Kind cluster details:$(NC)"
	@kubectl cluster-info --context kind-$(CLUSTER_NAME) 2>/dev/null || echo "  ❌ Cannot get cluster info"
	@echo ""
	@echo "$(YELLOW)Ingress status:$(NC)"
	@kubectl get ingress --namespace $(NAMESPACE) 2>/dev/null || echo "  ❌ Cannot get ingress info"
	@echo ""
	@echo "$(YELLOW)Recent events:$(NC)"
	@kubectl get events --sort-by='.lastTimestamp' --namespace $(NAMESPACE) | head -10 2>/dev/null || echo "  ❌ Cannot get events"

# Test targets
test-setup: ## Setup test environment
	@echo "$(BLUE)🧪 Setting up test environment...$(NC)"
	@cd tests && npm install >/dev/null 2>&1 || echo "$(YELLOW)⚠️  npm install failed, continuing...$(NC)"
	@cd tests && npx playwright install --with-deps chromium >/dev/null 2>&1 || echo "$(YELLOW)⚠️  Playwright install failed, continuing...$(NC)"
	@echo "$(GREEN)✅ Test setup completed$(NC)"

test: test-setup ## Run comprehensive E2E tests
	@echo "$(BLUE)🧪 Running E2E tests...$(NC)"
	@cd tests && chmod +x run-tests.sh
	@cd tests && ./run-tests.sh || { echo "$(RED)❌ Tests failed$(NC)"; exit 1; }
	@echo "$(GREEN)✅ All tests passed!$(NC)"

test-ui: test-setup ## Run tests in UI mode (interactive)
	@echo "$(BLUE)🧪 Running tests in UI mode...$(NC)"
	@cd tests && npx playwright test --ui

test-headed: test-setup ## Run tests in headed mode (visible browser)
	@echo "$(BLUE)🧪 Running tests in headed mode...$(NC)"
	@cd tests && npx playwright test --headed

test-debug: test-setup ## Run tests in debug mode
	@echo "$(BLUE)🧪 Running tests in debug mode...$(NC)"
	@cd tests && npx playwright test --debug

test-basic: test-setup ## Run only basic demo tests
	@echo "$(BLUE)🧪 Running basic demo tests...$(NC)"
	@cd tests && npx playwright test e2e/basic-demo.spec.js

test-enhanced: test-setup ## Run only enhanced feature tests
	@echo "$(BLUE)🧪 Running enhanced feature tests...$(NC)"
	@cd tests && npx playwright test e2e/enhanced-features.spec.js

test-integration: test-setup ## Run only integration tests
	@echo "$(BLUE)🧪 Running integration tests...$(NC)"
	@cd tests && npx playwright test e2e/integration.spec.js

test-ci: test-setup ## Run tests in CI mode (for automation)
	@echo "$(BLUE)🧪 Running tests in CI mode...$(NC)"
	@cd tests && npx playwright test --reporter=junit

test-report: ## Show test report
	@echo "$(BLUE)📊 Opening test report...$(NC)"
	@cd tests && npx playwright show-report

# =============================================================================
# Docker-based Test Targets (Containerized Testing)
# =============================================================================

test-docker-setup: ## Start test infrastructure (Docker)
	@echo "$(BLUE)🐳 Starting test infrastructure...$(NC)"
	@cd tests && docker compose -f docker-compose.test.yml up -d keycloak-db applicant-db redis mailhog
	@echo "$(BLUE)⏳ Waiting for services to be healthy...$(NC)"
	@sleep 10
	@cd tests && docker compose -f docker-compose.test.yml up -d keycloak
	@echo "$(BLUE)⏳ Waiting for Keycloak to be ready...$(NC)"
	@sleep 30
	@cd tests && docker compose -f docker-compose.test.yml up -d oid4vc-api ui
	@echo "$(BLUE)⏳ Waiting for API and UI to be ready...$(NC)"
	@sleep 15
	@echo "$(GREEN)✅ Test infrastructure ready$(NC)"

test-docker: test-docker-setup ## Run tests inside Docker container
	@echo "$(BLUE)🐳 Running tests in Docker container...$(NC)"
	@cd tests && docker compose -f docker-compose.test.yml --profile test up --build playwright --exit-code-from playwright
	@echo "$(GREEN)✅ Docker tests completed$(NC)"

test-docker-chromium: test-docker-setup ## Run Chromium tests in Docker
	@echo "$(BLUE)🐳 Running Chromium tests in Docker...$(NC)"
	@cd tests && docker compose -f docker-compose.test.yml run --rm -e PLAYWRIGHT_ARGS="--project=chromium" playwright
	@echo "$(GREEN)✅ Chromium tests completed$(NC)"

test-docker-down: ## Stop test infrastructure (Docker)
	@echo "$(BLUE)🐳 Stopping test infrastructure...$(NC)"
	@cd tests && docker compose -f docker-compose.test.yml --profile test down -v
	@echo "$(GREEN)✅ Test infrastructure stopped$(NC)"

test-docker-logs: ## Show test infrastructure logs
	@echo "$(BLUE)📋 Showing test infrastructure logs...$(NC)"
	@cd tests && docker compose -f docker-compose.test.yml logs -f

test-docker-status: ## Show test infrastructure status
	@echo "$(BLUE)📊 Test infrastructure status:$(NC)"
	@cd tests && docker compose -f docker-compose.test.yml ps

# Demo walkthrough targets
demo-basic: ## Walk through basic demo features
	@echo "$(BLUE)🎯 Basic Demo Walkthrough$(NC)"
	@echo "$(BLUE)========================$(NC)"
	@echo ""
	@echo "$(GREEN)1. Issuer Service:$(NC)"
	@echo "   - Navigate to http://localhost:9080 and click 'Issuer' tab"
	@echo "   - Fill in personal information (name, birth date, address)"
	@echo "   - Click 'Create Request' to generate a credential request"
	@echo "   - The system will issue an mDL credential with ISO 18013-5 compliance"
	@echo ""
	@echo "$(GREEN)2. Verifier Service:$(NC)"
	@echo "   - Click the 'Verifier' tab (http://localhost:9080)"
	@echo "   - Select verification type (age verification, identity check)"
	@echo "   - Click 'Create Verification Request'"
	@echo "   - Present your credential (QR code simulation)"
	@echo "   - View verification results with selective disclosure"
	@echo ""
	@echo "$(GREEN)3. Wallet Service:$(NC)"
	@echo "   - Click the 'Wallet' tab (http://localhost:9080)"
	@echo "   - View stored credentials and their details"
	@echo "   - Practice selective disclosure (choose which attributes to share)"
	@echo "   - Test credential deletion and management"

demo-enhanced: ## Walk through enhanced demo features
	@echo "$(BLUE)🚀 Enhanced Demo Walkthrough$(NC)"
	@echo "$(BLUE)============================$(NC)"
	@echo ""
	@echo "$(GREEN)1. Age Verification (Privacy-Preserving):$(NC)"
	@echo "   - Click 'Enhanced' tab, then 'Age Verification'"
	@echo "   - Select use case: Over 21 (alcohol), Over 18 (voting), Over 65 (senior)"
	@echo "   - Click 'Verify Age' - notice birth date is NOT disclosed"
	@echo "   - View privacy report showing zero-knowledge proof validation"
	@echo ""
	@echo "$(GREEN)2. Offline QR Verification:$(NC)"
	@echo "   - Go to 'Offline QR' section"
	@echo "   - Click 'Generate Offline QR' to create network-free verification"
	@echo "   - Use 'Scan QR Code' to simulate mobile scanning"
	@echo "   - Verify cryptographic signatures work without internet"
	@echo ""
	@echo "$(GREEN)3. Certificate Lifecycle:$(NC)"
	@echo "   - Navigate to 'Certificate Monitor'"
	@echo "   - View mDL Document Signer Certificate (DSC) status"
	@echo "   - Check expiry dates and renewal recommendations"
	@echo "   - Simulate certificate renewal process"
	@echo ""
	@echo "$(GREEN)4. Policy-Based Disclosure:$(NC)"
	@echo "   - Go to 'Policy Engine' section"
	@echo "   - Test different verifier trust levels"
	@echo "   - See how context affects attribute disclosure"
	@echo "   - View privacy scoring and policy decisions"

demo-full: ## Complete demo walkthrough
	@echo "$(BLUE)🎪 Complete Demo Experience$(NC)"
	@echo "$(BLUE)===========================$(NC)"
	@echo ""
	@echo "$(YELLOW)Follow this complete journey:$(NC)"
	@echo ""
	@echo "$(GREEN)Phase 1 - Credential Lifecycle:$(NC)"
	@echo "  1. Issue credential (Issuer tab)"
	@echo "  2. Store in wallet (Wallet tab)"
	@echo "  3. Verify presentation (Verifier tab)"
	@echo ""
	@echo "$(GREEN)Phase 2 - Privacy Features:$(NC)"
	@echo "  4. Age verification without birth date (Enhanced → Age Verification)"
	@echo "  5. Offline verification (Enhanced → Offline QR)"
	@echo ""
	@echo "$(GREEN)Phase 3 - Advanced Features:$(NC)"
	@echo "  6. Certificate monitoring (Enhanced → Certificate Monitor)"
	@echo "  7. Policy-based disclosure (Enhanced → Policy Engine)"
	@echo ""
	@echo "$(GREEN)Phase 4 - Integration Testing:$(NC)"
	@echo "  8. Run 'make test' to validate all features"
	@echo "  9. Review test report with 'make test-report'"
	@echo ""
	@echo "$(BLUE)🌐 Access the demo at: http://localhost$(NC)"

# Development targets
dev-build: ## Build only (without deployment)
	@$(MAKE) build

dev-deploy: ## Deploy only (assumes built)
	@$(MAKE) deploy

dev-logs-follow: ## Follow logs in real-time
	@echo "$(BLUE)📝 Following demo logs...$(NC)"
	@kubectl logs -f deployment/issuer-service --namespace $(NAMESPACE) &
	@kubectl logs -f deployment/verifier-service --namespace $(NAMESPACE) &
	@kubectl logs -f deployment/wallet-service --namespace $(NAMESPACE) &
	@kubectl logs -f deployment/demo-ui --namespace $(NAMESPACE)

dev-port-forward: ## Forward ports for local development
	@echo "$(BLUE)🔌 Setting up port forwarding...$(NC)"
	@kubectl port-forward service/demo-ui $(UI_PORT):80 --namespace $(NAMESPACE) &
	@kubectl port-forward service/issuer-service $(API_PORT):8000 --namespace $(NAMESPACE) &
	@echo "$(GREEN)✅ Port forwarding active$(NC)"
	@echo "  UI: http://localhost:$(UI_PORT)"
	@echo "  API: http://localhost:$(API_PORT)"

# Maintenance targets
update: ## Update demo to latest version
	@echo "$(BLUE)🔄 Updating demo...$(NC)"
	@git pull origin main
	@$(MAKE) clean
	@$(MAKE) start
	@echo "$(GREEN)✅ Demo updated$(NC)"

backup: ## Backup demo configuration
	@echo "$(BLUE)💾 Creating backup...$(NC)"
	@mkdir -p backups
	@kubectl get all --namespace $(NAMESPACE) -o yaml > backups/demo-backup-$(shell date +%Y%m%d-%H%M%S).yaml
	@echo "$(GREEN)✅ Backup created in backups/$(NC)"

validate: ## Validate demo configuration
	@echo "$(BLUE)✅ Validating demo configuration...$(NC)"
	@kubectl apply --dry-run=client -f k8s/ >/dev/null 2>&1 && echo "$(GREEN)✅ Kubernetes manifests are valid$(NC)" || echo "$(RED)❌ Invalid Kubernetes manifests$(NC)"
	@docker images | grep -q "marty-ui" && echo "$(GREEN)✅ Docker images exist$(NC)" || echo "$(YELLOW)⚠️  Docker images not found$(NC)"

# Documentation
docs: ## Open documentation
	@echo "$(BLUE)📖 Opening documentation...$(NC)"
	@open README.md || echo "$(YELLOW)Please open README.md manually$(NC)"

examples: ## Show usage examples
	@echo "$(BLUE)💡 Usage Examples$(NC)"
	@echo "$(BLUE)=================$(NC)"
	@echo ""
	@echo "$(GREEN)Quick start:$(NC)"
	@echo "  make start          # Build and start everything"
	@echo "  make demo-basic     # Walk through basic features"
	@echo "  make test           # Validate all functionality"
	@echo ""
	@echo "$(GREEN)Development workflow:$(NC)"
	@echo "  make build          # Build containers"
	@echo "  make deploy         # Deploy to Kind"
	@echo "  make status         # Check health"
	@echo "  make logs           # View logs"
	@echo ""
	@echo "$(GREEN)Testing:$(NC)"
	@echo "  make test-basic     # Test basic features"
	@echo "  make test-enhanced  # Test advanced features"
	@echo "  make test-ui        # Interactive testing"
	@echo ""
	@echo "$(GREEN)Cleanup:$(NC)"
	@echo "  make stop           # Stop demo"
	@echo "  make clean          # Deep cleanup"
