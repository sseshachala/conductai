"""add audit_log table for enterprise trust and compliance

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-26

Records every state-changing action: credential add/remove, member invite/remove,
workflow create/delete, run triggered. Admin-only queryable. No PII in metadata.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.String(255), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=True),
        sa.Column("actor_email", sa.String(255), nullable=True),
        sa.Column("actor_role", sa.String(50), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("metadata", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_log_workspace_created", "audit_log", ["workspace_id", "created_at"])
    op.create_index("ix_audit_log_workspace_action", "audit_log", ["workspace_id", "action"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_workspace_action", table_name="audit_log")
    op.drop_index("ix_audit_log_workspace_created", table_name="audit_log")
    op.drop_table("audit_log")
