# Adding a New Microservice

> Step-by-step guide for onboarding a new service into the Marty platform.

## 1. Scaffold the Service

```bash
# Create service directory
mkdir -p marty-ui/services/<service-name>/{domain,application,infrastructure/adapters}

# Create main.py using the shared service setup
cat > marty-ui/services/<service-name>/main.py << 'EOF'
import logging
from fastapi import APIRouter
from marty_common.service_setup import create_service_app

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/<service-name>", tags=["<service-name>"])

@router.get("/")
async def list_items():
    return {"items": []}

app = create_service_app(
    service_name="<service-name>",
    routers=[router],
)
EOF
```

`create_service_app()` automatically configures:
- CORS middleware (from `CORS_ORIGINS` env)
- RequestId middleware
- Request logging middleware
- `/health` endpoint
- OpenTelemetry / Prometheus metrics

## 2. Define Proto File (if using gRPC)

```protobuf
// marty-ui/proto/v1/<service_name>_service.proto
syntax = "proto3";
package marty.ui.<service_name>.v1;

service <ServiceName>Service {
  rpc Get<Entity> (<Entity>Request) returns (<Entity>Response);
}
```

Package naming convention: `marty.ui.<service_name>.v1`

Generate stubs:
```bash
cd marty-ui && make proto
```

## 3. Create Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY services/<service-name>/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/<service-name> ./services/<service-name>
COPY services/common ./services/common
CMD ["uvicorn", "services.<service-name>.main:app", "--host", "0.0.0.0", "--port", "800X"]
```

## 4. Register in Docker Compose

Add to `marty-ui/docker-compose.base.yml`:
```yaml
  <service-name>:
    build:
      context: .
      dockerfile: services/<service-name>/Dockerfile
    ports:
      - "800X:800X"
    environment:
      - SERVICE_NAME=<service-name>
      - REDIS_URL=redis://redis:6379
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:800X/health"]
      interval: 10s
      timeout: 5s
      retries: 3
```

## 5. Register in Gateway

Add route mapping in `marty-ui/services/gateway/routes/`:
```python
# marty-ui/services/gateway/routes/<service_name>.py
from fastapi import APIRouter
router = APIRouter(prefix="/v1/<service-name>", tags=["<service-name>"])
SERVICE_URL = os.environ.get("<SERVICE_NAME>_URL", "http://<service-name>:800X")
```

Register in `marty-ui/services/gateway/registry.py`.

## 6. Add Tests

```bash
mkdir -p marty-ui/services/<service-name>/tests
cat > marty-ui/services/<service-name>/tests/test_routes.py << 'EOF'
import pytest
from httpx import AsyncClient, ASGITransport
from services.<service_name>.main import app

@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
EOF
```

## 7. Checklist

- [ ] Service uses `create_service_app()` for consistent middleware
- [ ] Proto follows `marty.ui.<name>.v1` package naming
- [ ] Dockerfile copies `services/common` for shared utilities
- [ ] Docker Compose entry has health check
- [ ] Gateway route registered
- [ ] At least one integration test
- [ ] Environment variables documented in service README
