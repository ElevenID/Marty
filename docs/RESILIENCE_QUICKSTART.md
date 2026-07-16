# Marty Resilience Framework - Quick Start Guide

## 🚀 Getting Started

The Marty resilience framework provides comprehensive error handling, circuit breakers, retries, and monitoring for your microservices.

### Quick Demo

Run the demonstration script to see all features in action:

```bash
git clone https://github.com/ElevenID/Marty.git
cd Marty
python scripts/resilience_demo.py
```

## 📦 Key Components

### 1. Circuit Breakers

Prevent cascading failures by temporarily blocking requests to failing services:

```python
from marty_common.resilience import CircuitBreaker, CircuitBreakerConfig

config = CircuitBreakerConfig(failure_threshold=5, recovery_timeout=30.0)
circuit_breaker = CircuitBreaker("my_service", config)

@circuit_breaker.decorate
def call_external_service():
    # Your service call here
    pass
```

### 2. Advanced Retries

Intelligent retry mechanisms with multiple backoff strategies:

```python
from marty_common.resilience import AdvancedRetryManager, AdvancedRetryConfig, BackoffStrategy

config = AdvancedRetryConfig(
    max_attempts=3,
    base_delay=1.0,
    backoff_strategy=BackoffStrategy.EXPONENTIAL_JITTER
)

retry_manager = AdvancedRetryManager("my_retry", config)

# Synchronous retry
result = retry_manager.retry_sync(my_function)

# Asynchronous retry
result = await retry_manager.retry_async(my_async_function)
```

### 3. gRPC Interceptors

Automatic resilience for gRPC client and server calls:

```python
from marty_common.resilience import (
    ResilienceClientInterceptor,
    EnhancedResilienceServerInterceptor
)

# Client interceptor
channel = grpc.insecure_channel('localhost:50051')
intercepted_channel = grpc.intercept_channel(
    channel,
    ResilienceClientInterceptor()
)

# Server interceptor
server = grpc.server(
    futures.ThreadPoolExecutor(max_workers=10),
    interceptors=[EnhancedResilienceServerInterceptor()]
)
```

### 4. Monitoring & Health Checks

Monitor all resilience components in real-time:

```python
from marty_common.resilience import get_global_monitor

monitor = get_global_monitor()
health = monitor.get_overall_health()
report = monitor.generate_health_report()
```

## 🔧 Configuration

### Environment-Specific Configs

**Development** (`config/development.yaml`):

- Lower thresholds for testing
- Failure injection enabled
- Detailed logging

**Production** (`config/production.yaml`):

- Higher thresholds for stability
- Failure injection disabled
- Performance-optimized

**Testing** (`config/testing.yaml`):

- Aggressive failure scenarios
- Comprehensive metrics collection

### Loading Configuration

```python
from marty_common.resilience import (
    get_development_config,
    get_production_config,
    get_testing_config
)

# Load environment-specific configuration
config = get_development_config()
```

## 🧪 Testing

### Integration Tests with Failure Injection

```python
from marty_common.resilience.comprehensive_integration_tests import (
    ResilienceTestOrchestrator,
    FailureScenario
)

orchestrator = ResilienceTestOrchestrator()

# Create failure scenario
scenario = FailureScenario(
    name="high_latency_test",
    failure_rate=0.3,
    latency_range=(1.0, 3.0)
)

# Test with failure injection
with orchestrator.failure_injection(scenario):
    results = orchestrator.run_circuit_breaker_test(
        "test_service", "test_cb", num_requests=100
    )
```

## 📊 Monitoring Integration

### Metrics Collection

All resilience patterns automatically collect metrics:

- Success/failure rates
- Latency distributions
- Circuit breaker state changes
- Retry attempt counts

### Health Checks

Built-in health checks for:

- Circuit breaker states
- Retry manager performance
- Overall system health

## 🚀 Production Integration

### 1. Update Your Service

```python
# Add to your service initialization
from marty_common.resilience import get_production_config, setup_resilience

config = get_production_config()
setup_resilience(config)
```

### 2. Add gRPC Interceptors

```python
# Client side
from marty_common.resilience import ResilienceClientInterceptor

channel = grpc.insecure_channel(target)
channel = grpc.intercept_channel(channel, ResilienceClientInterceptor())

# Server side
from marty_common.resilience import EnhancedResilienceServerInterceptor

server = grpc.server(
    futures.ThreadPoolExecutor(max_workers=10),
    interceptors=[EnhancedResilienceServerInterceptor()]
)
```

### 3. Configure Monitoring

```python
from marty_common.resilience import (
    get_global_monitor,
    register_circuit_breaker_for_monitoring,
    register_retry_manager_for_monitoring
)

monitor = get_global_monitor()
register_circuit_breaker_for_monitoring("my_service", circuit_breaker)
register_retry_manager_for_monitoring("my_retry", retry_manager)
```

## 📖 Documentation

For comprehensive documentation, see:

- [Full Implementation Guide](docs/RESILIENCE_IMPLEMENTATION_GUIDE.md)
- [API Reference](src/marty_common/resilience/__init__.py)
- [Configuration Reference](config/)

## 🎯 Next Steps

1. **Start Simple**: Begin with basic circuit breakers
2. **Add Retries**: Implement retry mechanisms for critical calls
3. **Enable Monitoring**: Set up health checks and metrics
4. **Test Thoroughly**: Use failure injection for comprehensive testing
5. **Optimize**: Tune configurations based on production metrics

## 💡 Best Practices

- Use circuit breakers for external service calls
- Implement retries with jittered backoff to avoid thundering herd
- Monitor all resilience patterns in production
- Test failure scenarios regularly
- Configure appropriate timeouts and thresholds
- Use environment-specific configurations
- Include resilience patterns in CI/CD testing

The Marty resilience framework provides enterprise-grade reliability patterns that are easy to integrate and highly configurable for your specific needs.
