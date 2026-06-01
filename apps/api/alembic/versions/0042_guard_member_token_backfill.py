"""backfill null member_token for guard_members

Revision ID: 0042
Revises: 0041
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa

revision = '0042'
down_revision = '0041'
branch_labels = None
depends_on = None

def upgrade():
    op.execute("""
        UPDATE guard_members
        SET member_token = encode(gen_random_bytes(18), 'base64')
        WHERE member_token IS NULL OR member_token = ''
    """)

def downgrade():
    pass
