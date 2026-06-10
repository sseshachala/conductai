"""add blast_radius to guard_audit_events

Revision ID: 0078
Revises: 0077
Create Date: 2026-06-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guard_audit_events",
        sa.Column("blast_radius", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("guard_audit_events", "blast_radius")
