#!/usr/bin/env python3
"""Seed the Marty org signing-key service registry via the gateway API.

Registers all signing services required by the Marty org credential catalog:

  marty-vc-jwt-signer    — VC-JWT and DC+SD-JWT issuance (ES256)
  marty-eddsa-signer     — VC-JWT and DC+SD-JWT issuance (EdDSA)
  marty-mdoc-dsc         — ISO 18013-5 mDoc document signer (ES256)
  marty-vdsnc-signer     — VDS-NC ICAO travel credential signer (ES256)

Format and type routing defaults are configured so that:
  • vds_nc credentials      → marty-vdsnc-signer
  • mso_mdoc / zk_mdoc      → marty-mdoc-dsc
  • jwt_vc_json / dc+sd-jwt → marty-vc-jwt-signer
  • ICAO credential types   → marty-vdsnc-signer

Usage
-----
  python seed_marty_org_catalog.py
  python seed_marty_org_catalog.py --gateway-url http://localhost:8000
  python seed_marty_org_catalog.py --gateway-url https://beta.elevenidllc.com --api-key <key> --dry-run

The script is idempotent: it reads the current registry, merges the desired
services (matching on ``id``), and only writes back when a change is detected.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required.  Install it with:  pip install httpx", file=sys.stderr)
    sys.exit(1)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_GATEWAY_URL = os.environ.get("MARTY_GATEWAY_URL", "http://localhost:8000")
DEFAULT_API_KEY = os.environ.get("MARTY_API_KEY", "")
MARTY_ORG_ID = "00000000-0000-0000-0000-000000000001"

# Signing key references — these must exist in OpenBao transit before running this script.
KEY_REF_ES256 = "cred-issuer-marty-es256"
KEY_REF_EDDSA = "cred-issuer-marty-eddsa"
KEY_REF_MDL_DSC = "cred-dsc-marty-primary"
KEY_REF_VDSNC = "cred-issuer-marty-vdsnc"

OPENBAO_ENDPOINT = os.environ.get("OPENBAO_ADDR", "http://localhost:8200")
OPENBAO_MOUNT = os.environ.get("OPENBAO_TRANSIT_MOUNT", "transit")
OPENBAO_TOKEN_REF = os.environ.get("OPENBAO_TOKEN_SECRET_REF", "bao-root-token")

# ---------------------------------------------------------------------------
# Desired service catalog
# ---------------------------------------------------------------------------

DESIRED_SERVICES: list[dict[str, Any]] = [
    # ------------------------------------------------------------------
    # VC-JWT / SD-JWT issuance — ES256
    # ------------------------------------------------------------------
    {
        "id": "marty-vc-jwt-signer",
        "name": "Marty VC-JWT / SD-JWT Signer (ES256)",
        "description": (
            "Primary OpenBao-backed ES256 signing service for W3C VC-JWT and "
            "DC+SD-JWT credential issuance by the Marty org."
        ),
        "service_type": "openbao-transit",
        "provider": "openbao",
        "endpoint": OPENBAO_ENDPOINT,
        "mount": OPENBAO_MOUNT,
        "auth_mode": "token",
        "auth_reference": OPENBAO_TOKEN_REF,
        "key_reference": KEY_REF_ES256,
        "algorithms": ["ES256"],
        "key_purposes": ["vc_jwt_issuer"],
        "credential_formats": ["jwt_vc_json", "dc+sd-jwt"],
    },
    # ------------------------------------------------------------------
    # VC-JWT / SD-JWT issuance — EdDSA
    # ------------------------------------------------------------------
    {
        "id": "marty-eddsa-signer",
        "name": "Marty VC-JWT / SD-JWT Signer (EdDSA)",
        "description": (
            "OpenBao-backed EdDSA signing service for W3C VC-JWT and "
            "DC+SD-JWT credential issuance by the Marty org."
        ),
        "service_type": "openbao-transit",
        "provider": "openbao",
        "endpoint": OPENBAO_ENDPOINT,
        "mount": OPENBAO_MOUNT,
        "auth_mode": "token",
        "auth_reference": OPENBAO_TOKEN_REF,
        "key_reference": KEY_REF_EDDSA,
        "algorithms": ["EdDSA"],
        "key_purposes": ["vc_jwt_issuer"],
        "credential_formats": ["jwt_vc_json", "dc+sd-jwt"],
    },
    # ------------------------------------------------------------------
    # ISO 18013-5 mDoc Document Signer
    # ------------------------------------------------------------------
    {
        "id": "marty-mdoc-dsc",
        "name": "Marty mDoc Document Signer (ES256)",
        "description": (
            "OpenBao-backed ES256 Document Signer Certificate key for "
            "ISO 18013-5 mDoc (mso_mdoc and zk_mdoc) issuance by the Marty org. "
            "Also used for mDL and member credential issuance."
        ),
        "service_type": "openbao-transit",
        "provider": "openbao",
        "endpoint": OPENBAO_ENDPOINT,
        "mount": OPENBAO_MOUNT,
        "auth_mode": "token",
        "auth_reference": OPENBAO_TOKEN_REF,
        "key_reference": KEY_REF_MDL_DSC,
        "algorithms": ["ES256"],
        "key_purposes": ["mdoc_dsc"],
        "credential_formats": ["mso_mdoc", "zk_mdoc"],
    },
    # ------------------------------------------------------------------
    # VDS-NC ICAO travel credential signer  (NEW — VDSNC-RUST pipeline)
    # ------------------------------------------------------------------
    {
        "id": "marty-vdsnc-signer",
        "name": "Marty VDS-NC ICAO Signer (ES256)",
        "description": (
            "OpenBao-backed ES256 signing service for ICAO VDS-NC travel "
            "document credentials (ePassport, DTC-1, DTC-2, visa, ETD) "
            "produced by the VDSNC-RUST signing pipeline. "
            "Key reference: " + KEY_REF_VDSNC
        ),
        "service_type": "openbao-transit",
        "provider": "openbao",
        "endpoint": OPENBAO_ENDPOINT,
        "mount": OPENBAO_MOUNT,
        "auth_mode": "token",
        "auth_reference": OPENBAO_TOKEN_REF,
        "key_reference": KEY_REF_VDSNC,
        "algorithms": ["ES256"],
        "key_purposes": ["vdsnc_signing"],
        "credential_formats": ["vds_nc"],
    },
]

# Credential-format routing defaults — resolve to service ID.
FORMAT_DEFAULTS: dict[str, str] = {
    "vds_nc":       "marty-vdsnc-signer",
    "mso_mdoc":     "marty-mdoc-dsc",
    "zk_mdoc":      "marty-mdoc-dsc",
    "jwt_vc_json":  "marty-vc-jwt-signer",
    "dc+sd-jwt":    "marty-vc-jwt-signer",
}

# Credential-type routing defaults (overrides format_defaults when present).
TYPE_DEFAULTS: dict[str, str] = {
    "com.icao.mrv":   "marty-vdsnc-signer",
    "com.icao.dtc.1": "marty-vdsnc-signer",
    "com.icao.dtc.2": "marty-vdsnc-signer",
    "com.icao.visa":  "marty-vdsnc-signer",
    "com.icao.etd":   "marty-vdsnc-signer",
    # mDL / member credential types default to the mDoc DSC signer
    "org.iso.18013.5.1.mDL":    "marty-mdoc-dsc",
    "com.marty.member.v1":      "marty-mdoc-dsc",
    # Login credential defaults to VC-JWT signer
    "com.marty.credential.login.v1": "marty-vc-jwt-signer",
    "OpenBadgeCredential":           "marty-vc-jwt-signer",
    "AccessBadgeCredential":         "marty-vc-jwt-signer",
}

DEFAULT_SERVICE_ID = "marty-vc-jwt-signer"

# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def _build_desired_registry(existing_services: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge desired services into existing, preserving runtime fields."""
    desired_by_id = {s["id"]: s for s in DESIRED_SERVICES}
    existing_by_id = {s["id"]: s for s in existing_services if isinstance(s, dict)}

    merged: list[dict[str, Any]] = []

    # Keep existing services that are NOT in our desired set (don't clobber them)
    for svc_id, svc in existing_by_id.items():
        if svc_id not in desired_by_id:
            merged.append(svc)

    # Upsert our desired services, preserving runtime-only keys from existing entries
    RUNTIME_KEYS = {"created_at", "updated_at", "discovered_capabilities", "status", "x5c"}
    for desired in DESIRED_SERVICES:
        svc_id = desired["id"]
        existing = existing_by_id.get(svc_id, {})
        merged_service = {**desired}
        for key in RUNTIME_KEYS:
            if key in existing:
                merged_service.setdefault(key, existing[key])
        merged.append(merged_service)

    return {
        "services": merged,
        "default_service_id": DEFAULT_SERVICE_ID,
        "format_defaults": FORMAT_DEFAULTS,
        "type_defaults": TYPE_DEFAULTS,
    }


def _registry_needs_update(
    current: dict[str, Any],
    desired: dict[str, Any],
) -> bool:
    """Return True if the desired registry differs from the current one."""
    current_ids = {s["id"] for s in current.get("services", []) if isinstance(s, dict)}
    desired_ids = {s["id"] for s in desired.get("services", [])}
    if not desired_ids.issubset(current_ids):
        return True

    if current.get("format_defaults") != desired.get("format_defaults"):
        return True

    if current.get("type_defaults") != desired.get("type_defaults"):
        return True

    if current.get("default_service_id") != desired.get("default_service_id"):
        return True

    # Deep-check each desired service against its current counterpart
    current_by_id = {s["id"]: s for s in current.get("services", []) if isinstance(s, dict)}
    CHECK_KEYS = {
        "key_reference", "algorithms", "key_purposes", "credential_formats",
        "service_type", "endpoint", "mount", "auth_mode",
    }
    for desired_svc in desired.get("services", []):
        svc_id = desired_svc.get("id")
        if svc_id not in current_by_id:
            return True
        current_svc = current_by_id[svc_id]
        for key in CHECK_KEYS:
            if desired_svc.get(key) != current_svc.get(key):
                return True

    return False


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------


class GatewayClient:
    def __init__(self, base_url: str, api_key: str, org_id: str) -> None:
        self._base = base_url.rstrip("/")
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._org_id = org_id

    @property
    def _org_param(self) -> dict[str, str]:
        return {"organization_id": self._org_id} if self._org_id else {}

    async def get_config(self, client: httpx.AsyncClient) -> dict[str, Any]:
        url = f"{self._base}/v1/signing-keys/config"
        resp = await client.get(url, params=self._org_param, headers=self._headers)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()

    async def patch_config(
        self,
        client: httpx.AsyncClient,
        registry: dict[str, Any],
    ) -> dict[str, Any]:
        url = f"{self._base}/v1/signing-keys/config"
        resp = await client.patch(
            url,
            params=self._org_param,
            headers=self._headers,
            content=json.dumps(registry),
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------


async def seed(
    gateway_url: str,
    api_key: str,
    org_id: str,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Seed the signing key registry.  Returns 0 on success, non-zero on failure."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )

    gw = GatewayClient(gateway_url, api_key, org_id)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Read current state
        logger.info("Reading current signing-key registry from %s …", gateway_url)
        try:
            current_config = await gw.get_config(client)
        except httpx.HTTPStatusError as exc:
            logger.error("Failed to read registry: HTTP %s — %s", exc.response.status_code, exc.response.text)
            return 1
        except httpx.RequestError as exc:
            logger.error("Failed to connect to gateway: %s", exc)
            return 1

        current_services = current_config.get("services") or []
        logger.info("  → %d existing service(s) found", len(current_services))

        if verbose:
            existing_ids = [s.get("id") for s in current_services if isinstance(s, dict)]
            logger.debug("  existing service IDs: %s", existing_ids)

        # 2. Build desired state
        desired_registry = _build_desired_registry(current_services)

        # 3. Diff check
        if not _registry_needs_update(current_config, desired_registry):
            logger.info("Registry is already up-to-date. No changes needed.")
            return 0

        # 4. Report changes
        desired_ids = {s["id"] for s in desired_registry["services"]}
        existing_ids_set = {s.get("id") for s in current_services if isinstance(s, dict)}
        new_ids = desired_ids - existing_ids_set
        if new_ids:
            logger.info("  → New services to register: %s", sorted(new_ids))
        logger.info("  → format_defaults: %s", desired_registry["format_defaults"])
        logger.info("  → type_defaults: %d entries", len(desired_registry["type_defaults"]))

        if dry_run:
            logger.info("[DRY RUN] Would PATCH /v1/signing-keys/config with %d services.", len(desired_registry["services"]))
            logger.info("[DRY RUN] Desired registry:")
            logger.info("%s", json.dumps(desired_registry, indent=2))
            return 0

        # 5. Apply
        logger.info("Applying signing-key registry via PATCH /v1/signing-keys/config …")
        try:
            result = await gw.patch_config(client, desired_registry)
        except httpx.HTTPStatusError as exc:
            logger.error("PATCH failed: HTTP %s — %s", exc.response.status_code, exc.response.text)
            return 1
        except httpx.RequestError as exc:
            logger.error("PATCH request failed: %s", exc)
            return 1

        applied_services = result.get("services") or []
        logger.info("  ✓ Registry updated. Active services: %d", len(applied_services))
        for svc in applied_services:
            if isinstance(svc, dict):
                logger.info(
                    "    • %-35s  %-22s  %s",
                    svc.get("id", "—"),
                    svc.get("key_reference", "—"),
                    "/".join(svc.get("algorithms") or []),
                )

        return 0


# ---------------------------------------------------------------------------
# Summary — catalog reference
# ---------------------------------------------------------------------------

CATALOG_SUMMARY = """
Marty Org Credential Catalog — Full Reference
=============================================

Signing Services (this script)
-------------------------------
  marty-vc-jwt-signer  ES256   vc_jwt_issuer     jwt_vc_json, dc+sd-jwt
  marty-eddsa-signer   EdDSA   vc_jwt_issuer     jwt_vc_json, dc+sd-jwt
  marty-mdoc-dsc       ES256   mdoc_dsc          mso_mdoc, zk_mdoc
  marty-vdsnc-signer   ES256   vdsnc_signing     vds_nc

Credential Templates  (migration 20260417_0001 + earlier migrations)
----------------------------------------------------------------------
  50000000-…-0010  Marty Login Credential           SD-JWT / VC-JWT
  50000000-…-0020  ISO 18013-5 mDL                  mso_mdoc
  50000000-…-0030  mDoc Member Credential           mso_mdoc
  50000000-…-0040  Open Badge (v3)                  jwt_vc_json
  50000000-…-0050  Employee Access Badge            jwt_vc_json
  50000000-…-0060  ICAO ePassport / MRV             vds_nc + mso_mdoc  (NEW)
  50000000-…-0070  ICAO DTC Type 1                  vds_nc             (NEW)
  50000000-…-0080  ICAO DTC Type 2                  vds_nc             (NEW)
  50000000-…-0090  ICAO Visa                        vds_nc             (NEW)
  50000000-…-00a0  ICAO Emergency Travel Document   vds_nc             (NEW)

Trust Profiles  (migrations marty_trust_seed_001–003)
------------------------------------------------------
  60000000-…-0001  Marty Credential Login Trust          SD_JWT_VC, MDOC
  60000000-…-0002  ICAO Travel Document Verification     VDS_NC, MDOC    (NEW)
  60000000-…-0003  Mobile Driver's License (AAMVA)       MDOC, SD_JWT_VC (NEW)

Format / Type Routing Defaults
-------------------------------
  vds_nc                     → marty-vdsnc-signer
  mso_mdoc, zk_mdoc          → marty-mdoc-dsc
  jwt_vc_json, dc+sd-jwt     → marty-vc-jwt-signer
  com.icao.*                 → marty-vdsnc-signer
  org.iso.18013.5.1.mDL      → marty-mdoc-dsc
  OpenBadgeCredential        → marty-vc-jwt-signer
"""


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Seed the Marty org signing-key catalog via the gateway API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CATALOG_SUMMARY,
    )
    p.add_argument(
        "--gateway-url",
        default=DEFAULT_GATEWAY_URL,
        help=f"Gateway base URL (default: {DEFAULT_GATEWAY_URL} / env MARTY_GATEWAY_URL)",
    )
    p.add_argument(
        "--api-key",
        default=DEFAULT_API_KEY,
        help="API key / Bearer token (default: env MARTY_API_KEY)",
    )
    p.add_argument(
        "--org-id",
        default=MARTY_ORG_ID,
        help=f"Organisation ID to seed (default: {MARTY_ORG_ID})",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be applied without making any HTTP writes.",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    p.add_argument(
        "--catalog",
        action="store_true",
        help="Print the full credential catalog reference and exit.",
    )
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.catalog:
        print(CATALOG_SUMMARY)
        return

    exit_code = asyncio.run(
        seed(
            gateway_url=args.gateway_url,
            api_key=args.api_key,
            org_id=args.org_id,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
