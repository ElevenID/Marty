# Marty Common

Shared infrastructure library for Marty digital identity services.

## Overview

`marty-common` provides core infrastructure components used across the Marty ecosystem:

- **Cryptography Bridge** (`crypto_bridge.py`) - Python wrapper for Rust crypto operations
- **gRPC Infrastructure** - Server, client, interceptors, metrics, and TLS configuration
- **Database Infrastructure** - SQLAlchemy helpers, connection pooling, and migrations
- **Configuration Management** - Centralized config with validation
- **Observability** - Prometheus metrics, OpenTelemetry tracing, structured logging
- **Security** - Authorization, authentication interceptors
- **Validation** - Data validation utilities
- **Utilities** - Common helpers for Marty services

## Installation

### From GitHub Packages (production)

```bash
pip install marty-common --extra-index-url https://USERNAME:TOKEN@ghcr.io/ORG/
```

### Local Development

```bash
# Clone the Marty repository
git clone https://github.com/ElevenID/Marty.git
cd Marty/packages/marty-common

# Install in editable mode
pip install -e .
```

## Usage

Open Badges support is limited to **Open Badges 3.0**. The OB2 issuance and
verification adapters have been removed, including the legacy native exports.
Request a newly issued OB3 credential from the issuer; changing an OB2 type or
context does not migrate its signed contents. Existing OB3 verification continues
through `verify_open_badge_ob3`; issuance uses the Rust managed-KMS issuer.
Both native credential and verification modules must declare
`OPEN_BADGES_SUPPORTED_VERSIONS = ("3.0",)`. The adapter rejects older wheels
before exposing any operation, including generic VC verification. Build the
matching wheels from the exact Core revision pinned in CI, or use a subsequent
release containing that revision. A version number alone does not establish
this capability; historical release assets are unchanged.

The Python stack uses the maintained `0.1.62` Core package profile so existing
password and access-key APIs remain available during this OB3 cutover. It does
not yet adopt the separate `0.2` production-profile migration. Build the pinned
source while the release containing these changes is pending.

The shared runtime does not install `grpcio-tools`. When changing the owning
checkout's protobuf schemas, use the root `proto` extra or `make install`; see
[tooling ownership](../../docs/features/compatibility-tooling-ownership.md).
The runtime declares protobuf, gRPC reflection and gRPC health checking directly.

```python
from marty_common.crypto_bridge import verify_certificate_chain
from marty_common.grpc_server import create_grpc_server
from marty_common.infrastructure.database import get_database_engine
from marty_common.monitoring import create_default_monitor, create_service_monitor

# Use shared infrastructure components
```

See [compatibility consolidation](../../docs/features/compatibility-consolidation.md)
for the two monitoring object models, stable import paths and retry behavior.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy marty_common

# Linting
ruff check marty_common
```

## License

MIT
