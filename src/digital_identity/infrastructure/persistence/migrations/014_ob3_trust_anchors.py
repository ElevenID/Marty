"""
Migration: Add DID/JWK trust anchor support + seed OB3 anchors

Schema changes:
- trust_framework_anchors: make certificate_der/certificate_hash nullable
  (DID-based anchors have no X.509 certificate)
- trust_framework_anchors: add issuer_did (VARCHAR 500, indexed) and
  issuer_jwk (JSON, nullable) columns for Open Badge / DID-based anchors

Seed data:
- Insert system OB3 trust anchor for Marty platform issuer DID
  (did:web:marty.example.com) linked to the tf-ob3-system framework

Revision ID: 014_ob3_trust_anchors
Revises: 013_seed_system_trust_frameworks
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

import json
from datetime import datetime, timezone


revision = '014_ob3_trust_anchors'
down_revision = '013_seed_system_trust_frameworks'
branch_labels = None
depends_on = None


# OB3 system trust anchors (pinned issuer DIDs)
OB3_TRUST_ANCHORS = [
    {
        "id": "ta-ob3-marty-system",
        "framework_id": "tf-ob3-system",
        "anchor_type": "issuer_did",
        "jurisdiction": None,
        "certificate_der": None,
        "certificate_hash": None,
        "subject": "Marty Platform (System Issuer)",
        "issuer": "did:web:marty.example.com",
        "issuer_did": "did:web:marty.example.com",
        "issuer_jwk": {
            "kty": "EC",
            "crv": "P-256",
            "x": "_PLACEHOLDER_",
            "y": "_PLACEHOLDER_",
        },
        "source": "pinned_issuer",
    },
]


def upgrade() -> None:
    """Add DID/JWK columns and seed OB3 trust anchors."""

    # ── Schema changes ────────────────────────────────────
    # Make certificate columns nullable (DID anchors have no cert)
    with op.batch_alter_table('trust_framework_anchors') as batch_op:
        batch_op.alter_column(
            'certificate_der',
            existing_type=sa.LargeBinary(),
            nullable=True,
        )
        batch_op.alter_column(
            'certificate_hash',
            existing_type=sa.String(64),
            nullable=True,
        )
        # Add DID/JWK columns
        batch_op.add_column(
            sa.Column('issuer_did', sa.String(500), nullable=True),
        )
        batch_op.add_column(
            sa.Column('issuer_jwk', sa.JSON(), nullable=True),
        )
        batch_op.create_index('ix_trust_framework_anchors_issuer_did', ['issuer_did'])

    # ── Seed OB3 trust anchors ────────────────────────────
    bind = op.get_bind()
    now = datetime.now(timezone.utc).isoformat()

    for anchor in OB3_TRUST_ANCHORS:
        row = bind.execute(
            text("SELECT id FROM trust_framework_anchors WHERE id = :id"),
            {"id": anchor["id"]},
        ).fetchone()

        if not row:
            bind.execute(
                text("""
                    INSERT INTO trust_framework_anchors
                        (id, framework_id, anchor_type, jurisdiction,
                         certificate_der, certificate_hash, subject, issuer,
                         issuer_did, issuer_jwk,
                         source, synced_at, created_at)
                    VALUES
                        (:id, :framework_id, :anchor_type, :jurisdiction,
                         :certificate_der, :certificate_hash, :subject, :issuer,
                         :issuer_did, :issuer_jwk,
                         :source, :now, :now)
                """),
                {
                    "id": anchor["id"],
                    "framework_id": anchor["framework_id"],
                    "anchor_type": anchor["anchor_type"],
                    "jurisdiction": anchor["jurisdiction"],
                    "certificate_der": anchor["certificate_der"],
                    "certificate_hash": anchor["certificate_hash"],
                    "subject": anchor["subject"],
                    "issuer": anchor["issuer"],
                    "issuer_did": anchor["issuer_did"],
                    "issuer_jwk": json.dumps(anchor["issuer_jwk"]),
                    "source": anchor["source"],
                    "now": now,
                },
            )


def downgrade() -> None:
    """Remove DID/JWK columns and OB3 trust anchors."""
    bind = op.get_bind()

    # Remove seeded OB3 anchors
    for anchor in OB3_TRUST_ANCHORS:
        bind.execute(
            text("DELETE FROM trust_framework_anchors WHERE id = :id"),
            {"id": anchor["id"]},
        )

    with op.batch_alter_table('trust_framework_anchors') as batch_op:
        batch_op.drop_index('ix_trust_framework_anchors_issuer_did')
        batch_op.drop_column('issuer_jwk')
        batch_op.drop_column('issuer_did')
        batch_op.alter_column(
            'certificate_hash',
            existing_type=sa.String(64),
            nullable=False,
        )
        batch_op.alter_column(
            'certificate_der',
            existing_type=sa.LargeBinary(),
            nullable=False,
        )
