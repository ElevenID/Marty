"""Thin authenticated adapter to the canonical Rust wallet-offer boundary."""

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from app.models.doc_models_clean import PreTravelWalletOffer


class PreTravelIssuanceError(RuntimeError):
    """Safe public error; never attach an upstream response or bearer capability."""


@dataclass(frozen=True, slots=True)
class PreTravelIssuanceConfig:
    base_url: str = field(
        default_factory=lambda: os.getenv("PRETRAVEL_ISSUANCE_URL", "")
    )
    organization_id: str = field(
        default_factory=lambda: os.getenv("PRETRAVEL_ORGANIZATION_ID", "")
    )
    issuer_did: str = field(
        default_factory=lambda: os.getenv("PRETRAVEL_ISSUER_DID", "")
    )
    template_id: str = field(
        default_factory=lambda: os.getenv("PRETRAVEL_TEMPLATE_ID", "")
    )
    credential_issuer_url: str = field(
        default_factory=lambda: os.getenv("PRETRAVEL_CREDENTIAL_ISSUER_URL", "")
    )
    api_key_file: str = field(
        default_factory=lambda: os.getenv("PRETRAVEL_ISSUANCE_API_KEY_FILE", ""),
        repr=False,
    )

    def endpoint(self) -> str:
        try:
            url = urlsplit(self.base_url)
            _ = url.port
            valid = (
                url.scheme == "https"
                and not any(character.isspace() for character in self.base_url)
                and bool(url.hostname)
                and not url.username
                and not url.password
                and url.path in ("", "/")
                and not url.query
                and not url.fragment
                and all(
                    value.strip()
                    for value in (
                        self.organization_id,
                        self.issuer_did,
                        self.template_id,
                    )
                )
                and self.issuer_did.startswith("did:")
            )
        except ValueError:
            valid = False
        if not valid:
            raise PreTravelIssuanceError(
                "Pretravel Rust issuance configuration is unavailable"
            )
        return self.base_url.rstrip("/") + "/v1/issuance/initiate"

    def api_key(self) -> str:
        try:
            key = (
                Path(self.api_key_file).read_text(encoding="utf-8").strip()
                if self.api_key_file
                else ""
            )
        except (OSError, UnicodeError):
            key = ""
        if not key or len(key) > 4096 or any(character.isspace() for character in key):
            raise PreTravelIssuanceError(
                "Pretravel Rust issuance credentials are unavailable"
            )
        return key


class RustPreTravelIssuance:
    def __init__(
        self,
        config: PreTravelIssuanceConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.config = config
        self.transport = transport

    async def offer(self, claims: dict) -> PreTravelWalletOffer:
        endpoint = self.config.endpoint()
        key = self.config.api_key()
        request = {
            "organization_id": self.config.organization_id,
            "issuer_did": self.config.issuer_did,
            "credential_template_id": self.config.template_id,
            "delivery_mode": "wallet_only",
            "claims": claims,
        }
        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=10,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                async with client.stream(
                    "POST", endpoint, json=request, headers={"X-API-Key": key}
                ) as response:
                    if response.status_code != 200:
                        raise PreTravelIssuanceError(
                            "Rust issuance did not create a wallet offer"
                        )
                    content = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        if len(content) + len(chunk) > 65536:
                            raise PreTravelIssuanceError(
                                "Rust issuance returned an invalid wallet offer"
                            )
                        content.extend(chunk)
            # JSON validation preserves RFC3339 dates with strict scalar field types.
            offer = PreTravelWalletOffer.model_validate_json(bytes(content))
            if (
                offer.organization_id != self.config.organization_id
                or offer.credential_template_id != self.config.template_id
                or offer.expires_at.tzinfo is None
                or offer.expires_at <= datetime.now(UTC)
            ):
                raise ValueError("offer binding")
            # Check the canonical embedded offer before exposing its bearer link.
            uri = urlsplit(offer.credential_offer_uri)
            parameters = parse_qs(
                uri.query, strict_parsing=True, keep_blank_values=True
            )
            if (
                uri.scheme != "openid-credential-offer"
                or uri.netloc
                or uri.path
                or uri.fragment
            ):
                raise ValueError("offer URI")
            if (
                set(parameters) != {"credential_offer"}
                or len(parameters["credential_offer"]) != 1
            ):
                raise ValueError("offer parameters")
            embedded = json.loads(parameters["credential_offer"][0])
            expected_issuer = self.config.credential_issuer_url or (
                self.config.base_url.rstrip("/") + "/org/" + self.config.organization_id
            )
            if (
                embedded.get("credential_issuer") != expected_issuer
                or embedded.get("grants", {})
                .get("urn:ietf:params:oauth:grant-type:pre-authorized_code", {})
                .get("pre-authorized_code")
                != offer.pre_auth_code
            ):
                raise ValueError("offer issuer or grant")
            return offer
        except PreTravelIssuanceError:
            raise
        except (
            httpx.HTTPError,
            httpx.InvalidURL,
            ValueError,
            TypeError,
            AttributeError,
        ):
            raise PreTravelIssuanceError(
                "Rust issuance returned no usable wallet offer"
            ) from None
