"""add workspace_invites table for email-based member invitations

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-23
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invited_email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="editor"),
        sa.Column("invited_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workspace_id", "invited_email", name="uq_workspace_invite_email"),
    )
    op.create_index("ix_workspace_invites_email", "workspace_invites", ["invited_email"])


def downgrade() -> None:
    op.drop_table("workspace_invites")
