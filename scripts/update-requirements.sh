#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Update Requirements Script
# =============================================================================
# Updates requirements.txt to use the latest GitHub release artifact URLs
# for marty Python packages
#
# Usage:
#   ./update-requirements.sh [OPTIONS]
#
# Options:
#   --release TAG    Use specific release tag (default: latest dev release)
#   --output FILE    Output file path (default: ../marty-ui/src/requirements.txt)
#   --dry-run        Print URLs without modifying files
#   --help           Show this help message
#
# Prerequisites:
#   - gh CLI (GitHub CLI) installed and authenticated
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

# Default options
RELEASE_TAG=""
OUTPUT_FILE="$WORKSPACE_ROOT/../marty-ui/src/requirements.txt"
DRY_RUN=false

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

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --release)
      RELEASE_TAG="$2"
      shift 2
      ;;
    --output)
      OUTPUT_FILE="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --help)
      head -n 20 "$0" | grep "^#" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      log_error "Unknown option: $1"
      exit 1
      ;;
  esac
done

get_latest_release() {
  local repo=$1
  
  # Get latest prerelease (dev builds)
  local latest=$(gh release list --repo "$repo" --limit 1 --exclude-drafts --json tagName,isPrerelease --jq '.[] | select(.isPrerelease == true) | .tagName' 2>/dev/null || echo "")
  
  if [ -z "$latest" ]; then
    log_error "No prerelease found for $repo"
    return 1
  fi
  
  echo "$latest"
}

get_wheel_url() {
  local repo=$1
  local release=$2
  local package_prefix=$3
  
  # List release assets and find the appropriate wheel for linux/amd64
  local wheel=$(gh release view "$release" --repo "$repo" --json assets --jq '.assets[].name' | grep -E "${package_prefix}.*-cp3[0-9]+-.*-manylinux.*_x86_64\.whl" | head -n1)
  
  if [ -z "$wheel" ]; then
    log_error "No wheel found for $package_prefix in $repo@$release"
    return 1
  fi
  
  echo "https://github.com/$repo/releases/download/$release/$wheel"
}

main() {
  log_section "Update Python Package Requirements"
  
  # Check gh CLI is installed
  if ! command -v gh >/dev/null 2>&1; then
    log_error "gh CLI not installed. Install with: brew install gh"
    exit 1
  fi
  
  # Check gh authentication
  if ! gh auth status >/dev/null 2>&1; then
    log_error "Not authenticated to GitHub. Run: gh auth login"
    exit 1
  fi
  
  # Determine release tag
  if [ -z "$RELEASE_TAG" ]; then
    log_info "Finding latest dev release..."
    
    # Extract GitHub repo from git remote
    GITHUB_REPO=$(git -C "$WORKSPACE_ROOT" remote get-url origin | sed -E 's/.*[:/]([^/]+\/[^/]+)(\.git)?$/\1/')
    
    # Get latest release from main Marty repo (assuming wheels are published there)
    RELEASE_TAG=$(get_latest_release "$GITHUB_REPO")
    
    if [ -z "$RELEASE_TAG" ]; then
      log_error "Could not find latest release"
      exit 1
    fi
    
    log_info "Using release: $RELEASE_TAG"
  fi
  
  # Get wheel URLs for each package
  log_info "Fetching wheel URLs..."
  
  # Extract org/user from repo
  GITHUB_ORG=$(echo "$GITHUB_REPO" | cut -d'/' -f1)
  
  # Define package repos and wheel prefixes
  declare -A PACKAGES=(
    ["marty-rs"]="$GITHUB_ORG/marty-credentials:marty_rs"
    ["marty-msf"]="$GITHUB_ORG/marty-microservices-framework:marty_msf"
    ["marty-common"]="$GITHUB_REPO:marty_common"
  )
  
  declare -A WHEEL_URLS
  
  for package in "${!PACKAGES[@]}"; do
    IFS=':' read -r repo prefix <<< "${PACKAGES[$package]}"
    
    log_info "Fetching $package from $repo..."
    
    # Get latest release for this specific repo if needed
    local pkg_release="$RELEASE_TAG"
    if [ "$repo" != "$GITHUB_REPO" ]; then
      pkg_release=$(get_latest_release "$repo" || echo "$RELEASE_TAG")
    fi
    
    local url=$(get_wheel_url "$repo" "$pkg_release" "$prefix")
    
    if [ -n "$url" ]; then
      WHEEL_URLS[$package]=$url
      log_success "$package: $url"
    else
      log_warning "Could not find wheel for $package"
    fi
  done
  
  if [ ${#WHEEL_URLS[@]} -eq 0 ]; then
    log_error "No wheels found"
    exit 1
  fi
  
  # Generate requirements.txt content
  log_section "Updating Requirements"
  
  if [ "$DRY_RUN" = true ]; then
    log_info "Dry run mode - would update:"
    log_info "  File: $OUTPUT_FILE"
    log_info ""
    log_info "Package URLs:"
    for package in "${!WHEEL_URLS[@]}"; do
      echo "  $package @ ${WHEEL_URLS[$package]}"
    done
    exit 0
  fi
  
  # Read existing requirements.txt
  if [ ! -f "$OUTPUT_FILE" ]; then
    log_error "Requirements file not found: $OUTPUT_FILE"
    exit 1
  fi
  
  # Create backup
  cp "$OUTPUT_FILE" "${OUTPUT_FILE}.backup"
  log_info "Backup created: ${OUTPUT_FILE}.backup"
  
  # Update file - replace or add marty package URLs
  local temp_file=$(mktemp)
  
  # Copy non-marty lines
  grep -v "^marty-" "$OUTPUT_FILE" > "$temp_file" || true
  
  # Add updated marty packages
  echo "" >> "$temp_file"
  echo "# Marty packages from GitHub Release: $RELEASE_TAG" >> "$temp_file"
  for package in "${!WHEEL_URLS[@]}"; do
    echo "$package @ ${WHEEL_URLS[$package]}" >> "$temp_file"
  done
  
  # Replace original file
  mv "$temp_file" "$OUTPUT_FILE"
  
  log_success "Updated: $OUTPUT_FILE"
  log_info ""
  log_info "To revert: mv ${OUTPUT_FILE}.backup $OUTPUT_FILE"
  log_info ""
  log_info "Next steps:"
  log_info "  1. Test locally: pip install -r $OUTPUT_FILE"
  log_info "  2. Rebuild UI: make build-ui"
  log_info "  3. Commit changes: git add $OUTPUT_FILE && git commit -m 'chore: update marty packages to $RELEASE_TAG'"
}

main "$@"
