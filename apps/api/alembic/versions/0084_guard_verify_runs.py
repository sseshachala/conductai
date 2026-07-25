"""Add guard_verify_runs table for Guard Verify v2 adversarial battery results.

Revision ID: 0084
Revises: 0083
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guard_verify_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("grade", sa.String(2), nullable=False),
        sa.Column("results", JSONB(), nullable=False),
        sa.Column("total_tests", sa.Integer(), nullable=False),
        sa.Column("passed_tests", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_guard_verify_runs_workspace_id",
        "guard_verify_runs",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_guard_verify_runs_workspace_id", table_name="guard_verify_runs")
    op.drop_table("guard_verify_runs")
