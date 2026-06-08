"""add project_type and security_finding_id to projects

Revision ID: 0070
Revises: 0069
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("projects", sa.Column(
        "project_type", sa.String(32), nullable=False, server_default="user"
    ))
    op.add_column("projects", sa.Column(
        "security_finding_id", sa.String(36), nullable=True
    ))
    op.create_index("ix_projects_project_type", "projects", ["project_type"])
    op.create_index("ix_projects_security_finding_id", "projects", ["security_finding_id"])


def downgrade():
    op.drop_index("ix_projects_security_finding_id", table_name="projects")
    op.drop_index("ix_projects_project_type", table_name="projects")
    op.drop_column("projects", "security_finding_id")
    op.drop_column("projects", "project_type")
