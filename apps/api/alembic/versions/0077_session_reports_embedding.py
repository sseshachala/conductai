"""add embedding column to session_reports

Revision ID: 0077
Revises: 0076
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE session_reports ADD COLUMN IF NOT EXISTS embedding vector(1536)")


def downgrade() -> None:
    op.execute("ALTER TABLE session_reports DROP COLUMN IF EXISTS embedding")
