"""add token_type to agent_identities

Revision ID: 0068
Revises: 0067
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("agent_identities", sa.Column("token_type", sa.String(10), nullable=False, server_default="cli"))
    op.add_column("agent_identities", sa.Column("token_name", sa.Text, nullable=True))
    # IMPORTANT: rows with token_type='api' intentionally have no guard_member_config FK.
    # Any cleanup deleting orphan agent_identities MUST filter WHERE token_type = 'cli'.

def downgrade():
    op.drop_column("agent_identities", "token_name")
    op.drop_column("agent_identities", "token_type")
