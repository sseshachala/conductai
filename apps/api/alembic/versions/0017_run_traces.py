"""add run_traces table for full AI conversation replay

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-26

One row per turn per role inside an agentic brain block.
Enables full conversation replay, prompt debugging, and audit log.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_traces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("block_id", sa.String(255), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.String(255), nullable=True),
        sa.Column("tool_input", JSONB(), nullable=True),
        sa.Column("tool_use_id", sa.String(255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_run_traces_run_id", "run_traces", ["run_id"])
    op.create_index("ix_run_traces_run_id_block_turn", "run_traces", ["run_id", "block_id", "turn"])


def downgrade() -> None:
    op.drop_index("ix_run_traces_run_id_block_turn", table_name="run_traces")
    op.drop_index("ix_run_traces_run_id", table_name="run_traces")
    op.drop_table("run_traces")
