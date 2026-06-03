"""guard: add guard_savings table for per-developer RTK + Agent Booster savings tracking

Revision ID: 0055
Revises: 0054
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS guard_savings (
            id              SERIAL PRIMARY KEY,
            workspace_id    TEXT NOT NULL,
            member_email    TEXT NOT NULL,
            rtk_saved_tokens    BIGINT NOT NULL DEFAULT 0,
            rtk_savings_pct     DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            rtk_total_commands  INTEGER NOT NULL DEFAULT 0,
            booster_saved_tokens BIGINT NOT NULL DEFAULT 0,
            booster_savings_pct  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            booster_total_reads  INTEGER NOT NULL DEFAULT 0,
            period_start    TIMESTAMPTZ,
            period_end      TIMESTAMPTZ NOT NULL,
            recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_guard_savings_workspace_id
        ON guard_savings (workspace_id)
    """)


def downgrade():
    op.execute("ALTER TABLE IF EXISTS guard_savings RENAME TO guard_savings_removed_0055")
