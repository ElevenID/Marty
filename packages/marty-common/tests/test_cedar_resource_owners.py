"""Resource-owner lookup contracts for tenant authorization."""

from marty_common.cedar_actions import (
    resolve_action_and_resource,
    resolve_resource_lookup,
)


def test_identifier_routes_use_minimal_internal_owner_lookups() -> None:
    assert resolve_resource_lookup("/v1/issuance/transaction-b") == (
        "issuance",
        "/internal/v1/resource-owners/issuance-transactions/transaction-b",
    )
    assert resolve_resource_lookup("/v1/issued-credentials/credential-b/revoke") == (
        "issuance",
        "/internal/v1/resource-owners/issued-credentials/credential-b",
    )
    assert resolve_resource_lookup("/v1/application-templates/template-b") == (
        "issuance",
        "/internal/v1/resource-owners/application-templates/template-b",
    )
    assert resolve_resource_lookup("/v1/trust-profiles/profile-b/activate") == (
        "trust-profiles",
        "/internal/v1/resource-owners/trust-profiles/profile-b",
    )
    assert resolve_resource_lookup("/v1/issuer-entities/issuer-b") == (
        "trust-profiles",
        "/internal/v1/resource-owners/issuer-entities/issuer-b",
    )


def test_issuance_revocation_status_combines_action_and_owner_lookup() -> None:
    path = "/v1/issuance/transaction-b/revocation-status"

    for method in ("GET", "HEAD", "OPTIONS"):
        assert resolve_action_and_resource(method, path) == (
            "issuance:view",
            "issuance",
        )
    assert resolve_action_and_resource("POST", path) is None
    assert resolve_resource_lookup(path) == (
        "issuance",
        "/internal/v1/resource-owners/issuance-transactions/transaction-b",
    )


def test_public_protocol_and_collection_routes_do_not_become_owner_lookups() -> None:
    assert resolve_resource_lookup("/v1/issuance/offers/transaction-b") is None
    assert (
        resolve_resource_lookup(
            "/v1/issuance/delivery-records/canvas-credentials/provenance"
        )
        is None
    )
    assert (
        resolve_resource_lookup(
            "/v1/issuance/organizations/org-a/canvas-mirror-health"
        )
        is None
    )
    assert resolve_resource_lookup("/v1/issuance/oid4vci-clients") is None
    assert resolve_resource_lookup("/v1/issued-credentials/mine") is None
    assert resolve_resource_lookup("/v1/trust-profiles") is None
    assert resolve_resource_lookup("/v1/issuer-entities") is None
