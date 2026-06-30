"""add environment_id to agent_identities

Revision ID: 0042
Revises: 0041
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_identities", sa.Column("environment_id", sa.String(36), nullable=True))


def downgrade():
    op.drop_column("agent_identities", "environment_id")
