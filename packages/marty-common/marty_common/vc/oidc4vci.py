"""Data structures for OIDC4VCI flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class CredentialOfferGrantPreAuthorizedCode:
    """Grant structure for the pre-authorized code flow."""

    pre_authorized_code: str
    user_pin_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "pre-authorized_code": self.pre_authorized_code,
            "user_pin_required": self.user_pin_required,
        }


@dataclass(slots=True)
class CredentialOfferGrant:
    """Container for grants supported by the issuer."""

    pre_authorized_code: CredentialOfferGrantPreAuthorizedCode | None = None

    def to_dict(self) -> dict[str, Any]:
        grants: dict[str, Any] = {}
        if self.pre_authorized_code is not None:
            grants["urn:ietf:params:oauth:grant-type:pre-authorized_code"] = (
                self.pre_authorized_code.to_dict()
            )
        return grants


@dataclass(slots=True)
class CredentialOffer:
    """Serializable model for an OIDC4VCI credential offer."""

    credential_issuer: str
    credentials: list[dict[str, Any]]
    grants: CredentialOfferGrant
    credential_configuration_ids: list[str] | None = None
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "credential_issuer": self.credential_issuer,
            "credentials": self.credentials,
        }
        grants_dict = self.grants.to_dict()
        if grants_dict:
            data["grants"] = grants_dict
        if self.credential_configuration_ids:
            data["credential_configuration_ids"] = self.credential_configuration_ids
        if self.session_id:
            data["session_id"] = self.session_id
        return data


@dataclass(slots=True)
class Oidc4VciSession:
    """Book-keeping model describing the state of an issuance session."""

    offer_id: str
    subject_id: str
    credential_type: str
    expires_at: datetime
    pre_authorized_code: str
    access_token: str | None = None
    status: str = "offer_created"
    nonce: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "CredentialOffer",
    "CredentialOfferGrant",
    "CredentialOfferGrantPreAuthorizedCode",
    "Oidc4VciSession",
]
