# Marty Platform Prometheus Monitoring Implementation

> **Historical record:** This document covers the retired Python microservice
> monitoring stack. It is not a current operations guide. Do not use its
> removed runtime, Helm, or deployment paths; current telemetry belongs to the
> Rust MMF observability crate and `marty-ui` release stack.

This document describes the comprehensive Prometheus monitoring implementation for the Marty microservices platform.

## 🎯 Overview

The Marty platform now includes full Prometheus monitoring capabilities with:

- **Automatic metrics collection** for all gRPC microservices
- **Health check endpoints** for Kubernetes liveness and readiness probes
- **Service discovery** for automatic Prometheus scraping
- **Comprehensive metrics** including request rates, latencies, errors, and resource usage

## 📊 Architecture

### Metrics Server

Each microservice automatically starts a dedicated metrics HTTP server that provides:

- **Prometheus metrics** at `/metrics`
- **Health status** at `/health`
- **Liveness probe** at `/health/live`
- **Readiness probe** at `/health/ready`

### Port Allocation

Each service uses a specific port layout:

- **gRPC Service**: Base port (e.g., 8081)
- **Health/Management**: Base port + 1 (e.g., 8082)
- **Metrics**: Base port + 1000 (e.g., 9081)

| Service | gRPC Port | Health Port | Metrics Port |
|---------|-----------|-------------|--------------|
| csca-service | 8081 | 8082 | 9081 |
| document-signer | 8082 | 8083 | 9082 |
| inspection-system | 8083 | 8084 | 9083 |
| passport-engine | 8084 | 8085 | 9084 |
| mdl-engine | 8085 | 8086 | 9085 |
| mdoc-engine | 8086 | 8087 | 9086 |
| trust-anchor | 9080 | 9081 | 10080 |
| pkd-service | 9090 | 9091 | 10090 |

## 🚀 Implementation Details

### 1. Dependencies Added

- `prometheus_client>=0.19.0` - Python Prometheus client library

### 2. Core Components

#### Metrics Server (`src/marty_common/metrics_server.py`)

- **ServiceMetrics**: Collects gRPC request metrics, error rates, resource usage
- **HealthChecker**: Manages health status for different components
- **MetricsServer**: FastAPI-based HTTP server for exposing metrics and health endpoints

#### gRPC Interceptors (`src/marty_common/grpc_metrics.py`)

- **AsyncMetricsInterceptor**: Automatically captures metrics for all gRPC calls
- Tracks request duration, success/error rates, method-specific metrics

#### Runtime Integration (`src/apps/runtime.py`)

- Automatic metrics server startup for all services
- Health check integration
- Graceful shutdown handling

### 3. Kubernetes Integration

#### Service Annotations

All services include Prometheus scraping annotations:

```yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "9081"  # Metrics port
  prometheus.io/path: "/metrics"
```

#### Health Probes

Kubernetes deployment templates include:

```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: health
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /health/ready
    port: health
  initialDelaySeconds: 5
  periodSeconds: 5
```

#### Service Discovery

Prometheus automatically discovers services using Kubernetes service discovery:

```yaml
- job_name: 'marty-microservices'
  kubernetes_sd_configs:
    - role: service
      namespaces:
        names: ['marty']
  relabel_configs:
    - source_labels: [__meta_kubernetes_service_annotation_prometheus_io_scrape]
      action: keep
      regex: true
```

## 📈 Available Metrics

### gRPC Metrics

- `marty_grpc_requests_total` - Total gRPC requests by service, method, and status
- `marty_grpc_request_duration_seconds` - Request duration histograms
- `marty_grpc_errors_total` - Total errors by service, method, and error type
- `marty_grpc_active_connections` - Number of active gRPC connections

### Health Metrics

- `marty_service_health_status` - Service health status (1=healthy, 0=unhealthy)
- `marty_last_successful_operation_timestamp` - Timestamp of last successful operation

### Resource Metrics

- `marty_service_cpu_usage_percent` - CPU usage percentage
- `marty_service_memory_usage_bytes` - Memory usage in bytes
- `marty_database_connections_active` - Active database connections

### Service Information

- `marty_service_info` - Service metadata (name, version, etc.)

## 🧪 Testing

### Automated Testing

Use the provided test script to verify all metrics endpoints:

```bash
# Test all services locally
python scripts/test_metrics.py

# Test specific service
curl http://localhost:9081/metrics
curl http://localhost:8082/health
```

### Expected Responses

#### Metrics Endpoint (`/metrics`)

```
# HELP marty_grpc_requests_total Total gRPC requests
# TYPE marty_grpc_requests_total counter
marty_grpc_requests_total{service="csca-service",method="/csca.CscaService/GetCertificate",status="OK"} 42.0

# HELP marty_grpc_request_duration_seconds gRPC request duration in seconds
# TYPE marty_grpc_request_duration_seconds histogram
marty_grpc_request_duration_seconds_bucket{service="csca-service",method="/csca.CscaService/GetCertificate",le="0.001"} 15.0
```

#### Health Endpoint (`/health`)

```json
{
  "service": "csca-service",
  "healthy": true,
  "ready": true,
  "live": true,
  "uptime_seconds": 3600,
  "checks": {
    "grpc_server": true,
    "database": true
  },
  "timestamp": 1697875200.0
}
```

## 🔧 Configuration

### Environment Variables

- `MARTY_RESILIENCE_ENABLED` - Enable/disable resilience interceptors (default: true)
- `MARTY_METRICS_ENABLED` - Enable/disable metrics collection (default: true)

### Prometheus Configuration

The Prometheus configuration includes both:

1. **Service discovery** for annotated services (preferred)
2. **Static targets** for backward compatibility

## 📚 Usage Examples

### Adding Custom Metrics

```python
from marty_common.metrics_server import get_metrics_server

# Get the global metrics server
metrics_server = get_metrics_server()
if metrics_server:
    # Record a custom operation
    metrics_server.metrics.record_successful_operation("custom_operation")

    # Update health status
    metrics_server.health.add_check("custom_check", True)
```

### Service-Specific Health Checks

```python
# In your service implementation
metrics_server = get_metrics_server()
if metrics_server:
    # Update database health
    try:
        await database.health_check()
        metrics_server.health.add_check("database", True)
    except Exception:
        metrics_server.health.add_check("database", False)
```

## 🚀 Deployment

### Local Development

1. Start a service: `python -m apps.csca_service`
2. Check metrics: `curl http://localhost:9081/metrics`
3. Check health: `curl http://localhost:8082/health`

### Kubernetes Deployment

1. Deploy services: `helm install csca-service ./helm/charts/csca-service`
2. Verify Prometheus scraping: Check Prometheus targets page
3. Monitor in Grafana: Use the provided dashboards

### Production Considerations

- **Resource Limits**: Metrics servers use minimal resources (~10MB RAM, <1% CPU)
- **Network Policies**: Ensure Prometheus can reach metrics ports
- **Security**: Consider TLS for metrics endpoints in production
- **Retention**: Configure appropriate metrics retention in Prometheus

## 🔍 Troubleshooting

### Common Issues

1. **Metrics endpoint not responding**
   - Check if service is running
   - Verify port configuration
   - Check firewall/network policies

2. **Prometheus not scraping**
   - Verify service annotations
   - Check Prometheus configuration
   - Ensure service discovery is enabled

3. **Health checks failing**
   - Check service logs
   - Verify health check implementation
   - Check resource availability

### Debug Commands

```bash
# Check service status
kubectl get pods -n marty

# Check service annotations
kubectl get svc -n marty -o yaml | grep prometheus

# Check Prometheus targets
kubectl port-forward -n marty-monitoring svc/prometheus-server 9090:80
# Visit http://localhost:9090/targets

# Test metrics endpoint directly
kubectl port-forward -n marty svc/csca-service 9081:9081
curl http://localhost:9081/metrics
```

## 📊 Monitoring Dashboard

### Key Metrics to Monitor

- **Request Rate**: `rate(marty_grpc_requests_total[5m])`
- **Error Rate**: `rate(marty_grpc_errors_total[5m])`
- **Response Time**: `histogram_quantile(0.95, marty_grpc_request_duration_seconds)`
- **Service Health**: `marty_service_health_status`

### Alerting Rules

The platform includes predefined alert rules for:

- High error rates
- High response times
- Service health failures
- Resource exhaustion

## 🎯 Next Steps

1. **Extended Metrics**: Add business-specific metrics
2. **Tracing Integration**: Add OpenTelemetry tracing
3. **Log Aggregation**: Integrate with ELK stack
4. **SLA Monitoring**: Implement SLO/SLI tracking
5. **Capacity Planning**: Add predictive analytics

## 📝 Files Modified/Added

### New Files

- `src/marty_common/metrics_server.py` - Metrics server implementation
- `src/marty_common/grpc_metrics.py` - gRPC metrics interceptors
- `scripts/test_metrics.py` - Testing utilities

### Modified Files

- `pyproject.toml` - Added prometheus_client dependency
- `src/apps/runtime.py` - Integrated metrics server
- `monitoring/prometheus/prometheus.yml` - Updated service discovery
- `helm/charts/*/templates/deployment.yaml` - Added metrics ports and annotations
- `helm/charts/*/templates/service.yaml` - Added metrics service exposure
- `helm/charts/*/values.yaml` - Added metrics port configuration

## 🏆 Benefits Achieved

✅ **Production-ready monitoring** with industry-standard tools  
✅ **Automatic metrics collection** without code changes  
✅ **Kubernetes-native health checks** for better orchestration  
✅ **Service discovery** for dynamic environments  
✅ **Comprehensive observability** across all microservices  
✅ **Scalable architecture** for future growth  

The Marty platform now has enterprise-grade monitoring capabilities that provide deep insights into service performance, health, and resource utilization, enabling proactive issue detection and resolution.
