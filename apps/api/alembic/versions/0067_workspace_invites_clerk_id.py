"""workspace_invites: add clerk_invitation_id for Clerk org invite tracking

Revision ID: 0067
Revises: 0066
"""
from alembic import op
import sqlalchemy as sa

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workspace_invites", sa.Column("clerk_invitation_id", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("workspace_invites", "clerk_invitation_id")
