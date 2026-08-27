"""Add agent_identity_id to guard_audit_events.

The ORM has declared this column since a83c16f6 as part of the schema
drift cleanup, and PR #1322 started reading it in `_event_to_dict`.
No migration ever added the column to the DB, so serialisation raised
`AttributeError` on prod until hotfix #1338 papered over with getattr.

This adds the column for real (nullable, indexed, FK with ondelete
SET NULL — audit history must survive identity deletion).

Revision ID: 0102
Revises: 0101
Create Date: 2026-08-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guard_audit_events",
        sa.Column(
            "agent_identity_id",
            sa.String(length=36),
            sa.ForeignKey("agent_identities.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_guard_audit_events_agent_identity_id",
        "guard_audit_events",
        ["agent_identity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_guard_audit_events_agent_identity_id", table_name="guard_audit_events")
    op.drop_column("guard_audit_events", "agent_identity_id")
