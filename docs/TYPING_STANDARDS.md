# Typing Standards for Marty

This document outlines the type annotation standards and best practices for the Marty codebase. Following these conventions ensures consistent, maintainable, and type-safe code across all services.

## Table of Contents

- [Overview](#overview)
- [Configuration](#configuration)
- [General Principles](#general-principles)
- [Type Annotation Patterns](#type-annotation-patterns)
- [Common Patterns](#common-patterns)
- [Protocol Usage](#protocol-usage)
- [Generic Types](#generic-types)
- [Async Code](#async-code)
- [Exception Handling](#exception-handling)
- [Testing](#testing)
- [Gradual Adoption](#gradual-adoption)

## Overview

Marty uses **mypy** in strict mode for static type checking. All new code must be fully type-annotated, and existing code is being gradually improved to meet these standards.

### Benefits

- **Early Error Detection**: Catch type-related bugs before runtime
- **Better IDE Support**: Improved autocomplete, refactoring, and navigation
- **Self-Documenting Code**: Types serve as inline documentation
- **Safer Refactoring**: Confidence when making changes
- **Team Communication**: Clear contracts between modules

## Configuration

### pyproject.toml

The project uses strict mypy configuration in `pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.10"
disallow_untyped_defs = true
disallow_incomplete_defs = true
disallow_any_generics = true
strict_optional = true
warn_return_any = true
warn_unused_ignores = true
```

### mypy.ini

Additional module-specific configuration is in `mypy.ini`. Generated protobuf files and third-party libraries without stubs are excluded.

## General Principles

### 1. All Public Functions Must Have Type Annotations

✅ **Good:**

```python
def calculate_hash(data: bytes, algorithm: str = "sha256") -> str:
    """Calculate hash of data."""
    import hashlib
    hasher = hashlib.new(algorithm)
    hasher.update(data)
    return hasher.hexdigest()
```

❌ **Bad:**

```python
def calculate_hash(data, algorithm="sha256"):
    import hashlib
    hasher = hashlib.new(algorithm)
    hasher.update(data)
    return hasher.hexdigest()
```

### 2. Use Modern Type Syntax (PEP 585, PEP 604)

✅ **Good (Python 3.10+):**

```python
from __future__ import annotations

def process_items(items: list[str], config: dict[str, Any]) -> tuple[int, str]:
    result: str | None = items[0] if items else None
    return len(items), result or "default"
```

❌ **Bad (Old syntax):**

```python
from typing import List, Dict, Tuple, Optional, Any

def process_items(items: List[str], config: Dict[str, Any]) -> Tuple[int, str]:
    result: Optional[str] = items[0] if items else None
    return len(items), result or "default"
```

### 3. Use TYPE_CHECKING for Circular Imports

✅ **Good:**

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from marty_common.infrastructure import DatabaseManager

class Repository:
    def __init__(self, db: DatabaseManager) -> None:
        self._db = db
```

### 4. Prefer Specific Types Over Any

✅ **Good:**

```python
from typing import Literal

def set_log_level(level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]) -> None:
    pass
```

❌ **Bad:**

```python
from typing import Any

def set_log_level(level: Any) -> None:
    pass
```

## Type Annotation Patterns

### Function Signatures

```python
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")

def map_items(
    items: Iterable[T],
    transform: Callable[[T], R],
    *,
    parallel: bool = False,
) -> list[R]:
    """Transform items using the given function.

    Args:
        items: Input items to transform
        transform: Transformation function
        parallel: Whether to process in parallel

    Returns:
        List of transformed items
    """
    if parallel:
        # parallel implementation
        pass
    return [transform(item) for item in items]
```

### Class Attributes

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

@dataclass(slots=True)
class Certificate:
    """Represents an X.509 certificate."""

    certificate_id: str
    pem: str
    issuer: str
    subject: str
    not_before: datetime
    not_after: datetime
    revoked: bool = False
    metadata: dict[str, str] | None = None
```

### Class Methods

```python
from __future__ import annotations

from typing import Self  # Python 3.11+, or typing_extensions

class Builder:
    def __init__(self) -> None:
        self._config: dict[str, str] = {}

    def set_option(self, key: str, value: str) -> Self:
        """Set configuration option (builder pattern)."""
        self._config[key] = value
        return self

    def build(self) -> Config:
        """Build the configuration object."""
        return Config(self._config)
```

### Repository Pattern

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from .models import CertificateRecord

class CertificateRepository:
    """Repository for certificate database operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, cert_id: str) -> CertificateRecord | None:
        """Retrieve certificate by ID."""
        # implementation
        pass

    async def upsert(
        self,
        cert_id: str,
        pem: str,
        *,
        metadata: dict[str, str] | None = None,
    ) -> CertificateRecord:
        """Create or update a certificate."""
        # implementation
        pass

    async def list_all(self) -> list[CertificateRecord]:
        """List all certificates."""
        # implementation
        pass
```

## Common Patterns

### Optional Values

```python
def get_certificate(cert_id: str) -> Certificate | None:
    """Return certificate or None if not found."""
    # Note: Use `| None` instead of Optional[Certificate]
    pass

def process_certificate(cert: Certificate | None) -> str:
    """Process certificate with explicit None handling."""
    if cert is None:
        return "No certificate"
    return cert.subject
```

### Collections

```python
from collections.abc import Sequence, Mapping, Iterable

def process_certs(
    certificates: Sequence[Certificate],  # list or tuple
    config: Mapping[str, str],  # dict-like
    keys: Iterable[str],  # any iterable
) -> list[str]:
    """Process certificates with various collection types."""
    results: list[str] = []
    for cert in certificates:
        if cert.certificate_id in keys:
            results.append(cert.subject)
    return results
```

### Unions

```python
from pathlib import Path

def load_certificate(source: str | Path | bytes) -> Certificate:
    """Load certificate from various sources."""
    if isinstance(source, str):
        # Load from file path string
        pass
    elif isinstance(source, Path):
        # Load from Path object
        pass
    else:
        # Load from bytes
        pass
```

### TypedDict for Configuration

```python
from typing import TypedDict, NotRequired

class DatabaseConfig(TypedDict):
    """Type-safe database configuration."""
    host: str
    port: int
    database: str
    username: str
    password: str
    pool_size: NotRequired[int]  # Optional with Python 3.11+
    ssl_enabled: NotRequired[bool]
```

## Protocol Usage

Protocols enable structural subtyping without inheritance. Use them for defining interfaces:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Serializable(Protocol):
    """Protocol for objects that can be serialized."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        ...

    def to_json(self) -> str:
        """Convert to JSON string."""
        ...

def save_object(obj: Serializable, path: str) -> None:
    """Save any serializable object."""
    import json
    with open(path, "w") as f:
        f.write(obj.to_json())
```

See `src/marty_common/protocols.py` for standard protocol definitions.

## Generic Types

### Generic Functions

```python
from typing import TypeVar

T = TypeVar("T")

def first_or_default(items: list[T], default: T) -> T:
    """Return first item or default value."""
    return items[0] if items else default

# Usage:
numbers = [1, 2, 3]
result = first_or_default(numbers, 0)  # result is int
```

### Generic Classes

```python
from typing import Generic, TypeVar

T = TypeVar("T")

class Result(Generic[T]):
    """Generic result container."""

    def __init__(self, value: T | None, error: str | None = None) -> None:
        self.value = value
        self.error = error

    def is_success(self) -> bool:
        """Check if result is successful."""
        return self.error is None

    def unwrap(self) -> T:
        """Get value or raise exception."""
        if self.error:
            raise ValueError(self.error)
        assert self.value is not None
        return self.value
```

## Async Code

### Async Functions

```python
from collections.abc import AsyncIterator

async def fetch_certificates() -> list[Certificate]:
    """Fetch certificates asynchronously."""
    # async implementation
    pass

async def process_stream() -> AsyncIterator[Certificate]:
    """Stream certificates asynchronously."""
    async for cert in fetch_certificate_stream():
        yield cert
```

### Async Context Managers

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

@asynccontextmanager
async def database_session() -> AsyncIterator[AsyncSession]:
    """Provide async database session."""
    session = create_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
```

## Exception Handling

```python
class ValidationError(Exception):
    """Raised when validation fails."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")

def validate_certificate(cert: Certificate) -> None:
    """Validate certificate or raise ValidationError."""
    if not cert.pem:
        raise ValidationError("pem", "PEM data required")
```

## Testing

Test files have relaxed type checking requirements:

```python
from typing import Any
import pytest

from marty_common.infrastructure import DatabaseManager

def test_database_connection(db: DatabaseManager) -> None:
    """Test database connection."""
    # Type hints help with IDE support even in tests
    result = db.health_check()
    assert result is True

@pytest.fixture
def sample_certificate() -> Certificate:
    """Provide sample certificate for testing."""
    return Certificate(
        certificate_id="test-123",
        pem="...",
        issuer="Test CA",
        subject="Test Subject",
        not_before=datetime.now(),
        not_after=datetime.now() + timedelta(days=365),
    )
```

## Gradual Adoption

For existing code without type hints:

### 1. Start with Public APIs

Add type hints to module-level functions and class methods first.

### 2. Use `# type: ignore` Sparingly

Only use when absolutely necessary:

```python
from third_party import untyped_function

result = untyped_function()  # type: ignore[no-untyped-call]
```

### 3. Add Module-Specific Overrides

If a module needs more time, add to `mypy.ini`:

```ini
[mypy-src.legacy_module.*]
disallow_untyped_defs = False
```

## Best Practices Summary

1. ✅ Always use `from __future__ import annotations`
2. ✅ Use modern syntax: `list[str]`, `dict[str, int]`, `X | None`
3. ✅ Use TYPE_CHECKING for circular import types
4. ✅ Prefer specific types over `Any`
5. ✅ Use Protocols for interfaces
6. ✅ Document complex types with comments
7. ✅ Use TypedDict for configuration dictionaries
8. ✅ Add return type annotations to all functions
9. ✅ Use generics when appropriate
10. ✅ Keep type annotations readable and maintainable

## Resources

- [MyPy Documentation](https://mypy.readthedocs.io/)
- [PEP 484 – Type Hints](https://peps.python.org/pep-0484/)
- [PEP 585 – Type Hinting Generics In Standard Collections](https://peps.python.org/pep-0585/)
- [PEP 604 – Allow writing union types as X | Y](https://peps.python.org/pep-0604/)
- [PEP 544 – Protocols: Structural subtyping](https://peps.python.org/pep-0544/)
- [typing module documentation](https://docs.python.org/3/library/typing.html)

## Questions?

For questions or clarifications about type annotations in the Marty codebase, please:

1. Check this document first
2. Review existing code examples in `src/marty_common/`
3. Consult the team in code reviews

## Current enforcement and adoption

The separate historical typing quickstart/completion receipt is retired. Use
this guide for typing conventions and the checked-in `pyproject.toml`,
`mypy.ini`, pre-commit configuration and CI workflow for the actual enforcement
scope. A historical list of protocol interfaces, package markers or successful
checks does not prove strict coverage of the remaining compatibility code.
Gradual adoption, accurate protocol boundaries and appropriate type markers
remain maintenance requirements; verify existing modules before importing a
protocol named in an old example.
