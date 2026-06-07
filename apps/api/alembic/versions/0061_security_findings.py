"""feat: create security_findings table for Security Loop

Revision ID: 0061
Revises: 0060
Create Date: 2026-06-07
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_findings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("file", sa.String(), nullable=True),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("suggested_fix", sa.Text(), nullable=True),
        sa.Column("repo_full_name", sa.String(), nullable=True),
        sa.Column("commit_sha", sa.String(), nullable=True),
        sa.Column("source_run_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("github_issue_url", sa.String(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_index("ix_security_findings_workspace_id", "security_findings", ["workspace_id"])
    op.create_index("ix_security_findings_repo_full_name", "security_findings", ["repo_full_name"])
    op.create_index("ix_security_findings_created_at", "security_findings", ["created_at"])
    op.create_index("ix_security_findings_status", "security_findings", ["workspace_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_security_findings_status", table_name="security_findings")
    op.drop_index("ix_security_findings_created_at", table_name="security_findings")
    op.drop_index("ix_security_findings_repo_full_name", table_name="security_findings")
    op.drop_index("ix_security_findings_workspace_id", table_name="security_findings")
    op.drop_table("security_findings")
