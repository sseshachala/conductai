"""Backfill guard_audit_events.user_email — replace clerk_user_ids with real emails

Revision ID: 0010
Revises: 0009
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # workspace_users has no email column; users.clerk_id is unpopulated.
    # Email resolution now happens at runtime via get_clerk_user_email().
    # Old events with clerk_user_id stored as user_email are left as-is;
    # the activity UI resolves display labels server-side going forward.
    pass


def downgrade() -> None:
    pass  # not reversible — emails are correct, clerk_ids are not
