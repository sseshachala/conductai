"""Guard audit events: token usage provenance (usage_source, usage_status)

#2069. Records where tokens_before/tokens_after came from and how complete
they are, so Flight Recorder can tell provider-reported counts, prompt
estimates, known zeros and unavailable usage apart. Both columns are
nullable: NULL = legacy row written before provenance existed. No backfill;
legacy counts are never relabelled as provider-reported.

Revision ID: 0171
Revises: 0170
Create Date: 2026-10-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0171"
down_revision = "0170"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guard_audit_events", sa.Column("usage_source", sa.String(20), nullable=True))
    op.add_column("guard_audit_events", sa.Column("usage_status", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("guard_audit_events", "usage_status")
    op.drop_column("guard_audit_events", "usage_source")
