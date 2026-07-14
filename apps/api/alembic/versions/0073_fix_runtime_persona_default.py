"""fix: runtime_persona default — update stale 'conservative' rows to 'agent'

Revision ID: 0073
Revises: 0072
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade():
    # Fix stale rows from migration 0025 that used the old 'conservative' persona
    op.execute("""
        UPDATE guard_config
        SET runtime_persona = 'agent'
        WHERE runtime_persona NOT IN ('agent', 'proxy')
    """)
    # Update column default
    op.alter_column(
        "guard_config",
        "runtime_persona",
        server_default="agent",
        existing_type=sa.String(20),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "guard_config",
        "runtime_persona",
        server_default="conservative",
        existing_type=sa.String(20),
        existing_nullable=False,
    )
