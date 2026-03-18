"""
Migration: holder_binding JSON, vct, ApplicationTemplate status

- PresentationPolicy: holder_binding String(50) → JSON (with data migration)
- CredentialTemplate: add vct column
- ApplicationTemplate: add status column

Revision ID: 009_holder_binding_vct_status
Revises: 008_persistence_alignment
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '009_holder_binding_vct_status'
down_revision = '008_persistence_alignment'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- CredentialTemplate: add vct ---
    with op.batch_alter_table('digital_identity_credential_templates') as batch_op:
        batch_op.add_column(sa.Column('vct', sa.String(500), nullable=True))

    # --- ApplicationTemplate: add status ---
    with op.batch_alter_table('digital_identity_application_templates') as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(50), nullable=False, server_default='DRAFT'))

    # --- PresentationPolicy: holder_binding String → JSON ---
    # Step 1: Add a temporary JSON column
    with op.batch_alter_table('digital_identity_presentation_policies') as batch_op:
        batch_op.add_column(sa.Column('holder_binding_json', sa.JSON(), nullable=True))

    # Step 2: Migrate existing string values to JSON objects
    conn = op.get_bind()
    rows = conn.execute(
        sa.text('SELECT id, holder_binding FROM digital_identity_presentation_policies')
    ).fetchall()

    import json
    for row in rows:
        row_id, hb = row
        if isinstance(hb, str):
            # Legacy single-enum string → spec-shape object
            if hb == 'NONE':
                hb_dict = {"required": False, "binding_methods": [], "nonce_required": False}
            else:
                hb_dict = {
                    "required": True,
                    "binding_methods": [hb],
                    "nonce_required": hb == "NONCE",
                }
        elif isinstance(hb, dict):
            hb_dict = hb  # Already migrated
        else:
            hb_dict = {"required": False, "binding_methods": ["NONCE"], "nonce_required": False}
        conn.execute(
            sa.text('UPDATE digital_identity_presentation_policies SET holder_binding_json = :val WHERE id = :id'),
            {"val": json.dumps(hb_dict), "id": row_id},
        )

    # Step 3: Drop old column, rename new
    with op.batch_alter_table('digital_identity_presentation_policies') as batch_op:
        batch_op.drop_column('holder_binding')
        batch_op.alter_column('holder_binding_json', new_column_name='holder_binding')


def downgrade() -> None:
    # --- PresentationPolicy: revert holder_binding to String ---
    with op.batch_alter_table('digital_identity_presentation_policies') as batch_op:
        batch_op.add_column(sa.Column('holder_binding_str', sa.String(50), nullable=True))

    import json
    conn = op.get_bind()
    rows = conn.execute(
        sa.text('SELECT id, holder_binding FROM digital_identity_presentation_policies')
    ).fetchall()
    for row in rows:
        row_id, hb = row
        if isinstance(hb, str):
            hb = json.loads(hb)
        if isinstance(hb, dict):
            methods = hb.get("binding_methods", [])
            val = methods[0] if methods else "NONE"
            if not hb.get("required", False):
                val = "NONE"
        else:
            val = "NONCE"
        conn.execute(
            sa.text('UPDATE digital_identity_presentation_policies SET holder_binding_str = :val WHERE id = :id'),
            {"val": val, "id": row_id},
        )

    with op.batch_alter_table('digital_identity_presentation_policies') as batch_op:
        batch_op.drop_column('holder_binding')
        batch_op.alter_column('holder_binding_str', new_column_name='holder_binding')

    # --- ApplicationTemplate: drop status ---
    with op.batch_alter_table('digital_identity_application_templates') as batch_op:
        batch_op.drop_column('status')

    # --- CredentialTemplate: drop vct ---
    with op.batch_alter_table('digital_identity_credential_templates') as batch_op:
        batch_op.drop_column('vct')
