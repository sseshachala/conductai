"""add persona column to workspace_custom_rules

Revision ID: 0040
Revises: 0039
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0040"
down_revision = "0039_guard_session_intent"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workspace_custom_rules",
        sa.Column(
            "persona",
            sa.String(32),
            nullable=False,
            server_default="agent",
        ),
    )


def downgrade():
    op.drop_column("workspace_custom_rules", "persona")
