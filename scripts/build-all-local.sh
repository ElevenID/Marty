#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Local Build & Push Orchestration Script
# =============================================================================
# Builds all Marty artifacts locally and pushes to GitHub Container Registry
# - Python wheels (marty-core, marty-credentials, marty-msf)
# - Docker images (all 10 services)
# - Incremental builds: only rebuilds changed services
#
# Usage:
#   ./build-all-local.sh [OPTIONS]
#
# Options:
#   --force         Force rebuild all services (ignore change detection)
#   --skip-wheels   Skip Python wheel building
#   --skip-docker   Skip Docker image building
#   --skip-push     Skip pushing to GHCR
#   --help          Show this help message
#
# Prerequisites:
#   - Docker with Buildx
#   - Rust toolchain (cargo, rustup)
#   - Python 3.11+ with maturin, hatchling, twine
#   - gh CLI (GitHub CLI)
#   - Authenticated to GHCR (run ./scripts/ghcr-setup.sh first)
#
# =============================================================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_MARKER="$WORKSPACE_ROOT/.last-build-sha"
CURRENT_SHA=$(git -C "$WORKSPACE_ROOT" rev-parse HEAD)
SHORT_SHA=$(git -C "$WORKSPACE_ROOT" rev-parse --short HEAD)
CURRENT_BRANCH=$(git -C "$WORKSPACE_ROOT" rev-parse --abbrev-ref HEAD)
BUILD_DATE=$(date +%Y%m%d)
DEV_TAG="dev-${BUILD_DATE}-${SHORT_SHA}"

# GitHub organization/user (extract from git remote)
GITHUB_REPO=$(git -C "$WORKSPACE_ROOT" remote get-url origin | sed -E 's/.*[:/]([^/]+\/[^/]+)(\.git)?$/\1/' | sed 's/\.git$//')
GHCR_PREFIX=$(echo "ghcr.io/${GITHUB_REPO}" | tr '[:upper:]' '[:lower:]')  # Convert to lowercase

# Options
FORCE_BUILD=false
SKIP_WHEELS=false
SKIP_DOCKER=false
SKIP_PUSH=false

# Service list (actual Dockerfiles in src/)
SERVICES=(
  "csca-service:src/marty_plugin/csca_service/Dockerfile"
  "document-signer:src/document_signer/Dockerfile"
  "document-processing:src/marty_plugin/document_processing/Dockerfile"
  "inspection-system:src/marty_plugin/inspection_system/Dockerfile"
  "passport-engine:src/marty_plugin/passport_engine/Dockerfile"
)

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --force)
      FORCE_BUILD=true
      shift
      ;;
    --skip-wheels)
      SKIP_WHEELS=true
      shift
      ;;
    --skip-docker)
      SKIP_DOCKER=true
      shift
      ;;
    --skip-push)
      SKIP_PUSH=true
      shift
      ;;
    --help)
      head -n 30 "$0" | grep "^#" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      exit 1
      ;;
  esac
done

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
  echo -e "${BLUE}ℹ ${NC}$1"
}

log_success() {
  echo -e "${GREEN}✓${NC} $1"
}

log_warning() {
  echo -e "${YELLOW}⚠ ${NC}$1"
}

log_error() {
  echo -e "${RED}✗${NC} $1"
}

log_section() {
  echo ""
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${BLUE}  $1${NC}"
  echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo ""
}

check_prerequisites() {
  log_section "Checking Prerequisites"
  
  local missing=()
  
  command -v docker >/dev/null 2>&1 || missing+=("docker")
  command -v cargo >/dev/null 2>&1 || missing+=("cargo")
  command -v python3 >/dev/null 2>&1 || missing+=("python3")
  command -v gh >/dev/null 2>&1 || missing+=("gh")
  
  if [ ${#missing[@]} -ne 0 ]; then
    log_error "Missing required tools: ${missing[*]}"
    log_info "Install with: brew install ${missing[*]}"
    exit 1
  fi
  
  # Check Docker Buildx
  if ! docker buildx version >/dev/null 2>&1; then
    log_error "Docker Buildx not available"
    exit 1
  fi
  
  # Check GHCR authentication (unless skipping push)
  if [ "$SKIP_PUSH" = false ]; then
    # Try to login with stored credentials to verify auth
    if ! docker login ghcr.io --password-stdin < /dev/null 2>/dev/null; then
      log_warning "GHCR authentication may not be configured"
      log_info "Run ./scripts/ghcr-setup.sh if push fails"
      log_info "Or use --skip-push to build without pushing"
      # Don't exit - let the actual push fail if needed
    fi
  fi
  
  log_success "All prerequisites satisfied"
}

has_changes() {
  local path=$1
  local last_sha
  
  if [ "$FORCE_BUILD" = true ]; then
    return 0
  fi
  
  if [ ! -f "$BUILD_MARKER" ]; then
    log_info "No previous build marker found, will build all"
    return 0
  fi
  
  last_sha=$(cat "$BUILD_MARKER")
  
  # Check if path has changes since last build
  if git -C "$WORKSPACE_ROOT" diff --quiet "$last_sha" HEAD -- "$path" 2>/dev/null; then
    return 1  # No changes
  else
    return 0  # Has changes
  fi
}

# =============================================================================
# Python Wheel Building
# =============================================================================

build_python_wheels() {
  if [ "$SKIP_WHEELS" = true ]; then
    log_section "Skipping Python Wheels (--skip-wheels)"
    return 0
  fi
  
  log_section "Building Python Wheels"
  
  log_warning "⏭️  Skipping Python wheel builds (native macOS compilation issues)"
  log_info "Docker images will include all required Python dependencies"
  return 0
  
  local wheels_built=0
  local dist_dir="$WORKSPACE_ROOT/dist"
  rm -rf "$dist_dir"
  mkdir -p "$dist_dir"
  
  # Build marty-credentials (Rust + Python)
  if has_changes "../marty-credentials"; then
    log_info "Building marty-credentials wheels..."
    (
      cd "$WORKSPACE_ROOT/../marty-credentials"
      maturin build --release --manifest-path rust/marty-rs/Cargo.toml --out "$dist_dir"
    )
    log_success "marty-credentials wheels built"
    ((wheels_built++))
  else
    log_info "Skipping marty-credentials (no changes)"
  fi
  
  # Build marty-core Python bindings
  if has_changes "../marty-core"; then
    log_info "Building marty-core wheels..."
    (
      cd "$WORKSPACE_ROOT/../marty-core"
      # Build each crate that has Python bindings
      for crate in marty-types marty-biometrics marty-iso18013 marty-verification; do
        if [ -f "$crate/Cargo.toml" ] && grep -q "pyo3" "$crate/Cargo.toml" 2>/dev/null; then
          log_info "  Building $crate..."
          maturin build --release --manifest-path "$crate/Cargo.toml" --out "$dist_dir"
        fi
      done
    )
    log_success "marty-core wheels built"
    ((wheels_built++))
  else
    log_info "Skipping marty-core (no changes)"
  fi
  
  # Build marty-microservices-framework (pure Python)
  if has_changes "../marty-microservices-framework"; then
    log_info "Building marty-microservices-framework..."
    (
      cd "$WORKSPACE_ROOT/../marty-microservices-framework"
      python3 -m build --wheel --outdir "$dist_dir"
    )
    log_success "marty-microservices-framework built"
    ((wheels_built++))
  else
    log_info "Skipping marty-microservices-framework (no changes)"
  fi
  
  if [ $wheels_built -eq 0 ]; then
    log_warning "No wheels needed rebuilding"
    return 0
  fi
  
  # Create GitHub release with wheels
  if [ "$SKIP_PUSH" = false ]; then
    log_info "Creating GitHub release: $DEV_TAG"
    
    # Delete existing release if it exists (dev releases are ephemeral)
    gh release delete "$DEV_TAG" --yes --repo "$GITHUB_REPO" 2>/dev/null || true
    
    # Create new release
    gh release create "$DEV_TAG" \
      --repo "$GITHUB_REPO" \
      --title "Dev Build $DEV_TAG" \
      --notes "Automated development build from commit $SHORT_SHA on branch $CURRENT_BRANCH" \
      --prerelease \
      "$dist_dir"/*.whl
    
    log_success "Wheels published to GitHub release: $DEV_TAG"
  else
    log_info "Skipping wheel upload (--skip-push)"
  fi
  
  log_success "Python wheels built: $wheels_built"
}

# =============================================================================
# Docker Image Building
# =============================================================================

build_docker_images() {
  if [ "$SKIP_DOCKER" = true ]; then
    log_section "Skipping Docker Images (--skip-docker)"
    return 0
  fi
  
  log_section "Building Docker Images"
  
  local images_built=0
  
  for service_def in "${SERVICES[@]}"; do
    IFS=':' read -r service_name dockerfile <<< "$service_def"
    
    # Check if service needs rebuilding
    local dockerfile_path="$WORKSPACE_ROOT/$dockerfile"
    local service_dir=$(dirname "$dockerfile_path")
    
    if ! has_changes "$(basename "$service_dir")"; then
      log_info "Skipping $service_name (no changes)"
      continue
    fi
    
    log_info "Building $service_name..."
    
    # Build image with parent directory as context (to access sibling repos)
    # This allows pyproject.toml to reference ../marty-microservices-framework
    local parent_dir="$(cd "$WORKSPACE_ROOT/.." && pwd)"
    local dockerfile_rel="Marty/$dockerfile"
    
    # Change to parent directory for build context to work properly
    (
      cd "$parent_dir"
      docker buildx build \
        --no-cache \
        --platform linux/amd64 \
        --file "$dockerfile_rel" \
        --tag "${GHCR_PREFIX}/${service_name}:latest" \
        --tag "${GHCR_PREFIX}/${service_name}:${DEV_TAG}" \
        --cache-to type=inline \
        --load \
        .
    )
    
    log_success "$service_name built"
    ((images_built++))
    
    # Push if not skipped
    if [ "$SKIP_PUSH" = false ]; then
      log_info "Pushing $service_name to GHCR..."
      docker push "${GHCR_PREFIX}/${service_name}:latest"
      docker push "${GHCR_PREFIX}/${service_name}:${DEV_TAG}"
      log_success "$service_name pushed"
    fi
  done
  
  if [ $images_built -eq 0 ]; then
    log_warning "No images needed rebuilding"
    return 0
  fi
  
  log_success "Docker images built: $images_built"
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
  log_section "Marty Local Build & Push"
  log_info "Workspace: $WORKSPACE_ROOT"
  log_info "Current SHA: $SHORT_SHA"
  log_info "Dev Tag: $DEV_TAG"
  log_info "GHCR Prefix: $GHCR_PREFIX"
  
  if [ "$FORCE_BUILD" = true ]; then
    log_warning "Force build enabled - will rebuild all services"
  fi
  
  check_prerequisites
  
  # Track build start time
  local start_time=$(date +%s)
  
  # Build Python wheels
  build_python_wheels
  
  # Build Docker images
  build_docker_images
  
  # Update build marker on success
  echo "$CURRENT_SHA" > "$BUILD_MARKER"
  log_success "Build marker updated: $BUILD_MARKER"
  
  # Calculate build time
  local end_time=$(date +%s)
  local duration=$((end_time - start_time))
  local minutes=$((duration / 60))
  local seconds=$((duration % 60))
  
  log_section "Build Complete"
  log_success "Total build time: ${minutes}m ${seconds}s"
  log_info "Artifacts tagged: latest, $DEV_TAG"
  
  if [ "$SKIP_PUSH" = false ]; then
    log_info "Next steps:"
    log_info "  - Pull images: make pull-latest"
    log_info "  - Update requirements: ./scripts/update-requirements.sh"
    log_info "  - Start services: docker compose up -d"
  else
    log_info "Images built locally only (--skip-push used)"
    log_info "To push: docker push ${GHCR_PREFIX}/SERVICE_NAME:TAG"
  fi
}

# Run main function
main "$@"
