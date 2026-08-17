"""Add evaluated_rules (JSONB) + defense_score to guard_audit_events

Phase 1 of the layered verdict envelope (#1150). Persists the full set of
rules that fired on a given decision, not just the winning rule. Existing
`rule_id` column continues to hold the primary/winning rule.

Both columns are nullable so historical rows and non-eval audit paths
(auth, approval, guard block) stay as-is.

GIN index enables analytics queries like
  WHERE jsonb_array_length(evaluated_rules) >= 2

Revision ID: 0094
Revises: 0093
Create Date: 2026-08-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guard_audit_events",
        sa.Column("evaluated_rules", JSONB, nullable=True),
    )
    op.add_column(
        "guard_audit_events",
        sa.Column("defense_score", sa.Integer, nullable=True),
    )
    op.create_index(
        "ix_guard_audit_events_evaluated_rules_gin",
        "guard_audit_events",
        ["evaluated_rules"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_guard_audit_events_evaluated_rules_gin",
        table_name="guard_audit_events",
    )
    op.drop_column("guard_audit_events", "defense_score")
    op.drop_column("guard_audit_events", "evaluated_rules")
