"""feat(#1347 PR B.6): add routing_meta jsonb to guard_audit_events

Persists the tier-form resolution (before/after model + reason) into the
audit trail so operators can prove which primitives decision drove each
LLM call. NULL when the caller sent a concrete model ID.

Revision ID: 0104
Revises: 0103
Create Date: 2026-08-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0104"
down_revision = "0103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guard_audit_events",
        sa.Column("routing_meta", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("guard_audit_events", "routing_meta")
