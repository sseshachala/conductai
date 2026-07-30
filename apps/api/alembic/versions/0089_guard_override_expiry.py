"""Require explicit expiry metadata for Guard policy exceptions.

Existing overrides that may weaken policy receive a seven-day review grace
period. This is deliberately conservative: action overrides cannot be
reliably classified against every historical pack version in SQL, so all
existing action overrides receive exception metadata. Equal or stronger
actions continue to apply after the date because application code does not
treat them as exceptions. Message-only and match-pattern customizations remain
indefinite. The policy cache is cleared so the grace deadline takes effect.

Revision ID: 0089
Revises: 0088
Create Date: 2026-07-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guard_rule_overrides", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column(
        "guard_rule_overrides",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "guard_rule_overrides",
        sa.Column("use_audited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "guard_rule_overrides",
        sa.Column("expiry_audited_at", sa.DateTime(timezone=True), nullable=True),
    )

    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE guard_rule_overrides
           SET reason = COALESCE(reason, 'Legacy override migrated by 0089; review before grace period ends'),
               expires_at = CURRENT_TIMESTAMP + INTERVAL '7 days',
               overridden_by = COALESCE(overridden_by, 'system:legacy-migration')
         WHERE disabled IS TRUE
            OR action IS NOT NULL
    """))
    conn.execute(sa.text("DELETE FROM guard_policy_cache"))


def downgrade() -> None:
    op.drop_column("guard_rule_overrides", "expiry_audited_at")
    op.drop_column("guard_rule_overrides", "use_audited_at")
    op.drop_column("guard_rule_overrides", "expires_at")
    op.drop_column("guard_rule_overrides", "reason")
