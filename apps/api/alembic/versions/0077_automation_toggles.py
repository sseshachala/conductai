"""add automation toggles to guard_config and security_config

Revision ID: 0077
Revises: 0076
Create Date: 2026-06-10
"""

from alembic import op
import sqlalchemy as sa

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guard_config", sa.Column("automation_security_scan", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("guard_config", sa.Column("automation_workflow_trigger", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("security_config", sa.Column("automation_workflow_on_finding", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("security_config", sa.Column("automation_finding_severity", sa.String(20), nullable=False, server_default="critical"))


def downgrade() -> None:
    op.drop_column("security_config", "automation_finding_severity")
    op.drop_column("security_config", "automation_workflow_on_finding")
    op.drop_column("guard_config", "automation_workflow_trigger")
    op.drop_column("guard_config", "automation_security_scan")
