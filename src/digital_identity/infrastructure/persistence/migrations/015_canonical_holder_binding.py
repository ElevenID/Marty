"""Normalize persisted PresentationPolicy holder-binding configuration.

Revision ID: 015_canonical_holder_binding
Revises: 014_ob3_trust_anchors
Create Date: 2026-07-15
"""

import json

import sqlalchemy as sa
from alembic import op


revision = "015_canonical_holder_binding"
down_revision = "014_ob3_trust_anchors"
branch_labels = None
depends_on = None


def _as_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {"required": value != "NONE", "binding_methods": [value]}
    return {"required": False}


def _canonical(value: object) -> dict:
    old = _as_dict(value)
    required = bool(old.get("required", False))
    if not required:
        return {"required": False}

    methods = []
    for method in old.get("binding_methods", []):
        mapped = {
            "NONCE": "SESSION_BINDING",
            "BIOMETRIC": "DEVICE_KEY",
        }.get(method, method)
        if mapped in {"CREDENTIAL_KEY", "DEVICE_KEY", "SESSION_BINDING"} and mapped not in methods:
            methods.append(mapped)
    if not methods:
        methods = ["DEVICE_KEY"]

    return {
        "required": True,
        "binding_methods": methods,
        "proof_profiles": old.get("proof_profiles") or ["OID4VP_VERIFIABLE_PRESENTATION"],
        "proof_freshness": old.get("proof_freshness") or {
            "challenge_required": True,
            "audience_binding_required": True,
            "replay_detection_required": True,
        },
    }


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, holder_binding FROM digital_identity_presentation_policies")
    ).fetchall()
    for row_id, holder_binding in rows:
        connection.execute(
            sa.text(
                "UPDATE digital_identity_presentation_policies "
                "SET holder_binding = :holder_binding WHERE id = :id"
            ),
            {"holder_binding": json.dumps(_canonical(holder_binding)), "id": row_id},
        )


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, holder_binding FROM digital_identity_presentation_policies")
    ).fetchall()
    for row_id, holder_binding in rows:
        current = _as_dict(holder_binding)
        methods = [
            "NONCE" if method == "SESSION_BINDING" else method
            for method in current.get("binding_methods", [])
        ]
        legacy = {
            "required": bool(current.get("required", False)),
            "binding_methods": methods,
            "nonce_required": "NONCE" in methods,
        }
        connection.execute(
            sa.text(
                "UPDATE digital_identity_presentation_policies "
                "SET holder_binding = :holder_binding WHERE id = :id"
            ),
            {"holder_binding": json.dumps(legacy), "id": row_id},
        )
