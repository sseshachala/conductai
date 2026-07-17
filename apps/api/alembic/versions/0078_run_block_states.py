"""add run_block_states table for atomic checkpoint per block

Revision ID: 0078
Revises: 0077
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE run_block_states (
            run_id           UUID         NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            block_id         VARCHAR(255) NOT NULL,
            attempt_id       UUID         NOT NULL,
            output           JSONB        NOT NULL DEFAULT '{}',
            partial          BOOLEAN      NOT NULL DEFAULT FALSE,
            resume_from_turn INTEGER      NOT NULL DEFAULT 0,
            completed_at     TIMESTAMPTZ,
            created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
            PRIMARY KEY (run_id, block_id)
        )
    """)
    op.execute("CREATE INDEX ix_run_block_states_run_id ON run_block_states (run_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS run_block_states")
