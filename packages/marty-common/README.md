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
git clone https://github.com/ORG/Marty.git
cd Marty/packages/marty-common

# Install in editable mode
pip install -e .
```

## Usage

```python
from marty_common.crypto_bridge import verify_certificate_chain
from marty_common.grpc_server import create_grpc_server
from marty_common.infrastructure.database import get_database_engine
from marty_common.monitoring import setup_prometheus_metrics

# Use shared infrastructure components
```

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
