# gRPC service factory compatibility guide

## Retained interfaces

The Python [factory implementation](../packages/marty-common/marty_common/grpc_service_factory.py)
remains available for compatibility. Current Rust service infrastructure belongs
to Marty Microservices Framework; deployment composition belongs to marty-ui.
See [shared service ownership](DRY_IMPLEMENTATION_GUIDE.md) before migrating a service.

The packaged `grpc_service_factory_examples.py` is retired. It imported absent
TrustAnchorService/PKDService application classes and had no tracked code caller.
Its generated trust-anchor protobuf module still exists and is retained.
The old `main_dry.py` migration example and `src/marty_common` paths in this
guide were not current entry points. Removing these claims does not remove the
factory, generated protocols or service implementations.

| Interface | Current behavior |
| --- | --- |
| `GRPCServiceFactory(config)` | Holds configuration, service definitions and server lifecycle state |
| `register_service(name, servicer_factory, registration_func, health_service_name=None, dependencies=None, priority=100)` | Adds a definition; returns the factory for chaining |
| `create_grpc_service_factory(service_name, config_type="grpc", **config_kwargs)` | Builds configuration and queues standard health/logging service definitions |
| `create_server(**kwargs)` | Constructs the gRPC server and attempts registration in priority order |
| `start(**kwargs)`, `serve(**kwargs)`, `stop(grace_period=30)` | Start, wait for termination, and request graceful shutdown |
| `run_single_service(...)` | Convenience entry point that creates a factory, registers a service and serves |
| `ServiceRegistry`, `register_service_globally(...)`, `grpc_service(...)` | Maintain definitions in the separate global registry |
| `auto_register_service(...)`, `auto_register_from_config(...)` | Attempt convention-based discovery; failures are logged |

A service supplies its real constructor and generated
`add_*Servicer_to_server` callback to `register_service`. Stored
`dependencies` are merged with creation keyword arguments; creation arguments
take precedence. Multiple definitions are supported, and lower numeric
priorities are attempted first.

The decorator/global registry does not automatically populate a factory's
`services` list. The former example that decorated a class and immediately
called `create_grpc_service_factory(...).serve()` did not establish registration
of that application service. Explicitly registering a definition is distinct
from adding it to the global registry.

Configuration comes from [base_config.py](../packages/marty-common/marty_common/base_config.py).
Use actual supported field names and `get_grpc_config()`/`get_tls_config()`
results when inspecting a retained service. Selecting a `hybrid` configuration
does not make this factory start an HTTP application.

## Qualification work retained

This is an interface inventory, not a production startup recipe. The existing
implementation has integration limits that the removed examples did not test:

- Auto-registration still tries historical `src.proto` paths before looking
  for a callback in the supplied service module. Qualify discovery and manual
  registration against actual generated namespaces and constructor dependencies.
- Registration exceptions are logged and startup can continue without a requested
  service. A running server alone does not establish that all required RPCs exist.
- Standard health definitions and reflection setup do not prove application
  readiness. The health-update path looks for `_health_servicer`, while the
  constructor initializes `health_servicer`; qualify actual serving status.
- TLS configuration can fall back to an insecure port when certificate/key
  configuration is missing. This factory must not be treated as fail-closed
  transport security. Correcting that behavior needs explicit transport
  requirements and positive/negative startup tests.
- Qualify bind failures, certificate loading, shutdown/draining and signal
  handling in the owning process. Verify configured message limits, keepalive
  and reflection behavior rather than inferring them from configuration fields.
- Preserve single-service, multi-service, dependency-injection and explicit
  registration scenarios when replacing this compatibility API. A decorator
  migration needs a defined registry-to-factory step and tests.
- Verify health, logging-streamer and application RPC registration with actual
  clients, including startup failures and missing dependencies. Broader
  telemetry, HTTP/hybrid operation and discovery remain owner-specific work.

The [compatibility tooling ownership note](features/compatibility-tooling-ownership.md)
also records registration-path qualification. Retiring the nonworking sample
does not complete these requirements or authorize removing a service's existing
server setup before its replacement is tested.
