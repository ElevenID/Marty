#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Semantic Release Helper Script
# =============================================================================
# Creates semantic version releases (v1.2.3) for Marty
# - Updates version in pyproject.toml and Cargo.toml files
# - Creates git tag
# - Forces rebuild of all services
# - Pushes versioned tags to GHCR
#
# Usage:
#   ./release-helper.sh [VERSION]
#
# Examples:
#   ./release-helper.sh 1.2.3
#   ./release-helper.sh          # Interactive mode
#
# =============================================================================

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

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

validate_version() {
  local version=$1
  if [[ ! $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    log_error "Invalid version format: $version"
    log_info "Expected format: X.Y.Z (e.g., 1.2.3)"
    return 1
  fi
  return 0
}

get_current_version() {
  # Try to get version from pyproject.toml
  if [ -f "$WORKSPACE_ROOT/pyproject.toml" ]; then
    grep -E '^version = ' "$WORKSPACE_ROOT/pyproject.toml" | head -n1 | sed -E 's/version = "(.*)"/\1/'
  else
    echo "0.0.0"
  fi
}

update_version_files() {
  local version=$1
  log_info "Updating version to $version in project files..."
  
  # Update pyproject.toml
  if [ -f "$WORKSPACE_ROOT/pyproject.toml" ]; then
    if command -v gsed >/dev/null 2>&1; then
      gsed -i "s/^version = \".*\"/version = \"$version\"/" "$WORKSPACE_ROOT/pyproject.toml"
    else
      sed -i '' "s/^version = \".*\"/version = \"$version\"/" "$WORKSPACE_ROOT/pyproject.toml"
    fi
    log_success "Updated pyproject.toml"
  fi
  
  # Update related project versions
  for project in marty-credentials marty-microservices-framework marty-core; do
    local project_path="$WORKSPACE_ROOT/../$project"
    
    # Update pyproject.toml if exists
    if [ -f "$project_path/pyproject.toml" ]; then
      if command -v gsed >/dev/null 2>&1; then
        gsed -i "s/^version = \".*\"/version = \"$version\"/" "$project_path/pyproject.toml"
      else
        sed -i '' "s/^version = \".*\"/version = \"$version\"/" "$project_path/pyproject.toml"
      fi
      log_success "Updated $project/pyproject.toml"
    fi
    
    # Update Cargo.toml if exists
    if [ -f "$project_path/Cargo.toml" ]; then
      if command -v gsed >/dev/null 2>&1; then
        gsed -i "0,/^version = \".*\"/s//version = \"$version\"/" "$project_path/Cargo.toml"
      else
        sed -i '' "1,/^version = \".*\"/s//version = \"$version\"/" "$project_path/Cargo.toml"
      fi
      log_success "Updated $project/Cargo.toml"
    fi
  done
}

create_git_tag() {
  local version=$1
  local tag="v$version"
  
  log_info "Creating git tag: $tag"
  
  # Check if tag already exists
  if git -C "$WORKSPACE_ROOT" tag -l | grep -q "^$tag$"; then
    log_error "Tag $tag already exists"
    log_info "Delete it first with: git tag -d $tag && git push origin :refs/tags/$tag"
    return 1
  fi
  
  # Commit version changes
  git -C "$WORKSPACE_ROOT" add -A
  git -C "$WORKSPACE_ROOT" commit -m "chore: bump version to $version" || log_warning "No changes to commit"
  
  # Create tag
  git -C "$WORKSPACE_ROOT" tag -a "$tag" -m "Release $version"
  log_success "Created tag: $tag"
  
  # Ask to push
  read -p "Push tag to origin? (Y/n): " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    git -C "$WORKSPACE_ROOT" push origin "$tag"
    git -C "$WORKSPACE_ROOT" push origin HEAD
    log_success "Pushed tag and commits to origin"
  else
    log_info "Tag not pushed. Push manually with: git push origin $tag"
  fi
  
  return 0
}

build_and_push_release() {
  local version=$1
  
  log_section "Building Release Artifacts"
  
  # Force full rebuild
  rm -f "$WORKSPACE_ROOT/.last-build-sha"
  
  log_info "Building all services with version tags..."
  
  # Run build script with version tag override
  export RELEASE_VERSION="v$version"
  
  "$SCRIPT_DIR/build-all-local.sh" --force
  
  log_success "Release build complete"
  
  # Also tag with semantic version
  log_info "Tagging images with v$version..."
  
  GITHUB_REPO=$(git -C "$WORKSPACE_ROOT" remote get-url origin | sed -E 's/.*[:/]([^/]+\/[^/]+)(\.git)?$/\1/')
  GHCR_PREFIX="ghcr.io/${GITHUB_REPO}"
  
  SERVICES=(
    "csca-service"
    "document-signer"
    "dtc-engine"
    "inspection-system"
    "mdl-engine"
    "mdoc-engine"
    "passport-engine"
    "pkd-service"
    "trust-anchor"
    "ui-app"
  )
  
  for service in "${SERVICES[@]}"; do
    docker tag "${GHCR_PREFIX}/${service}:latest" "${GHCR_PREFIX}/${service}:v${version}"
    docker push "${GHCR_PREFIX}/${service}:v${version}"
    log_success "Tagged and pushed ${service}:v${version}"
  done
}

main() {
  log_section "Semantic Release Helper"
  
  # Get version from argument or prompt
  local version=""
  
  if [ $# -eq 1 ]; then
    version=$1
  else
    local current_version=$(get_current_version)
    log_info "Current version: $current_version"
    log_info ""
    log_info "Enter new version (X.Y.Z format):"
    read -r version
  fi
  
  # Validate version format
  if ! validate_version "$version"; then
    exit 1
  fi
  
  # Confirm
  log_warning "This will:"
  log_warning "  - Update version to $version in all project files"
  log_warning "  - Create git tag v$version"
  log_warning "  - Rebuild all services (full rebuild)"
  log_warning "  - Push versioned images to GHCR"
  log_warning ""
  read -p "Continue? (y/N): " -n 1 -r
  echo
  
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Aborted"
    exit 0
  fi
  
  # Update version files
  update_version_files "$version"
  
  # Create git tag
  if ! create_git_tag "$version"; then
    exit 1
  fi
  
  # Build and push
  build_and_push_release "$version"
  
  log_section "Release Complete"
  log_success "Version $version released successfully"
  log_info ""
  log_info "Artifacts available at:"
  log_info "  - GitHub Release: https://github.com/${GITHUB_REPO}/releases/tag/v${version}"
  log_info "  - GHCR Images: ghcr.io/${GITHUB_REPO}/SERVICE:v${version}"
}

main "$@"
