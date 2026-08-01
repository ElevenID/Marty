"""Resource-owner lookup contracts for tenant authorization."""

from marty_common.cedar_actions import resolve_resource_lookup


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


def test_public_protocol_and_collection_routes_do_not_become_owner_lookups() -> None:
    assert resolve_resource_lookup("/v1/issuance/offers/transaction-b") is None
    assert resolve_resource_lookup("/v1/issued-credentials/mine") is None
    assert resolve_resource_lookup("/v1/trust-profiles") is None
