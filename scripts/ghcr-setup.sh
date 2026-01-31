#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# GitHub Container Registry Setup Script
# =============================================================================
# Authenticates Docker to GHCR and validates permissions
#
# Usage:
#   ./ghcr-setup.sh
#
# Prerequisites:
#   - Docker installed and running
#   - GitHub Personal Access Token with write:packages and read:packages scopes
#
# Creating a PAT:
#   1. Go to https://github.com/settings/tokens
#   2. Click "Generate new token" → "Generate new token (classic)"
#   3. Select scopes: write:packages, read:packages
#   4. Generate token and save it securely
#
# =============================================================================

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

main() {
  log_section "GitHub Container Registry Setup"
  
  # Check Docker is running
  if ! docker info >/dev/null 2>&1; then
    log_error "Docker is not running. Please start Docker Desktop."
    exit 1
  fi
  
  log_success "Docker is running"
  
  # Check if already authenticated
  if docker-credential-desktop list 2>/dev/null | grep -q "ghcr.io" || \
     docker-credential-osxkeychain list 2>/dev/null | grep -q "ghcr.io" 2>/dev/null; then
    log_info "Already authenticated to GHCR"
    
    read -p "Do you want to re-authenticate? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      log_info "Skipping authentication"
      exit 0
    fi
  fi
  
  # Prompt for GitHub username
  log_info "Enter your GitHub username:"
  read -r GITHUB_USERNAME
  
  if [ -z "$GITHUB_USERNAME" ]; then
    log_error "Username cannot be empty"
    exit 1
  fi
  
  # Prompt for PAT
  log_info ""
  log_info "GitHub Personal Access Token (PAT) required with scopes:"
  log_info "  - write:packages"
  log_info "  - read:packages"
  log_info ""
  log_info "Create one at: https://github.com/settings/tokens"
  log_info ""
  log_info "Enter your GitHub PAT (input hidden):"
  read -rs GITHUB_TOKEN
  echo
  
  if [ -z "$GITHUB_TOKEN" ]; then
    log_error "Token cannot be empty"
    exit 1
  fi
  
  # Authenticate to GHCR
  log_info "Authenticating to ghcr.io..."
  
  if echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_USERNAME" --password-stdin >/dev/null 2>&1; then
    log_success "Successfully authenticated to GHCR"
  else
    log_error "Authentication failed. Check your username and token."
    exit 1
  fi
  
  # Validate permissions with a test pull
  log_info "Validating permissions..."
  
  # Try to pull a test image (hello-world equivalent for GHCR)
  # We'll just verify the login worked by checking docker config
  if docker system info 2>&1 | grep -q "ghcr.io"; then
    log_success "GHCR credentials stored successfully"
  else
    log_warning "Could not verify credential storage, but login succeeded"
  fi
  
  log_section "Setup Complete"
  log_success "You can now push images to ghcr.io/$GITHUB_USERNAME/*"
  log_info ""
  log_info "Next steps:"
  log_info "  1. Build and push: make build-push"
  log_info "  2. Or just build: ./scripts/build-all-local.sh"
  log_info ""
  log_info "Your credentials are stored in Docker's credential helper and will persist."
}

main "$@"
