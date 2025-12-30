#!/bin/bash
# Docker build script for DRY Marty services
# This script builds the base image and all service images efficiently

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
BASE_TAG="marty-base:latest"
REGISTRY=""
PUSH=false
PARALLEL=false

# Services that have been converted to use base image
DRY_SERVICES=(
    "csca-service:8081"
    "passport-engine:8084"
    "mdl-engine:8085"
)

# Services that still use individual Dockerfiles (not yet converted)
LEGACY_SERVICES=(
    "document-signer:8082"
    "trust-anchor:8080"
    "inspection-system:8083"
    "mdoc-engine:8086"
    "dtc-engine:8087"
    "open-badges:8091"
    "pkd-service:8088"
    "ui-app:3000"
)

usage() {
    cat << EOF
Usage: $0 [OPTIONS] [SERVICES...]

Build Docker images for Marty services using DRY principles.

OPTIONS:
    -h, --help          Show this help message
    -b, --base-only     Build only the base image
    -l, --legacy        Build legacy services (not using base image)
    -r, --registry      Registry prefix (e.g., docker.io/myorg)
    -p, --push          Push images to registry after building
    -t, --tag           Tag for base image (default: marty-base:latest)
    --parallel          Build services in parallel
    --list              List available services

SERVICES:
    If no services specified, builds all DRY services.
    Use 'all' to build all services including legacy.

Examples:
    $0                              # Build base + all DRY services
    $0 -b                          # Build only base image
    $0 csca-service passport-engine # Build specific services
    $0 -l                          # Build legacy services
    $0 all                         # Build everything
    $0 -r my-registry.com/marty -p # Build and push to registry
EOF
}

log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1" >&2
}

warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

build_base_image() {
    log "Building base image: $BASE_TAG"

    if docker build -f docker/base.Dockerfile -t "$BASE_TAG" .; then
        success "Base image built successfully"

        if [ "$PUSH" = true ] && [ -n "$REGISTRY" ]; then
            REGISTRY_TAG="${REGISTRY}/marty-base:latest"
            docker tag "$BASE_TAG" "$REGISTRY_TAG"
            log "Pushing base image to registry: $REGISTRY_TAG"
            docker push "$REGISTRY_TAG"
            success "Base image pushed to registry"
        fi
    else
        error "Failed to build base image"
        exit 1
    fi
}

build_dry_service() {
    local service_spec=$1
    local service_name=$(echo "$service_spec" | cut -d: -f1)
    local service_port=$(echo "$service_spec" | cut -d: -f2)

    local image_name="marty-${service_name}:latest"
    if [ -n "$REGISTRY" ]; then
        image_name="${REGISTRY}/marty-${service_name}:latest"
    fi

    log "Building DRY service: $service_name (port $service_port)"

    # Use the DRY Dockerfile for this service
    local dockerfile="docker/${service_name}.Dockerfile"

    if [ ! -f "$dockerfile" ]; then
        error "Dockerfile not found: $dockerfile"
        return 1
    fi

    if docker build \
        --build-arg BASE_IMAGE="$BASE_TAG" \
        --build-arg SERVICE_NAME="$service_name" \
        --build-arg SERVICE_PORT="$service_port" \
        -f "$dockerfile" \
        -t "$image_name" \
        .; then
        success "Built $service_name successfully"

        if [ "$PUSH" = true ]; then
            log "Pushing $service_name to registry"
            docker push "$image_name"
            success "Pushed $service_name to registry"
        fi
    else
        error "Failed to build $service_name"
        return 1
    fi
}

build_legacy_service() {
    local service_spec=$1
    local service_name=$(echo "$service_spec" | cut -d: -f1)

    local image_name="marty-${service_name}:latest"
    if [ -n "$REGISTRY" ]; then
        image_name="${REGISTRY}/marty-${service_name}:latest"
    fi

    log "Building legacy service: $service_name"

    local dockerfile="docker/${service_name}.Dockerfile"

    if [ ! -f "$dockerfile" ]; then
        error "Dockerfile not found: $dockerfile"
        return 1
    fi

    if docker build -f "$dockerfile" -t "$image_name" .; then
        success "Built $service_name successfully"

        if [ "$PUSH" = true ]; then
            log "Pushing $service_name to registry"
            docker push "$image_name"
            success "Pushed $service_name to registry"
        fi
    else
        error "Failed to build $service_name"
        return 1
    fi
}

list_services() {
    echo "DRY Services (using base image):"
    for service in "${DRY_SERVICES[@]}"; do
        service_name=$(echo "$service" | cut -d: -f1)
        service_port=$(echo "$service" | cut -d: -f2)
        echo "  - $service_name (port $service_port)"
    done

    echo
    echo "Legacy Services (individual Dockerfiles):"
    for service in "${LEGACY_SERVICES[@]}"; do
        service_name=$(echo "$service" | cut -d: -f1)
        service_port=$(echo "$service" | cut -d: -f2)
        echo "  - $service_name (port $service_port)"
    done
}

# Parse command line arguments
BASE_ONLY=false
LEGACY_ONLY=false
LIST_ONLY=false
SERVICES_TO_BUILD=()

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        -b|--base-only)
            BASE_ONLY=true
            shift
            ;;
        -l|--legacy)
            LEGACY_ONLY=true
            shift
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -p|--push)
            PUSH=true
            shift
            ;;
        -t|--tag)
            BASE_TAG="$2"
            shift 2
            ;;
        --parallel)
            PARALLEL=true
            shift
            ;;
        --list)
            LIST_ONLY=true
            shift
            ;;
        all)
            SERVICES_TO_BUILD=("${DRY_SERVICES[@]}" "${LEGACY_SERVICES[@]}")
            shift
            ;;
        *)
            SERVICES_TO_BUILD+=("$1")
            shift
            ;;
    esac
done

# Handle special modes
if [ "$LIST_ONLY" = true ]; then
    list_services
    exit 0
fi

# Validate registry format if pushing
if [ "$PUSH" = true ] && [ -n "$REGISTRY" ]; then
    if [[ ! "$REGISTRY" =~ ^[a-zA-Z0-9.-]+(/[a-zA-Z0-9._-]+)*$ ]]; then
        error "Invalid registry format: $REGISTRY"
        exit 1
    fi
fi

# Main execution
log "Starting Docker build process"
log "Base tag: $BASE_TAG"
if [ -n "$REGISTRY" ]; then
    log "Registry: $REGISTRY"
fi
if [ "$PUSH" = true ]; then
    log "Will push images to registry"
fi

# Build base image unless we're only building legacy services
if [ "$LEGACY_ONLY" = false ]; then
    build_base_image
fi

# Exit if only building base image
if [ "$BASE_ONLY" = true ]; then
    success "Base image build complete"
    exit 0
fi

# Determine which services to build
if [ ${#SERVICES_TO_BUILD[@]} -eq 0 ]; then
    if [ "$LEGACY_ONLY" = true ]; then
        SERVICES_TO_BUILD=("${LEGACY_SERVICES[@]}")
    else
        SERVICES_TO_BUILD=("${DRY_SERVICES[@]}")
    fi
fi

# Build services
failed_services=()

for service_spec in "${SERVICES_TO_BUILD[@]}"; do
    service_name=$(echo "$service_spec" | cut -d: -f1)

    # Check if this is a DRY service
    is_dry=false
    for dry_service in "${DRY_SERVICES[@]}"; do
        if [[ "$dry_service" == "$service_spec" ]] || [[ "$dry_service" == "$service_name:*" ]]; then
            is_dry=true
            break
        fi
    done

    if [ "$is_dry" = true ]; then
        if [ "$LEGACY_ONLY" = false ]; then
            if ! build_dry_service "$service_spec"; then
                failed_services+=("$service_name")
            fi
        fi
    else
        if ! build_legacy_service "$service_spec"; then
            failed_services+=("$service_name")
        fi
    fi
done

# Summary
echo
if [ ${#failed_services[@]} -eq 0 ]; then
    success "All builds completed successfully!"
else
    error "The following services failed to build:"
    for service in "${failed_services[@]}"; do
        echo "  - $service"
    done
    exit 1
fi
