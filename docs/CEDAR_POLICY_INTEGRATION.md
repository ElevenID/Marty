# Cedar policy integration

## Current engine and installation

The Python compatibility package provides synchronous, in-process authorization
through [CedarEngine](../packages/marty-common/marty_common/cedar_engine.py) and
`cedarpy`. Its dependency is declared in
[marty-common's package metadata](../packages/marty-common/pyproject.toml);
install that package from the repository root:

```sh
python -m pip install ./packages/marty-common
```

The former `requirements_cedar.txt` listed dependencies for a proposed YAML
rule-pack service. It did not install the current engine. There are no tracked
Python consumers of its `watchdog` or `jsonschema` dependencies.

## Policy sets and evaluation

Policies and schemas ship in the
[cedar directory](../packages/marty-common/marty_common/cedar/).
Choose the policy set for the decision being made:

| Factory | Policy scope |
| --- | --- |
| `CedarEngine.with_defaults()` | MIP schema and gateway role policies |
| `CedarEngine.with_credential_verification()` | Gateway policies plus credential-verification rules |
| `CedarEngine.with_approval_rules()` | Approval policies only |
| `CedarEngine.with_approval_policy_text(policies)` | Caller-provided approval policies with the MIP schema |
| `CedarEngine.from_files(schema_path, policy_paths)` | Explicit schema and policy files; directories contribute `*.cedar` files |

Approval decisions deliberately exclude broad gateway permits. Keep policy
selection explicit; adding gateway policies to an approval engine can change
which requests are permitted.

`is_authorized(principal, action, resource, context, entities)` accepts Cedar UID
strings, an action-specific context record and entity dictionaries containing
`uid`, `attrs` and `parents`. It returns `AuthzDecision` with `allowed`,
`reasons` and `errors`. Evaluation exceptions produce a denied decision with
errors; callers must enforce the decision and must not treat errors as permission.

This example demonstrates a denied gateway request with no role membership:

```python
from marty_common.cedar_engine import CedarEngine
from marty_common.cedar_entities import build_request_context

engine = CedarEngine.with_defaults()
decision = engine.is_authorized(
    principal='MIP::User::"unassigned-user"',
    action='MIP::Action::"credentials:read"',
    resource='MIP::Organization::"example-org"',
    context=build_request_context("127.0.0.1"),
    entities=[],
)
assert not decision.allowed
```

Real callers supply authenticated identity and organization facts using the
[entity builders](../packages/marty-common/marty_common/cedar_entities.py).
Route mapping and HTTP enforcement live in
[cedar_actions.py](../packages/marty-common/marty_common/cedar_actions.py) and
[cedar_middleware.py](../packages/marty-common/marty_common/cedar_middleware.py).
This engine does not establish those facts or enforce a transport boundary by itself.

File loading reads the current contents when the factory runs. The
`policies` setter and `append_policies()` change an instance's policy text;
they do not provide file watching, validated activation or rollback.
The engine does not load cross-zone YAML rule packs.

## Cross-zone feature requirements retained

The previous guide described a separate document-consistency feature as if it
were operational. Its Python `CedarPolicyEngine`, asynchronous initialization,
rule-pack loader and demo are absent from this repository. The retained
[consistency-engine protobuf](../proto/consistency_engine.proto),
[document schema](../config/cedar_schema.cedarschema),
[rule-pack schema proposal](../config/rule_pack_schema.yaml), and
[passport](../config/rules/passport_rules.yaml),
[driver's license](../config/rules/drivers_license_rules.yaml) and
[national-ID](../config/rules/national_id_rules.yaml) definitions preserve intent.
They are not evidence of an implemented service or inputs accepted by `CedarEngine`.

The following remain requirements for a future implementation and qualification:

- Model document zones, fields, document types, validation rules and comparison
  contexts; support field consistency, cross-zone matching, checksums, dates and
  hashes across OCR, MRZ, barcode and RFID evidence.
- Load versioned, country-aware document rule packs with canonical field mappings,
  validation rules and Cedar policies. Define schema and policy validation before
  activation, plus controlled reload and rollback behavior.
- Define strict, lenient and adaptive validation modes, including confidence,
  fuzzy-match and document-quality thresholds.
- Implement and qualify the rule-pack, validation-mode and evaluation RPCs in the
  protobuf before advertising them. REST exposure needs its own defined contract.
- Specify safe hot reload, caching, concurrency and evaluation limits; qualify
  staged migration, feature flags and any traditional-rule fallback without
  silently allowing failed authorization.
- Provide evaluation/load/reload metrics, audit events and health checks.
  The formerly advertised metric names and `CEDAR_*` environment variables
  are proposals, not configuration consumed by this engine.
- Treat the visual rule builder, rule testing framework, optimization analytics,
  cloud integration and live dashboard as future proposals requiring ownership
  and acceptance criteria.

Installing a file watcher or schema validator does not implement these features.
Their dependencies should be declared with the component that actually uses them.

## Existing verification

Authorization regression coverage includes
[credential revocation decisions](../packages/marty-common/tests/test_credential_verification_cedar.py),
[failed resource lookups](../packages/marty-common/tests/test_cedar_lookup_fail_closed.py),
[resource ownership](../packages/marty-common/tests/test_cedar_resource_owners.py) and
[audit routes](../packages/marty-common/tests/test_cedar_audit_routes.py).
These tests qualify their covered authorization behavior, not the proposed
cross-zone service.
