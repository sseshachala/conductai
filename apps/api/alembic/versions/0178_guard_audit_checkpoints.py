"""guard_audit_checkpoints + guard_audit_signing_keys: signed chain-head checkpoints (#2524 item 2).

Checkpoints are per-workspace (RLS, same policy as guard_audit_archive_segments).
Signing keys are public material and are retained forever for rotation, so that
table has no RLS and the well-known endpoint can read it unauthenticated.

NOTE: other branches add migrations 0174-0177 in parallel; renumber/rebase
down_revision if 0173 is no longer the head on main.

Revision ID: 0178
Revises: 0173
Create Date: 2026-11-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0178"
down_revision = "0173"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guard_audit_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("head_entry_hash", sa.String(length=64), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("hash_version", sa.Integer(), nullable=False),
        sa.Column("key_id", sa.String(length=64), nullable=False),
        sa.Column("alg", sa.String(length=32), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"],
                                name="fk_guard_audit_checkpoints_workspace_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_guard_audit_checkpoints"),
        sa.UniqueConstraint("workspace_id", "head_entry_hash", "row_count",
                            name="uq_guard_audit_checkpoints_head"),
        sa.CheckConstraint("row_count > 0", name="ck_guard_audit_checkpoints_row_count"),
    )
    op.create_index("ix_guard_audit_checkpoints_ws_ts", "guard_audit_checkpoints", ["workspace_id", "ts"])
    op.execute("ALTER TABLE guard_audit_checkpoints ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE guard_audit_checkpoints FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY guard_audit_checkpoints_workspace ON guard_audit_checkpoints "
        "USING (workspace_id = NULLIF(current_setting('app.current_workspace', true), '')::uuid) "
        "WITH CHECK (workspace_id = NULLIF(current_setting('app.current_workspace', true), '')::uuid)"
    )

    op.create_table(
        "guard_audit_signing_keys",
        sa.Column("key_id", sa.String(length=64), nullable=False),
        sa.Column("alg", sa.String(length=32), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("backend", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key_id", name="pk_guard_audit_signing_keys"),
    )


def downgrade() -> None:
    op.drop_table("guard_audit_signing_keys")
    op.drop_index("ix_guard_audit_checkpoints_ws_ts", table_name="guard_audit_checkpoints")
    op.drop_table("guard_audit_checkpoints")
