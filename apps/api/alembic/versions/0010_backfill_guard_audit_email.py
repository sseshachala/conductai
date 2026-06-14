"""Backfill guard_audit_events.user_email — replace clerk_user_ids with real emails

Revision ID: 0010
Revises: 0009
"""
from alembic import op


def upgrade() -> None:
    op.execute("""
        UPDATE guard_audit_events e
        SET user_email = u.email
        FROM users u
        WHERE u.clerk_id = e.user_email
          AND e.user_email LIKE 'user_%'
    """)


def downgrade() -> None:
    pass  # not reversible — emails are correct, clerk_ids are not
