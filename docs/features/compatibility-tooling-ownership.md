# Compatibility tooling ownership

The uncalled DRY configuration launcher imported retired `src.marty_common`
paths and is removed. The published `marty_common.config.dry_env_generator`
and its service registry remain supported APIs. Their consumers and configuration
policy need a package migration before any further consolidation; this cleanup
does not remove those interfaces or qualify historical defaults for production.

Protobuf Python implementations are generated once into `marty_plugin.proto.v1`
from `proto/v1`. Both installed `proto.v1` and checkout `src.proto.v1` imports
remain module aliases. Run `python src/compile_protos.py` with
`grpcio-tools==1.76.0`; generation requires both message and RPC outputs and
fails if either cannot be generated. The former system-protoc fallback could
report success with missing RPC bindings and is retired.
Generation is a checkout development command: the wheel does not ship protocol
sources or `src.compile_protos`. Its broken `compile-protos` console entry point
is removed; it never provided an installed generation command.

The pinned compiler belongs to the root checkout's `proto` extra, installed by
`make install` (or `python -m pip install -e ".[proto]"`). This also supplies the
system-language protobuf pre-commit hook. Ordinary `marty-common` installations
no longer install a compiler; gRPC, protobuf messages, reflection and health
checking remain runtime dependencies. Protocol CI keeps its explicit pinned
compiler installation and checks generated bindings and compatibility imports.

The DTC source already contains Type 1, 2 and 3 profiles. Regeneration reconciles
the stale implementation with those additive schema definitions; it does not
establish that each profile has a completed runtime issuance feature.
The public root protocol sources are retained and validated separately.
The older dynamic root imports in the common gRPC factory/runner remain a
separate integration issue: changing them can activate previously unused
registration paths and requires service-specific qualification.
