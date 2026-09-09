"""Backfill workspace_users with admin membership for legacy owner_id.

Legacy workspaces created before workspace_users was the source of truth
have `workspaces.owner_id` set but no matching `workspace_users` row. This
made /me/permissions resolve them as 'viewer' and hid the guard.*.view_all
permissions — the "You can view your own activity only" banner showed for
actual admins. Every production create-path now inserts the row; this
migration heals existing data. Idempotent via NOT EXISTS.

Revision ID: 0117
Revises: 0116
Create Date: 2026-09-07

Numbered 0117 (not 0116) to sit downstream of PR #1715's
0116_behavior_arg_baselines — that PR was in review when this backfill
was written, and we don't want the first outside contributor to rebase
on our unmerged branch.
"""
from __future__ import annotations

from alembic import op


revision = "0117"
down_revision = "0116"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO workspace_users (workspace_id, clerk_user_id, role, joined_at)
        SELECT w.id, w.owner_id, 'admin', COALESCE(w.created_at, NOW())
        FROM workspaces w
        WHERE w.owner_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM workspace_users wu
              WHERE wu.workspace_id = w.id
                AND wu.clerk_user_id = w.owner_id
          )
        """
    )


def downgrade() -> None:
    # ponytail: no-op — we can't tell backfilled rows from real ones, and
    # removing admin membership is destructive.
    pass
