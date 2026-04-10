#!/usr/bin/env python3
"""
Generate Dev License

Creates an Ed25519 key pair and a dev-mode license JWT for local development.
Writes to docker/dev-license/license.key and docker/dev-license/license.pub.

Usage:
    python scripts/generate-dev-license.py
    python scripts/generate-dev-license.py --tier institution --days 365
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# Allow import from src/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from licensing.service import DEFAULT_ENTITLEMENTS, VALID_PLAN_TIERS

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docker" / "dev-license"
LICENSE_FILE = OUTPUT_DIR / "license.key"
PUBLIC_KEY_FILE = OUTPUT_DIR / "license.pub"

DEV_ORG_ID = "dev-org-00000000"
DEV_ORG_NAME = "Local Development"


def generate_dev_license(
    tier: str = "institution",
    duration_days: int = 365,
) -> tuple[str, str, str]:
    """
    Generate a dev Ed25519 key pair and license JWT.

    Returns (jwt_str, private_pem, public_pem).
    """
    if tier not in VALID_PLAN_TIERS:
        raise ValueError(f"Invalid tier '{tier}'. Must be one of: {VALID_PLAN_TIERS}")

    # Generate fresh Ed25519 key pair
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    # Build license claims — all products entitled for dev convenience
    defaults = DEFAULT_ENTITLEMENTS[tier]
    now = int(datetime.now(timezone.utc).timestamp())
    exp = now + (duration_days * 86400)

    claims = {
        "iss": "marty-license-issuer",
        "sub": DEV_ORG_ID,
        "iat": now,
        "exp": exp,
        "nbf": now,
        "jti": f"dev_{uuid4().hex[:16]}",
        "org_name": DEV_ORG_NAME,
        "plan_tier": tier,
        "entitled_products": list(
            {
                "verifier", "document-signer", "passport-engine", "csca-service",
                "inspection-system", "document-processing", "mdl-engine",
                "oid4vc-api", "ui-app", "open-badges", "trust-anchor",
                "dtc-engine", "mdoc-engine", "pkd-service", "mmf-plugin",
            }
        ),
        "features": defaults["features"] if defaults["features"] != ["*"] else [
            "mdl", "emrtd", "oid4vp", "sd-jwt", "open-badges",
            "usb-sync", "reporting",
        ],
        "max_instances": defaults["max_instances"],
        "registry_access": True,
        "api_calls_limit": 0,  # unlimited for dev
        "deployment_mode": "development",
        "grace_period_days": defaults["grace_period_days"],
    }

    jwt_str = pyjwt.encode(claims, private_key, algorithm="EdDSA")
    return jwt_str, private_pem, public_pem


def main():
    parser = argparse.ArgumentParser(description="Generate a dev license for local Docker development")
    parser.add_argument("--tier", default="institution", choices=sorted(VALID_PLAN_TIERS),
                        help="Plan tier (default: institution)")
    parser.add_argument("--days", type=int, default=365,
                        help="License validity in days (default: 365)")
    args = parser.parse_args()

    jwt_str, private_pem, public_pem = generate_dev_license(tier=args.tier, duration_days=args.days)

    # Write output files
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LICENSE_FILE.write_text(jwt_str + "\n")
    PUBLIC_KEY_FILE.write_text(public_pem)

    # Also write the private key for test/admin use
    private_key_file = OUTPUT_DIR / "license-private.pem"
    private_key_file.write_text(private_pem)
    os.chmod(private_key_file, 0o600)

    print(f"Dev license generated ({args.tier} tier, {args.days} days):")
    print(f"  License JWT:  {LICENSE_FILE}")
    print(f"  Public key:   {PUBLIC_KEY_FILE}")
    print(f"  Private key:  {private_key_file}")
    print()
    print("Add to .gitignore if not already present:")
    print("  docker/dev-license/")


if __name__ == "__main__":
    main()
