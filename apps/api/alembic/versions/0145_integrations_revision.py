"""integrations.revision — optimistic concurrency for env-var writes

Adds a ``revision`` column to ``integrations``. Every write to
``env-vars`` (save_env_vars, delete_env_var) reads the caller's
``expected_revision`` and bumps this column atomically. Concurrent
writers whose expected value doesn't match get a 409 with the current
revision so the client can reload + diff before retrying.

See also: #2054 (Vault epic — canonical storage, safe write path).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0145"
down_revision = "0144"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NOT NULL with server-side default so existing rows land at 1 without
    # a backfill query. New inserts default to 1; the writer bumps on every
    # update.
    op.add_column(
        "integrations",
        sa.Column(
            "revision",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )


def downgrade() -> None:
    op.drop_column("integrations", "revision")
