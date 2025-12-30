#!/bin/bash
# Build script for Marty services using shared Docker infrastructure
# This demonstrates how to build all services with minimal duplication

set -euo pipefail

# Default values
BUILD_BASE=${BUILD_BASE:-true}
BUILD_SERVICES=${BUILD_SERVICES:-true}
REGISTRY=${REGISTRY:-""}
TAG=${TAG:-latest}
PUSH=${PUSH:-false}

# Service definitions
declare -A SERVICES=(
    ["mdoc-engine"]="8086"
    ["passport-engine"]="8084"
    ["dtc-engine"]="8087"
    ["open-badges"]="8091"
    ["csca-service"]="8081"
    ["document-signer"]="8082"
    ["inspection-system"]="8083"
    ["trust-anchor"]="8080"
    ["pkd-service"]="8088"
    ["mdl-engine"]="8089"
    ["ui-app"]="3000"
)

function log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >&2
}

function build_base_image() {
    log "Building base image..."
    docker build \
        -f docker/base.Dockerfile \
        -t marty-base:${TAG} \
        .

    if [ "${PUSH}" = "true" ] && [ -n "${REGISTRY}" ]; then
        docker tag marty-base:${TAG} ${REGISTRY}/marty-base:${TAG}
        docker push ${REGISTRY}/marty-base:${TAG}
    fi

    log "Base image built successfully"
}

function build_service() {
    local service_name=$1
    local service_port=$2

    log "Building ${service_name} service..."

    local image_name="marty-${service_name}"
    local base_image="marty-base:${TAG}"

    if [ -n "${REGISTRY}" ]; then
        base_image="${REGISTRY}/marty-base:${TAG}"
    fi

    docker build \
        -f docker/service.Dockerfile \
        --build-arg BASE_IMAGE=${base_image} \
        --build-arg SERVICE_NAME=${service_name} \
        --build-arg SERVICE_PORT=${service_port} \
        -t ${image_name}:${TAG} \
        .

    if [ "${PUSH}" = "true" ] && [ -n "${REGISTRY}" ]; then
        docker tag ${image_name}:${TAG} ${REGISTRY}/${image_name}:${TAG}
        docker push ${REGISTRY}/${image_name}:${TAG}
    fi

    log "${service_name} service built successfully"
}

function build_all_services() {
    log "Building all services..."

    for service in "${!SERVICES[@]}"; do
        build_service "${service}" "${SERVICES[$service]}"
    done

    log "All services built successfully"
}

function main() {
    log "Starting Marty build process..."
    log "Build base: ${BUILD_BASE}"
    log "Build services: ${BUILD_SERVICES}"
    log "Registry: ${REGISTRY:-none}"
    log "Tag: ${TAG}"
    log "Push: ${PUSH}"

    if [ "${BUILD_BASE}" = "true" ]; then
        build_base_image
    fi

    if [ "${BUILD_SERVICES}" = "true" ]; then
        build_all_services
    fi

    log "Build process completed successfully"
}

# Handle command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-base)
            BUILD_BASE=false
            shift
            ;;
        --no-services)
            BUILD_SERVICES=false
            shift
            ;;
        --registry)
            REGISTRY="$2"
            shift 2
            ;;
        --tag)
            TAG="$2"
            shift 2
            ;;
        --push)
            PUSH=true
            shift
            ;;
        --service)
            # Build specific service only
            BUILD_BASE=false
            BUILD_SERVICES=false
            service_name="$2"
            if [[ -n "${SERVICES[$service_name]:-}" ]]; then
                build_service "$service_name" "${SERVICES[$service_name]}"
                exit 0
            else
                log "Error: Unknown service '$service_name'"
                log "Available services: ${!SERVICES[*]}"
                exit 1
            fi
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  --no-base          Skip building base image"
            echo "  --no-services      Skip building service images"
            echo "  --registry REG     Use registry prefix for images"
            echo "  --tag TAG          Tag for images (default: latest)"
            echo "  --push             Push images to registry"
            echo "  --service NAME     Build specific service only"
            echo "  --help             Show this help"
            echo ""
            echo "Available services: ${!SERVICES[*]}"
            exit 0
            ;;
        *)
            log "Unknown option: $1"
            exit 1
            ;;
    esac
done

main
