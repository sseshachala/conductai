"""add proxy_routed to discovered_agents

Revision ID: 0063
Revises: 0062
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("discovered_agents", sa.Column("proxy_routed", sa.Boolean(), nullable=False, server_default=sa.false()))

def downgrade():
    op.drop_column("discovered_agents", "proxy_routed")
