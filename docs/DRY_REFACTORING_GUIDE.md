# DRY Refactoring Implementation Guide

This document describes the DRY (Don't Repeat Yourself) refactoring implemented in the Marty project to reduce code duplication and improve maintainability.

## Overview

The refactoring addressed several areas of redundancy:

1. **gRPC Server Setup** - Standardized server initialization across all services
2. **Docker Configurations** - Shared base images and templates
3. **Configuration Management** - Centralized configuration loading
4. **Verification Patterns** - Common verification engine patterns
5. **Logging Setup** - Standardized logging configuration

## New Shared Utilities

### 1. gRPC Server Framework (`marty_common/grpc_server.py`)

**Before:** Each service had its own server setup with ~50 lines of duplicated code:

```python
def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = MyServicer()
    add_MyServicer_to_server(servicer, server)

    # Add logging streamer
    try:
        logging_streamer = LoggingStreamerServicer()
        add_LoggingStreamerServicer_to_server(logging_streamer, server)
    except Exception as e:
        logger.error(f"Failed to add LoggingStreamerServicer: {e}")

    server.add_insecure_port(f"[::]:{port}")
    server.start()
    # ... signal handling, shutdown logic
```

**After:** Single line service startup:

```python
from marty_common.grpc_server import run_grpc_service

def main():
    run_grpc_service(
        service_name="my_service",
        servicer_class=MyServicer,
        add_servicer_func=add_MyServicer_to_server
    )
```

**Benefits:**

- Reduced from ~50 lines to ~5 lines per service
- Consistent error handling and graceful shutdown
- Standardized health checks and logging integration
- Centralized configuration management

### 2. Configuration Management (`marty_common/config_manager.py`)

**Before:** Each service loaded configuration differently:

```python
# Various patterns across services
config_env = os.environ.get("ENV", "development")
config = Config(config_env)
port = os.environ.get("GRPC_PORT", "50051")
# ... scattered configuration logic
```

**After:** Standardized configuration:

```python
from marty_common.config_manager import get_service_config

def __init__(self):
    self.config = get_service_config("my_service")
    # Config includes all standard settings with environment overrides
```

**Benefits:**

- Consistent configuration structure across all services
- Environment variable override support
- Validation and error handling
- Service discovery integration

### 3. Native Verification Kernels

Deterministic document verification is consolidated in the canonical Rust
crates. Python services map requests and native typed results, but do not
inherit from or implement a shared Python verification engine. New verification
behavior belongs in the canonical Rust owner and its generated bindings.

### 4. Docker Infrastructure

**Before:** 12 nearly identical Dockerfiles with ~50 lines each:

```dockerfile
FROM python:3.10-slim
# 40+ lines of repeated dependency installation
COPY pyproject.toml uv.lock /app/
RUN pip install uv && uv pip install --system -e .
# ... repeated patterns across all services
```

**After:** Shared base image + service template:

**Base Image (`docker/base.Dockerfile`):**

```dockerfile
FROM python:3.10-slim
# All common dependencies and setup
# Shared by all services
```

**Service Template (`docker/service.Dockerfile`):**

```dockerfile
ARG BASE_IMAGE=marty-base:latest
FROM ${BASE_IMAGE}
ARG SERVICE_NAME
COPY src/${SERVICE_NAME}/ /app/src/${SERVICE_NAME}/
ENV SERVICE_NAME=${SERVICE_NAME}
```

**Benefits:**

- Reduced Docker build time (shared layers)
- Consistent base environment
- Easier dependency management
- Smaller total image size

## Usage Examples

### Creating a New Service

1. **Create the servicer class:**

```python
# src/services/my_new_service.py
from marty_common.grpc_server import run_grpc_service
from marty_common.config_manager import get_service_config

class MyNewServiceServicer(MyNewServiceServicer):
    def __init__(self):
        self.config = get_service_config("my_new_service")
        self.logger = logging.getLogger(self.__class__.__name__)

def main():
    run_grpc_service(
        service_name="my_new_service",
        servicer_class=MyNewServiceServicer,
        add_servicer_func=add_MyNewServiceServicer_to_server
    )
```

2. **Add configuration (optional):**

```yaml
# config/my_new_service.yaml
grpc_port: 8090
max_workers: 15
enable_metrics: true
```

3. **Build with shared infrastructure:**

```bash
./scripts/build-services.sh --service my-new-service
```

### Adding Verification Behavior

Extend the canonical Rust crate, add shared golden vectors, expose the operation
through the generated native binding, and keep the Python caller limited to
request/result mapping. Required native operations must fail closed when they
are unavailable.

## Migration Guide

### Updating Existing Services

1. **Replace server setup:**

```python
# Old
def serve():
    # 50+ lines of server setup

# New  
def main():
    run_grpc_service(
        service_name="service_name",
        servicer_class=ServicerClass,
        add_servicer_func=add_ServicerClass_to_server
    )
```

2. **Update configuration:**

```python
# Old
config_env = os.environ.get("ENV", "development")
config = Config(config_env)

# New
config = get_service_config("service_name")
```

3. **Update Dockerfile:**

```dockerfile
# Old: Copy entire service-specific Dockerfile

# New: Use service template
ARG BASE_IMAGE=marty-base:latest
FROM ${BASE_IMAGE}
ARG SERVICE_NAME
COPY src/${SERVICE_NAME}/ /app/src/${SERVICE_NAME}/
ENV SERVICE_NAME=${SERVICE_NAME}
```

## Build System

The new build system supports:

```bash
# Build everything
./scripts/build-services.sh

# Build base image only
./scripts/build-services.sh --no-services

# Build specific service
./scripts/build-services.sh --service mdoc-engine

# Build and push to registry
./scripts/build-services.sh --registry myregistry.com --push --tag v1.0.0
```

## Metrics

### Lines of Code Reduction

| Area | Before | After | Reduction |
|------|--------|-------|-----------|
| gRPC server setup | ~600 lines (12 services × 50) | ~60 lines (shared utility) | **90%** |
| Docker configurations | ~600 lines (12 files × 50) | ~80 lines (base + template) | **87%** |
| Verification engines | ~400 lines duplicated | ~100 lines (shared base) | **75%** |
| Configuration loading | ~150 lines scattered | ~50 lines (centralized) | **67%** |
| **Total** | **~1,750 lines** | **~290 lines** | **83%** |

### Maintenance Benefits

- **Consistency**: All services now follow the same patterns
- **Testing**: Shared utilities can be unit tested once
- **Updates**: Changes to common patterns only need to be made in one place
- **Onboarding**: New developers learn one pattern, not 12 different ones
- **Debugging**: Standardized logging and error handling

## Future Improvements

1. **Service Templates**: Generate new services from templates
2. **Shared Testing Utilities**: Common test patterns and fixtures
3. **Monitoring Integration**: Standardized metrics and tracing
4. **API Gateway**: Centralized routing and authentication
5. **Service Mesh**: Advanced traffic management and security

## Dependencies

The refactoring maintains backward compatibility and doesn't introduce new external dependencies. All shared utilities use existing dependencies already present in the project.
