# Native Development Setup

This guide describes the **hybrid TDD development environment** for fast feedback during development.

## Overview

The project uses a hybrid setup:
- **Native**: Python API and React UI run natively with hot reload
- **Docker**: Infrastructure services (Keycloak, Redis, PostgreSQL) run in containers

This provides sub-second API restarts while maintaining realistic infrastructure.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Host Machine                              │
├─────────────────────────────────────────────────────────────────┤
│  Native Services:                                                │
│  ├── React UI (port 3000) - CRA dev server with setupProxy.js   │
│  └── Python API (port 8000) - uvicorn with --reload             │
├─────────────────────────────────────────────────────────────────┤
│  Docker Services (via docker-compose):                           │
│  ├── Keycloak (port 8180) - Auth/OIDC provider                  │
│  ├── Redis (port 6379) - Session storage                        │
│  └── PostgreSQL (port 5432) - Database                          │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# 1. Start Docker infrastructure
make dev-infra

# 2. Start native API (new terminal)
make dev-api

# 3. Start React UI (new terminal)
make dev-ui

# 4. Run E2E tests (new terminal)
make test-e2e-onboarding
```

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make dev-infra` | Start Docker services (Keycloak, Redis, PostgreSQL) |
| `make dev-api` | Start Python API natively with hot reload |
| `make dev-ui` | Start React UI dev server |
| `make dev-setup` | One-time setup (install deps, create venv) |
| `make test-e2e-onboarding` | Run onboarding E2E tests |

## Key Directories

| Directory | Purpose |
|-----------|---------|
| `marty-ui/src/` | Python API source |
| `marty-ui/ui/` | React UI source |
| `marty-ui/tests/e2e/` | Playwright E2E tests |
| `marty-microservices-framework/` | MMF shared package |

## Environment Variables

The `make dev-api` target sets all required environment variables automatically. Key ones include:

| Variable | Value | Purpose |
|----------|-------|---------|
| `KEYCLOAK_URL` | `http://localhost:8180` | Keycloak admin API (not Docker hostname!) |
| `OIDC_ISSUER_URL` | `http://localhost:8180/realms/marty` | OIDC token validation |
| `REDIS_URL` | `redis://localhost:6379/0` | Session storage |
| `PYTHONPATH` | Includes `marty-microservices-framework/` | Required for MMF imports |

## React Proxy Configuration

The React app (`marty-ui/ui/`) uses `setupProxy.js` to proxy requests to the native API:

- `/auth/*` → `http://localhost:8000`
- `/api/*` → `http://localhost:8000`
- `/health` → `http://localhost:8000`

## Running E2E Tests

```bash
cd marty-ui/tests

# Run workflow tests
BASE_URL=http://localhost:3000 API_URL=http://localhost:8000 npx playwright test --project=workflows

# Run onboarding tests
BASE_URL=http://localhost:3000 API_URL=http://localhost:8000 npx playwright test --project=onboarding
```

## Test Users

| User | Password | Role |
|------|----------|------|
| `admin@marty.demo` | `admin` | Platform admin |
| `vendor@marty.demo` | `vendor` | Vendor admin |

## Troubleshooting

### "ModuleNotFoundError: No module named 'mmf'"

**Cause**: PYTHONPATH doesn't include `marty-microservices-framework/`

**Fix**: Use `make dev-api` which sets PYTHONPATH automatically, or manually:
```bash
export PYTHONPATH=$(pwd)/marty-microservices-framework:$PYTHONPATH
```

### "[Errno 8] nodename nor servname provided"

**Cause**: `KEYCLOAK_URL` using Docker hostname (`keycloak:8080`) instead of localhost

**Fix**: Set `KEYCLOAK_URL=http://localhost:8180`

### Login redirects to landing page instead of Keycloak

**Cause**: `setupProxy.js` not configured or React dev server not restarted

**Fix**: Ensure `marty-ui/ui/src/setupProxy.js` exists and restart React dev server

### 500 errors on /auth/callback

**Cause**: API missing environment variables or PYTHONPATH

**Fix**: Use `make dev-api` to start API with all required env vars

## Full Docker Mode

For production-like testing, use full Docker mode instead:

```bash
docker-compose up --build
```

This runs everything in containers but has slower feedback loops for API changes.
