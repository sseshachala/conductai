"""add yaml_content and submitter_email to playbook_submissions for community submissions

Revision ID: 0034
Revises: 0033
"""
from alembic import op
import sqlalchemy as sa

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("playbook_submissions", sa.Column("yaml_content", sa.Text, nullable=True))
    op.add_column("playbook_submissions", sa.Column("submitter_email", sa.String(255), nullable=True))
    op.add_column("playbook_submissions", sa.Column("submitter_workspace_id", sa.String(255), nullable=True))


def downgrade():
    op.drop_column("playbook_submissions", "yaml_content")
    op.drop_column("playbook_submissions", "submitter_email")
    op.drop_column("playbook_submissions", "submitter_workspace_id")
