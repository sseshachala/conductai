"""add playbook_slug to workflows and preferences to workspaces

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workflows", sa.Column("playbook_slug", sa.String(100), nullable=True))
    op.add_column("workspaces", sa.Column("preferences", JSONB, nullable=True))


def downgrade():
    op.drop_column("workflows", "playbook_slug")
    op.drop_column("workspaces", "preferences")
