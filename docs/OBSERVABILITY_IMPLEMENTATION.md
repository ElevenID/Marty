# Marty Observability Implementation Summary

> **Historical record:** This summarizes observability work for the retired
> Python microservice runtime. It is not a current implementation or operations
> guide. Do not use the removed runtime paths; shared Rust observability is
> provided by the canonical MMF crates and `marty-ui` services.

## Overview

This implementation provides a comprehensive observability solution for the Marty microservices platform, focusing on "Observability you can trust" with metrics, tracing, and logs.

## What Was Implemented

### 1. OpenTelemetry Tracing with OTLP Export ✅

**File**: `src/marty_common/otel.py`

- **Environment-driven configuration**: Toggle tracing with `OTEL_TRACING_ENABLED`
- **OTLP exporter**: Ships traces to any OTLP-compatible backend (Jaeger, Zipkin, etc.)
- **Resource attribution**: Automatic service identification with namespace, version, environment
- **Flexible exporters**: OTLP for production, console for debugging
- **gRPC instrumentation**: Automatic client/server span creation
- **Utility functions**: Easy span creation, trace ID extraction, exception recording

**Key Environment Variables**:

```bash
OTEL_TRACING_ENABLED=true|false          # Master toggle
OTEL_SERVICE_NAME=your-service           # Service identification
OTEL_EXPORTER_OTLP_ENDPOINT=http://...   # Where to send traces
OTEL_CONSOLE_EXPORT=true|false          # Debug output
```

### 2. gRPC Auto-Instrumentation ✅

**File**: `src/apps/runtime.py`

- **Server instrumentation**: Automatic span creation for all gRPC service calls
- **Client instrumentation**: Automatic span creation for outbound gRPC calls
- **Centralized setup**: All services get tracing via the runtime framework
- **No code changes required**: Existing services automatically traced

**Implementation**:

```python
# Initialize tracing with service-specific name
init_tracing(service.name)

# Auto-instrument all gRPC traffic
instrument_grpc()
```

### 3. Structured Logging with Trace Correlation ✅

**File**: `src/marty_common/logging_config.py` (Already implemented!)

- **JSON structured logs**: Machine-readable log format
- **Trace correlation**: Automatic `trace_id` and `span_id` injection
- **Service identification**: Every log includes service name
- **OpenTelemetry integration**: Uses current span context automatically

**JSON Log Format**:

```json
{
  "timestamp": "2025-01-04T10:30:45.123456",
  "level": "INFO",
  "service": "passport-engine",
  "logger": "passport.validation",
  "message": "Document validation completed",
  "trace_id": "1234567890abcdef1234567890abcdef",
  "span_id": "abcdef1234567890",
  "module": "validation",
  "function": "validate_document"
}
```

### 4. Local Development Tracing Backend ✅

**Files**:

- `monitoring/jaeger/docker-compose.yml`
- `monitoring/jaeger/otel-collector.yml`
- `monitoring/jaeger/README.md`

- **Jaeger All-in-One**: Complete tracing backend for development
- **OTLP endpoints**: Both gRPC (4317) and HTTP (4318) receivers
- **Optional OTEL Collector**: Advanced processing and routing
- **Health checks**: Reliable startup and monitoring
- **Documentation**: Complete setup and usage guide

**Quick Start**:

```bash
cd monitoring/jaeger
docker-compose up -d
# Jaeger UI available at: http://localhost:16686
```

### 5. Helm/Kubernetes Integration ✅

**File**: `helm/values.yaml` (Previous todo - already completed)

- **OTLP routing**: Production-ready trace shipping
- **Environment variables**: Proper configuration management
- **Service mesh ready**: Compatible with Istio, Linkerd, etc.

### 6. Dependencies Management ✅

**File**: `pyproject.toml` (Already included!)

Required OpenTelemetry packages are already present:

- `opentelemetry-distro>=0.45b0`
- `opentelemetry-exporter-otlp-proto-grpc>=1.24.0`
- `opentelemetry-instrumentation-grpc>=0.45b0`

## Key Benefits

### 1. **Distributed Tracing**

- Track requests across all Marty microservices
- Identify performance bottlenecks and failures
- Understand service dependencies and call patterns

### 2. **Correlated Observability**

- Every log message includes trace context
- Easy correlation between logs, traces, and metrics
- Single pane of glass for debugging

### 3. **Zero Code Changes**

- Existing services automatically get tracing
- Configuration-driven observability
- No modification to business logic required

### 4. **Production Ready**

- Environment-based configuration
- Efficient OTLP export to any backend
- Configurable sampling and resource limits

### 5. **Developer Friendly**

- Local Jaeger setup for immediate feedback
- Console export for debugging
- Comprehensive documentation

## Usage Examples

### Enable Tracing for a Service

```bash
# Set environment variables
export OTEL_TRACING_ENABLED=true
export OTEL_SERVICE_NAME=passport-engine
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Start service (tracing happens automatically)
python -m apps.passport_engine
```

### View Traces Locally

```bash
# Start observability stack
cd monitoring/jaeger
docker-compose up -d

# Generate some traffic
# View traces at: http://localhost:16686
```

### Add Custom Spans

```python
from marty_common.otel import create_span, set_span_attribute

# Manual span creation
with create_span("document.validation", document_type="passport") as span:
    result = validate_document(doc)
    set_span_attribute("validation.result", result.status)
```

### Production Deployment

```bash
# Deploy with Helm
helm upgrade --install marty ./helm \
  --set otel.enabled=true \
  --set otel.endpoint=https://your-otlp-collector:4317
```

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Passport      │    │      mDL        │    │   Inspection    │
│   Engine        │    │    Engine       │    │    System       │
│                 │    │                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │  OTEL Auto  │ │    │ │  OTEL Auto  │ │    │ │  OTEL Auto  │ │
│ │ Instrument  │ │    │ │ Instrument  │ │    │ │ Instrument  │ │
│ └─────────────┘ │    │ └─────────────┘ │    │ └─────────────┘ │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          │              ┌───────▼─────────┐            │
          └──────────────►│  OTLP Endpoint  │◄───────────┘
                         │  (Jaeger/OTEL)  │
                         └─────────────────┘
                                 │
          ┌─────────────────────────────────────────┐
          │           Jaeger UI / Backend           │
          │     • Trace visualization              │
          │     • Service maps                     │
          │     • Performance analysis             │
          │     • Dependency graphs                │
          └─────────────────────────────────────────┘
```

## Next Steps

1. **Start local development**: Use `docker-compose up -d` in monitoring/jaeger
2. **Test trace generation**: Run services with `OTEL_TRACING_ENABLED=true`
3. **Explore Jaeger UI**: Visit <http://localhost:16686> to see traces
4. **Add custom spans**: Instrument business logic with domain-specific spans
5. **Production deployment**: Configure OTLP endpoint for your production tracing backend

The Marty platform now has comprehensive, production-ready observability that provides deep insights into microservice behavior, performance, and dependencies.
