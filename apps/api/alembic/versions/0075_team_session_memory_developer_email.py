"""add developer_email to team_session_memory

Revision ID: 0075
Revises: 0074
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "team_session_memory",
        sa.Column("developer_email", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("team_session_memory", "developer_email")
