"""add session_reports table

Revision ID: 0079
Revises: 0078
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("clerk_user_id", sa.Text, nullable=True),
        sa.Column("developer_email", sa.String(255), nullable=False),
        sa.Column("archetype", sa.String(100), nullable=True),
        sa.Column("autonomy_score", sa.Float, nullable=True),
        sa.Column("planning_ratio", sa.Float, nullable=True),
        sa.Column("sessions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("prompts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("commits", sa.Integer, nullable=False, server_default="0"),
        sa.Column("lines_per_hour", sa.Float, nullable=True),
        sa.Column("active_days", sa.Integer, nullable=True),
        sa.Column("tools_json", postgresql.JSONB, nullable=True),
        sa.Column("report_md", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_session_reports_workspace", "session_reports", ["workspace_id"])
    op.create_index("ix_session_reports_email", "session_reports", ["developer_email"])


def downgrade() -> None:
    op.drop_index("ix_session_reports_email")
    op.drop_index("ix_session_reports_workspace")
    op.drop_table("session_reports")
