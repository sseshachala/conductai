"""Add CHECK constraint on guard_audit_events.lifecycle_state.

Post-review follow-up to #1959 Phase 1's schema. The writer already
uses a fixed vocabulary of lifecycle values ('accepted' | 'finalized' |
'orphaned' | 'expired'), but the column was declared as a plain
nullable VARCHAR(20) so nothing at the DB level prevented drift into
an unknown value. This migration adds the CHECK constraint the ORM
comment already claimed.

NULL is allowed because legacy single-phase rows (guard_use_durable_audit=false)
and every pre-Phase-1 row have no lifecycle. The constraint only
enforces the allowed values when the column is populated.

Revision ID: 0134
Revises: 0133
"""
from alembic import op


revision = "0134"
down_revision = "0133"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE guard_audit_events
        ADD CONSTRAINT ck_guard_audit_events_lifecycle_state
        CHECK (
            lifecycle_state IS NULL OR
            lifecycle_state IN ('accepted', 'finalized', 'orphaned', 'expired')
        )
    """)


def downgrade():
    op.execute(
        "ALTER TABLE guard_audit_events "
        "DROP CONSTRAINT IF EXISTS ck_guard_audit_events_lifecycle_state"
    )
