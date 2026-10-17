# Protocol Buffer Backward Compatibility Policy

## Overview

This document outlines the backward compatibility policy for Protocol Buffer wire formats in the Marty gRPC services. These policies ensure that services can evolve without breaking existing clients or causing interoperability issues.

## Versioning Strategy

### Version 1 (v1) - Stabilized Wire Contract

Canonical protobuf definitions are under `proto/v1/` and generate into `marty_plugin.proto.v1`. The shipped `proto.v1` and checkout `src.proto.v1` namespaces remain compatibility aliases to the same modules. See [tooling ownership](features/compatibility-tooling-ownership.md) for regeneration. This is the first stable version of the wire protocol.

### Wire Format Stability Guarantees

The v1 protocol provides the following guarantees:

1. **Field Compatibility**: Field numbers will never be reused for different purposes
2. **Message Structure**: Core message structure remains stable
3. **Unknown Field Tolerance**: All services must gracefully handle unknown fields
4. **Enum Compatibility**: New enum values will only be added, never removed or changed
5. **Service Method Signatures**: Existing method signatures remain unchanged

## Compatibility Rules

### Safe Changes (Backward Compatible)

These changes can be made without breaking existing clients:

- Adding new optional fields
- Adding new enum values (with proper defaults)
- Adding new service methods
- Adding new messages
- Removing deprecated fields (after deprecation period)
- Changing field documentation/comments

### Breaking Changes (Require Major Version)

These changes require a new major version:

- Changing field numbers
- Changing field types
- Removing fields
- Removing enum values
- Removing service methods
- Changing service method signatures
- Changing required fields to optional or vice versa

### Deprecation Process

1. **Mark as Deprecated**: Add `[deprecated = true]` to the field/message/service
2. **Documentation**: Update documentation with migration path
3. **Grace Period**: Maintain support for at least 6 months
4. **Migration Support**: Provide tooling/documentation for migration
5. **Removal**: Remove in next major version only

## Testing and Validation

### Contract Tests

The system includes comprehensive contract tests under `tests/contracts/`:

- **Golden File Tests**: JSON serialization tests that detect unintended changes
- **Unknown Field Tests**: Verify graceful handling of unknown fields
- **Fuzz Tests**: Random data serialization/deserialization validation
- **Compatibility Tests**: Cross-version compatibility validation

### Running Contract Tests

```bash
# Run all contract tests
make test-contracts

# Generate/update golden files (development only)
make test-contracts-generate-golden

# Run specific service contract tests
uv run python -m pytest tests/contracts/test_document_signer_contracts.py -v
```

### Continuous Integration

Contract tests are automatically run in CI/CD to catch accidental breaking changes:

- Pre-commit hooks validate proto changes
- Pull request checks include contract tests
- Golden file mismatches fail the build
- Unknown field tolerance is validated

## Implementation Guidelines

### Service Implementation

All services must:

1. **Handle Unknown Fields**: Accept and preserve unknown fields in messages
2. **Default Values**: Use appropriate defaults for missing fields
3. **Error Handling**: Return structured errors using standard error messages
4. **Version Headers**: Include version information in service metadata

### Client Implementation

All clients should:

1. **Field Validation**: Validate required fields are present
2. **Graceful Degradation**: Handle missing optional fields gracefully
3. **Error Parsing**: Parse structured error responses
4. **Version Compatibility**: Check service version compatibility

### Proto File Organization

```
proto/v1/
├── common_services.proto      # Common types and errors
├── document_signer.proto      # Document signing service
├── trust_anchor.proto         # Trust verification service
├── passport_engine.proto      # Passport processing
├── mdl_engine.proto          # Mobile driver license
└── ...                       # Other service definitions
```

## Migration Path

### From Unversioned to v1

The migration from the original unversioned protos to v1 involves:

1. **Import Updates**: Change `from src.proto import` to `from src.proto.v1 import`
2. **Package Names**: Proto packages now include `v1` (e.g., `marty.signer.v1`)
3. **Generated Code**: Implementation at `src/marty_plugin/proto/v1/`; `src/proto/v1/` retains import aliases
4. **Build Scripts**: Updated protoc compilation paths

### Future Versions

When a v2 is needed:

1. Create `proto/v2/` directory
2. Copy and modify proto files as needed
3. Update package names to include `v2`
4. Maintain v1 support during transition period
5. Provide migration tooling and documentation

## Monitoring and Alerting

### Compatibility Monitoring

- **Wire Format Changes**: Monitor for unexpected message structure changes
- **Field Usage**: Track which fields are actively used by clients
- **Error Rates**: Monitor for increased error rates after deployments
- **Version Distribution**: Track client version distribution

### Breaking Change Detection

- **Schema Evolution**: Automated detection of breaking changes
- **Golden File Drift**: Alert on unexpected golden file changes  
- **Client Compatibility**: Monitor client connection success rates
- **Field Coverage**: Track which proto fields are being used

## Governance

### Change Approval Process

1. **Impact Assessment**: Evaluate compatibility impact
2. **Review Process**: Technical review by protocol stewards
3. **Testing Requirements**: Comprehensive contract test coverage
4. **Documentation**: Update compatibility documentation
5. **Rollout Plan**: Staged deployment with rollback procedures

### Protocol Stewards

- Architecture team reviews major changes
- Service owners approve service-specific changes
- Security team reviews security-sensitive protocol changes
- DevOps team validates operational impact

## Tools and Resources

### Development Tools

- `buf` - Protocol buffer linting and breaking change detection
- `protoc` - Protocol buffer compiler
- `grpcurl` - Command-line gRPC client for testing
- Contract test framework for validation

### Documentation

- [Protocol Buffers Guide](https://developers.google.com/protocol-buffers)
- [gRPC Documentation](https://grpc.io/docs/)
- [Buf Documentation](https://docs.buf.build/)
- Service-specific API documentation

## Examples

### Adding a New Field (Safe)

```protobuf
message SignRequest {
  string document_data = 1;
  string document_type = 2;
  string signing_algorithm = 3;

  // New optional field - safe to add
  string request_id = 4;
}
```

### Deprecating a Field

```protobuf
message SignRequest {
  string document_data = 1;
  string document_type = 2;

  // Deprecated field - will be removed in v2
  string signing_algorithm = 3 [deprecated = true];

  // New field replacing the deprecated one
  SigningAlgorithm algorithm = 4;
}
```

### Error Handling Example

```protobuf
message SignResponse {
  oneof result {
    SignedDocument success = 1;
    ApiError error = 2;
  }
}

message ApiError {
  ErrorCode code = 1;
  string message = 2;
  map<string, string> details = 3;
  string trace_id = 4;
}
```

This policy ensures that the Marty platform can evolve while maintaining backward compatibility and providing a stable foundation for service integration.
