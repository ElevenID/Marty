# Docker Development Guide

Quick reference for the Marty development environment.

## Quick Start

```bash
# Start development environment
make dev

# Run E2E tests (full browser matrix)
make test

# Run fast Chromium-only tests
make test-local

# Stop everything
make down
```

## Profiles

| Profile | Description | Services |
|---------|-------------|----------|
| `dev` | Local development | API, UI, Keycloak, Postgres, Redis, MailHog, Seed |
| `test` | Full E2E testing | Above + Playwright (all browsers), wallet-simulator |
| `test-local` | Fast E2E testing | Above + Playwright (Chromium only), wallet-simulator |
| `pytest` | Python tests | Postgres, Redis + pytest container |

## URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| UI | http://localhost:9080 | - |
| API | http://localhost:8000 | - |
| Keycloak Admin | http://localhost:8180 | admin / admin |
| MailHog | http://localhost:8025 | - |
| Wallet Simulator | http://localhost:9081 | (test profile only) |

## Demo Users

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@marty.demo | Admin123! |
| Vendor | vendor@marty.demo | Vendor123! |
| Applicant | john.doe@marty.demo | Applicant123! |
| Applicant | jane.smith@marty.demo | Applicant123! |
| Applicant | carlos.garcia@marty.demo | Applicant123! |

## Makefile Targets

```bash
make help          # Show all commands
make dev           # Start development environment
make test          # Run E2E tests (all browsers)
make test-local    # Run Chromium-only E2E tests
make pytest        # Run Python unit/integration tests
make build         # Build all service images
make build-wallet  # Build wallet-simulator image
make status        # Show service status
make logs          # Follow logs
make down          # Stop all services
make clean         # Stop and remove volumes
```

## Wallet Simulator

The wallet-simulator is a Flutter Web app from `marty-authenticator` used for E2E testing.

```bash
# Build the image (required before running tests)
make build-wallet

# Or build manually
docker build -t ghcr.io/anthropic/marty-authenticator:local \
  -f ../marty-authenticator/docker/Dockerfile.flutter.web.test \
  ../marty-authenticator
```

## File Structure

```
Marty/
├── docker-compose.yml      # Unified compose with profiles
├── Makefile                # Entry point for all commands
└── marty-ui/
    ├── docker/
    │   ├── api.Dockerfile         # Python API
    │   ├── ui.Dockerfile          # React UI (nginx)
    │   ├── seed.Dockerfile        # Database seeding
    │   ├── init-databases.sh      # Postgres init script
    │   └── Dockerfile.fluentd     # Logging (observability)
    └── tests/
        ├── Dockerfile.playwright       # Full browser E2E
        ├── Dockerfile.playwright.local # Chromium-only E2E
        └── Dockerfile.pytest           # Python test runner
```

## Troubleshooting

### Services not starting
```bash
# Check status
make status

# View logs
make logs

# Clean restart
make clean && make dev
```

### Wallet image not found
```bash
# Ensure marty-authenticator is cloned alongside Marty
make build-wallet
```

### Database issues
```bash
# Reset databases
make clean  # This removes volumes
make dev
```

### Port conflicts
Check if ports 8000, 8180, 9080, 9081, 6379, 5432 are in use:
```bash
lsof -i :8000
```
