# Marty Educational Developer Guide

**Technical documentation for learning ICAO standards through practical implementation**

> Contributions must follow the repository security, testing, and release policies.

## Educational Context

This developer guide documents an educational implementation created to:

- Learn and demonstrate ICAO Doc 9303 and ISO/IEC 18013-5 standards
- Explore microservices architecture patterns
- Practice cryptographic implementations and PKI concepts
- Showcase modern development practices and tools

**This is a learning project and should never be used in production environments.**

## Table of Contents

- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Architecture Deep Dive](#architecture-deep-dive)
- [Development Setup](#development-setup)
- [Integration Examples](#integration-examples)
- [Advanced Topics](#advanced-topics)

## Quick Start

Get Marty running locally in under 5 minutes:

```bash
# Clone and setup
git clone https://github.com/ElevenID/Marty.git
cd Marty
make setup
docker-compose up --build

# Verify services are running
curl http://localhost:8080/health
```

## API Reference

### gRPC Services

Marty provides these core gRPC services for integration:

| Service | Port | Protocol Buffers | Purpose |
|---------|------|------------------|---------|
| CSCA Service | 8081 | `csca_service.proto` | Country Signing Certificate Authority operations |
| Document Signer | 8082 | `document_signer.proto` | Document signing and certificate management |
| Inspection System | 8083 | `inspection_system.proto` | Document verification and validation |
| Passport Engine | 8084 | `passport_engine.proto` | eMRTD personalization and creation |
| MDL Engine | 8085 | `mdl_engine.proto` | Mobile driving license creation |
| DTC Engine | 8086 | `dtc_engine.proto` | Digital travel credential management |
| Trust Anchor | 8080 | `trust_anchor.proto` | Certificate trust management |
| PKD Service | 8087 | `common_services.proto` | Public Key Directory operations |

### REST API Endpoints

For easier integration and testing, REST endpoints wrap the gRPC services:

**Base URL**: `http://localhost:8080/api/v1/`

Key endpoints:

```
GET    /v1/csca/certificates        # List CSCA certificates
POST   /v1/csca/certificates        # Create new CSCA certificate
GET    /v1/csca/certificates/{id}   # Get specific certificate

POST   /v1/passport/personalize     # Create eMRTD document
POST   /v1/verify/passport          # Verify eMRTD authenticity

POST   /v1/mdl/create              # Create mobile driving license  
POST   /v1/mdl/verify              # Verify mDL document

POST   /v1/dtc/issue               # Issue digital travel credential
POST   /v1/dtc/verify              # Verify DTC document

GET    /v1/trust/anchors           # Get trusted certificate list
POST   /v1/trust/anchors           # Add trusted certificate
```

**OpenAPI Specification**: Complete API documentation available at `docs/api/openapi.yaml`

## Architecture Deep Dive

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Applications                      │
├─────────────────────────────────────────────────────────────┤
│  Mobile Apps  │  Web Apps  │  Verification  │  Admin UI    │
│               │            │  Systems       │  (FastAPI)   │
└───────┬───────┴────────────┴───────┬────────┴──────┬───────┘
        │                           │               │
        └───────────────┬───────────┴───────────────┘
                        │
            ┌───────────▼────────────┐
            │    gRPC Gateway        │
            │   (Load Balancer)      │
            │   + REST API Layer     │
            └───────────┬────────────┘
                        │
    ┌───────────────────┼───────────────────┐
    │                   │                   │
    ▼                   ▼                   ▼
┌─────────┐      ┌─────────────┐    ┌─────────────┐
│Passport │      │MDL Engine   │    │DTC Engine   │
│Engine   │      │(ISO 18013-5)│    │(ICAO DTC)   │
│(ICAO    │      └──────┬──────┘    └──────┬──────┘
│9303)    │             │                  │
└────┬────┘             │                  │
     │                  │                  │
     └──────────────────┼──────────────────┘
                        │
        ┌───────────────▼───────────────┐
        │    Document Signer Service    │
        │   (Certificate Management)    │
        └───────────────┬───────────────┘
                        │
    ┌───────────────────┼───────────────────┐
    │                   │                   │
    ▼                   ▼                   ▼
┌─────────┐    ┌─────────────┐    ┌─────────────┐
│CSCA     │    │Trust Anchor │    │PKD Service  │
│Service  │    │Management   │    │(OpenXPKI)  │
└────┬────┘    └──────┬──────┘    └──────┬──────┘
     │                │                  │
     └────────────────┼──────────────────┘
                      │
          ┌───────────▼───────────┐
          │    PostgreSQL DB      │
          │  + Certificate Store  │
          └───────────────────────┘
```

### Core Components

#### Document Engines

- **Passport Engine**: ICAO Doc 9303 compliant eMRTD creation with full LDS support
- **MDL Engine**: ISO/IEC 18013-5 mobile driving licenses with selective disclosure
- **DTC Engine**: ICAO Digital Travel Credentials with token management

#### Security Layer

- **CSCA Service**: Country Signing Certificate Authority with HSM integration
- **Document Signer**: Cryptographic document signing using RSA/ECDSA
- **Trust Anchor**: Certificate trust chain validation and management

#### Verification Layer

- **Inspection System**: Multi-format document verification with BAC/PACE support
- **PKD Service**: Public Key Directory integration with ICAO Master Lists

## Development Setup

### Prerequisites

- Python 3.10+
- Docker and Docker Compose
- UV package manager
- Make (for development shortcuts)

### Local Development

```bash
# Install UV package manager
pip install uv

# Clone and setup project
git clone https://github.com/ElevenID/Marty.git
cd Marty

# Install dependencies
make setup

# Generate protocol buffers
make compile-proto

# Run tests
make test

# Start development services
make dev
```

### Docker Development

```bash
# Build and start all services
docker-compose up --build

# Start specific service
docker-compose up passport-engine

# View logs
docker-compose logs -f passport-engine

# Scale services
docker-compose up --scale passport-engine=3
```

### Kubernetes Development

The recommended development approach for microservices is using Kubernetes, which better matches production deployment patterns.

#### Prerequisites

- Docker Desktop (with Kubernetes enabled) or Docker Engine
- Make (for running commands)

#### Quick Start

```bash
# Set up local Kubernetes cluster with all dependencies
make k8s-setup

# Deploy all services to Kubernetes
make k8s-deploy

# Set up port forwarding for local development
make k8s-port-forward

# Check status
make k8s-status
```

#### Development Workflow

**1. Initial Setup**

```bash
# One-time setup of Kind cluster with ingress, storage, and namespaces
make k8s-setup
```

This creates a local Kubernetes cluster using Kind with:

- Multi-node cluster (1 control plane + 2 workers)
- NGINX Ingress Controller
- Local storage class
- Namespaces: `marty` (services) and `marty-system` (monitoring)
- Self-signed TLS certificates
- Helm repositories configured

**2. Deploy Services**

```bash
# Build Docker images and deploy to Kubernetes
make k8s-deploy
```

This will:

- Compile protocol buffers
- Build all Docker images
- Load images into Kind cluster
- Deploy PostgreSQL database
- Deploy all Marty microservices via Helm

**3. Development with Hot Reload**

```bash
# Start Skaffold for continuous development
make k8s-dev
```

Skaffold provides:

- Automatic image rebuilds on code changes
- Deployment to Kubernetes
- Port forwarding to local machine
- Log streaming from pods

**4. Access Services**

```bash
# Set up port forwarding for all services
make k8s-port-forward

# Or manually forward specific services
kubectl port-forward svc/ui-app 8090:8090 -n marty
kubectl port-forward svc/csca-service 8081:8081 -n marty
```

**5. Monitoring and Debugging**

```bash
# Deploy monitoring stack (Prometheus + Grafana)
make k8s-monitoring

# View logs from all services
make k8s-logs

# Check pod status
kubectl get pods -n marty

# Describe a specific service
kubectl describe svc csca-service -n marty

# Get events
kubectl get events -n marty --sort-by='.lastTimestamp'
```

#### Service Access URLs

When port forwarding is active:

- **UI Application**: <http://localhost:8090>
- **CSCA Service**: <http://localhost:8081>
- **Document Signer**: <http://localhost:8082>
- **Inspection System**: <http://localhost:8083>
- **Passport Engine**: <http://localhost:8084>
- **MDL Engine**: <http://localhost:8085>
- **mDoc Engine**: <http://localhost:8086>
- **DTC Engine**: <http://localhost:8087>
- **PKD Service**: <http://localhost:8088>

#### Monitoring Access

```bash
# Access Grafana dashboard
kubectl port-forward svc/marty-monitoring-grafana 3000:3000 -n marty-system
# Open http://localhost:3000 (admin/admin)

# Access Prometheus
kubectl port-forward svc/marty-monitoring-prometheus-server 9090:9090 -n marty-system
# Open http://localhost:9090
```

#### Common Development Tasks

**Restart Services**

```bash
# Restart all services
make k8s-restart

# Restart specific service
kubectl rollout restart deployment/csca-service -n marty
```

**Update Configuration**

```bash
# Update Helm values and redeploy
helm upgrade csca-service helm/charts/csca-service -n marty --set image.tag=latest

# Apply configuration changes
kubectl apply -f k8s/configmap.yaml
```

**Debugging**

```bash
# Get pod logs
kubectl logs -f deployment/csca-service -n marty

# Execute into a pod
kubectl exec -it deployment/csca-service -n marty -- /bin/bash

# Port forward to specific pod
kubectl port-forward pod/csca-service-xxx 8081:8081 -n marty
```

**Testing Service Communication**

```bash
# Test internal service communication
kubectl run test-pod --image=curlimages/curl -i --tty --rm -- /bin/sh
# Inside pod:
curl http://csca-service.marty.svc.cluster.local:8081/health
```

#### Cleanup

```bash
# Remove all services but keep cluster
make k8s-undeploy

# Destroy entire cluster
make k8s-destroy
```

#### Troubleshooting

**Pod Won't Start**

```bash
# Check pod status and events
kubectl describe pod <pod-name> -n marty

# Check logs
kubectl logs <pod-name> -n marty --previous
```

**Service Not Accessible**

```bash
# Check service and endpoints
kubectl get svc,ep -n marty

# Test DNS resolution
kubectl run test-dns --image=busybox -i --tty --rm -- nslookup csca-service.marty.svc.cluster.local
```

**Image Pull Issues**

```bash
# Ensure images are loaded into Kind
kind load docker-image marty/csca-service:latest --name marty-dev

# Check image pull policy
kubectl get deployment csca-service -n marty -o yaml | grep imagePullPolicy
```

**Port Forwarding Issues**

```bash
# Kill existing port forwards
pkill -f "kubectl port-forward"

# Restart port forwarding
make k8s-port-forward
```

#### Configuration Management

All Kubernetes configurations are managed through:

- **Helm Charts**: `helm/charts/` - Service deployment configurations
- **Skaffold**: `skaffold.yaml` - Development workflow automation  
- **Makefile**: Kubernetes development targets
- **Config Maps**: Environment-specific configurations
- **Secrets**: Sensitive data like database passwords

### Environment Configuration

Configuration is managed through environment-specific YAML files:

```
config/
├── development.yaml    # Local development
├── testing.yaml       # Test environment  
├── production.yaml    # Production settings
```

Set environment: `export MARTY_ENV=development`

### OpenXPKI Integration Setup

⚠️ **Important**: OpenXPKI services require explicit credential configuration. No defaults are provided for security.

**Quick Setup for Development**:

```bash
# 1. Setup environment configuration
cp docker/openxpki.env.example docker/openxpki.env
# Edit docker/openxpki.env and set OPENXPKI_USERNAME/PASSWORD

# 2. Start OpenXPKI container with credentials
docker-compose -f docker/docker-compose.openxpki.yml up -d

# 3. Initialize OpenXPKI configuration and create development secrets
./scripts/development/setup_openxpki.sh

# 4. Verify OpenXPKI is running
curl -k https://localhost:8443/openxpki/
```

**Credential Configuration Options**:

1. **Environment Variables** (development):

   ```bash
   export OPENXPKI_USERNAME="pkiadmin"
   export OPENXPKI_PASSWORD="your_secure_password"
   ```

2. **Secret Files** (production):

   ```bash
   echo "admin_user" > /run/secrets/openxpki_username
   echo "secure_password" > /run/secrets/openxpki_password
   export OPENXPKI_USERNAME_FILE="/run/secrets/openxpki_username"
   export OPENXPKI_PASSWORD_FILE="/run/secrets/openxpki_password"
   ```

**Validation**: Services will fail to start with `ValueError` if credentials are not provided.

See `docs/SECRETS_MANAGEMENT.md` for production deployment patterns.

## Integration Examples

### 1. Python gRPC Client

```python
import grpc
from src.proto import passport_engine_pb2_grpc, passport_engine_pb2

class MartyPassportClient:
    def __init__(self, server_address='localhost:8084'):
        self.channel = grpc.insecure_channel(server_address)
        self.stub = passport_engine_pb2_grpc.PassportEngineStub(self.channel)

    def create_passport(self, citizen_data):
        """Create an eMRTD passport"""
        request = passport_engine_pb2.PersonalizationRequest(
            mrz_data=citizen_data['mrz'],
            photo_data=citizen_data['photo'],
            additional_data_groups=citizen_data.get('additional_dgs', [])
        )

        try:
            response = self.stub.PersonalizePassport(request)
            return {
                'success': response.success,
                'passport_id': response.passport_id,
                'error': response.error_message if not response.success else None
            }
        except grpc.RpcError as e:
            return {'success': False, 'error': f'gRPC Error: {e.details()}'}

# Usage
client = MartyPassportClient()
result = client.create_passport({
    'mrz': 'P<UTOBAKER<<JOHN<<<<<<<<<<<<<<<<<<<<<<<<<1234567890USA8001019M2501017<<<<<<<<<<<<<<02',
    'photo': photo_bytes
})
```

### 2. Document Verification

```python
from src.proto import inspection_system_pb2_grpc, inspection_system_pb2

class MartyVerificationClient:
    def __init__(self, server_address='localhost:8083'):
        self.channel = grpc.insecure_channel(server_address)
        self.stub = inspection_system_pb2_grpc.InspectionSystemStub(self.channel)

    def verify_document(self, document_data, doc_type='passport'):
        """Verify document authenticity"""
        request = inspection_system_pb2.VerificationRequest(
            document_data=document_data,
            verification_type="FULL_CHIP_VERIFICATION",
            document_type=doc_type.upper()
        )

        response = self.stub.VerifyDocument(request)
        return {
            'valid': response.is_valid,
            'trust_status': response.trust_status,
            'certificate_chain': response.certificate_chain,
            'verification_details': response.verification_details,
            'errors': response.errors
        }
```

### 3. Mobile Driving License Creation

```python
from src.proto import mdl_engine_pb2_grpc, mdl_engine_pb2

class MartyMDLClient:
    def __init__(self, server_address='localhost:8085'):
        self.channel = grpc.insecure_channel(server_address)
        self.stub = mdl_engine_pb2_grpc.MdlEngineStub(self.channel)

    def create_mdl(self, driver_data):
        """Create ISO 18013-5 compliant mDL"""
        request = mdl_engine_pb2.MdlCreationRequest(
            driver_data=driver_data,
            portrait_image=driver_data['portrait'],
            signature_image=driver_data.get('signature'),
            issuing_authority=driver_data['issuing_authority'],
            issue_date=driver_data['issue_date'],
            expiry_date=driver_data['expiry_date']
        )

        response = self.stub.CreateMdl(request)
        return {
            'success': response.success,
            'mdl_id': response.mdl_id,
            'mdl_data': response.mdl_data,
            'qr_code': response.qr_code_data
        }
```

### 4. Batch Processing with Connection Pooling

```python
import grpc
from concurrent.futures import ThreadPoolExecutor
import logging

class MartyBatchProcessor:
    def __init__(self, max_workers=10):
        self.max_workers = max_workers
        self.channels = {}
        self.clients = {}

    def get_client(self, service_name, port):
        """Get or create gRPC client with connection pooling"""
        key = f"{service_name}:{port}"
        if key not in self.channels:
            self.channels[key] = grpc.insecure_channel(f'localhost:{port}')

        if key not in self.clients:
            if service_name == 'passport':
                self.clients[key] = passport_engine_pb2_grpc.PassportEngineStub(
                    self.channels[key]
                )
            # Add other service clients as needed

        return self.clients[key]

    def batch_create_passports(self, citizens_data):
        """Process multiple passports in parallel"""
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for citizen in citizens_data:
                future = executor.submit(self._create_single_passport, citizen)
                futures.append(future)

            results = []
            for future in futures:
                try:
                    result = future.result(timeout=30)
                    results.append(result)
                except Exception as e:
                    logging.error(f"Batch processing error: {e}")
                    results.append({'success': False, 'error': str(e)})

            return results

    def _create_single_passport(self, citizen_data):
        """Create single passport (internal method)"""
        client = self.get_client('passport', 8084)
        request = passport_engine_pb2.PersonalizationRequest(
            mrz_data=citizen_data['mrz'],
            photo_data=citizen_data['photo']
        )

        response = client.PersonalizePassport(request)
        return {
            'success': response.success,
            'passport_id': response.passport_id,
            'citizen_id': citizen_data.get('id')
        }
```

## Advanced Topics

### Error Handling Patterns

```python
import grpc
from grpc import StatusCode
import time

def retry_with_backoff(func, max_retries=3, backoff_factor=2):
    """Retry gRPC calls with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return func()
        except grpc.RpcError as e:
            if e.code() in [StatusCode.UNAVAILABLE, StatusCode.DEADLINE_EXCEEDED]:
                if attempt < max_retries - 1:
                    sleep_time = backoff_factor ** attempt
                    time.sleep(sleep_time)
                    continue
            raise e

def robust_document_verification(document_data):
    """Production-ready document verification with error handling"""
    def verify():
        channel = grpc.insecure_channel('localhost:8083')
        client = inspection_system_pb2_grpc.InspectionSystemStub(channel)

        request = inspection_system_pb2.VerificationRequest(
            document_data=document_data,
            verification_type="FULL_CHIP_VERIFICATION"
        )

        return client.VerifyDocument(request)

    try:
        response = retry_with_backoff(verify)
        return {
            'status': 'success',
            'valid': response.is_valid,
            'details': response.verification_details
        }
    except grpc.RpcError as e:
        error_map = {
            StatusCode.INVALID_ARGUMENT: "Invalid document format or data",
            StatusCode.NOT_FOUND: "Certificate not found in trust store",
            StatusCode.DEADLINE_EXCEEDED: "Verification timeout - check document complexity",
            StatusCode.PERMISSION_DENIED: "Insufficient permissions for verification",
            StatusCode.UNAVAILABLE: "Verification service unavailable"
        }

        return {
            'status': 'error',
            'error_code': e.code().name,
            'error_message': error_map.get(e.code(), f"Unknown error: {e.details()}")
        }
```

### Custom Protocol Buffer Extensions

```python
# Example: Extending the passport engine for custom data groups
from src.proto import passport_engine_pb2
import json

def create_custom_data_group(dg_number, data):
    """Create custom data group for passport"""
    custom_dg = passport_engine_pb2.DataGroup(
        group_number=dg_number,
        data=json.dumps(data).encode('utf-8'),
        hash_algorithm='SHA256'
    )
    return custom_dg

# Usage in passport creation
additional_dgs = [
    create_custom_data_group(16, {'custom_field': 'custom_value'}),
    create_custom_data_group(17, {'biometric_template': biometric_data})
]
```

### Performance Monitoring

```python
import time
import logging
from functools import wraps

def monitor_performance(func):
    """Decorator to monitor gRPC call performance"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            logging.info(f"{func.__name__} completed in {duration:.3f}s")
            return result
        except Exception as e:
            duration = time.time() - start_time
            logging.error(f"{func.__name__} failed after {duration:.3f}s: {e}")
            raise
    return wrapper

@monitor_performance
def create_and_verify_document(citizen_data):
    # Implementation here
    pass
```

## Testing

### Unit Tests

```bash
# Run all tests
make test

# Run specific test module
pytest tests/unit/test_passport_engine.py

# Run with coverage
pytest --cov=src tests/
```

### Integration Tests

```bash
# Start test environment
docker-compose -f docker/docker-compose.yml up -d

# Run integration tests
make test-integration

# Clean up
docker-compose -f docker/docker-compose.yml down
```

### Load Testing

```bash
# Install load testing tools
pip install grpcio-tools grpcio-status

# Run load tests
python tests/load/passport_load_test.py --concurrent=50 --requests=1000
```

## Deployment

### Production Configuration

```yaml
# config/production.yaml
server:
  host: "0.0.0.0"
  port: 8080
  workers: 4

database:
  url: "postgresql://user:pass@db:5432/marty"
  pool_size: 20
  max_overflow: 0

openxpki:
  server_url: "https://openxpki.production.com"
  api_endpoint: "/api/v1"
  realm: "production-ca"

logging:
  level: "INFO"
  format: "json"
```

### Docker Production Build

```dockerfile
# Dockerfile.production
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ ./src/
COPY config/ ./config/
COPY proto/ ./proto/

EXPOSE 8080
CMD ["python", "-m", "src.main"]
```

## Support Resources

- **Protocol Buffers**: All `.proto` files in `proto/` directory
- **OpenAPI Specification**: Complete REST API docs at `docs/api/openapi.yaml`
- **Test Examples**: Integration patterns in `tests/integration/`
- **Configuration Examples**: Environment configs in `config/`
- **GitHub Issues**: Bug reports and feature requests
