"""add agent_role_id to runs

Revision ID: 0043
Revises: 0042
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("runs", sa.Column("agent_role_id", sa.String(36), nullable=True))


def downgrade():
    op.drop_column("runs", "agent_role_id")
