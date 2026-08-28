"""Phase 3c schema drift reconciliation — JSON→JSONB + users.workspace_id NOT NULL

Revision ID: 0105
Revises: 0104
Create Date: 2026-08-27

Two functional fixes:

1. agent_identities.metadata_json JSON → JSONB
   The model has always declared JSONB. DB has JSON (since original
   migration). JSON columns can't be indexed with GIN and don't support
   the `->>` / `@>` operators used by JSONB queries. Any code path
   assuming JSONB behavior on this column silently misbehaves today.
   Uses `USING metadata_json::jsonb` cast — JSON literals are valid JSONB
   input, so the conversion is lossless. Rewrites the column in place.

2. users.workspace_id NOT NULL
   DB currently allows NULL; model declares nullable=False; verified via
   `SELECT COUNT(*) FROM users WHERE workspace_id IS NULL` returns 0 rows
   before this migration ships. Adds a pre-check that raises if any NULL
   rows appear at deploy time (defensive: catches new nulls introduced
   between draft and deploy).
"""
from alembic import op
import sqlalchemy as sa

revision = "0105"
down_revision = "0104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. agent_identities.metadata_json → JSONB ──
    op.execute(
        "ALTER TABLE agent_identities "
        "ALTER COLUMN metadata_json TYPE jsonb "
        "USING metadata_json::jsonb"
    )

    # ── 2. users.workspace_id NOT NULL ──
    # Defensive check: refuse to run if any NULLs sneaked in since draft.
    conn = op.get_bind()
    null_count = conn.execute(
        sa.text("SELECT COUNT(*) FROM users WHERE workspace_id IS NULL")
    ).scalar()
    if null_count:
        raise RuntimeError(
            f"Refusing to enforce NOT NULL on users.workspace_id: "
            f"{null_count} row(s) currently have NULL. Backfill first."
        )
    op.alter_column("users", "workspace_id", nullable=False)


def downgrade() -> None:
    op.alter_column("users", "workspace_id", nullable=True)
    op.execute(
        "ALTER TABLE agent_identities "
        "ALTER COLUMN metadata_json TYPE json "
        "USING metadata_json::json"
    )
