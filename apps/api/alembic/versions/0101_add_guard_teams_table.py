"""add guard_teams compatibility table

Revision ID: 0101_add_guard_teams_table
Revises: 0100_drop_glens_render_spec_orphan
Create Date: 2026-08-27 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "0101_add_guard_teams_table"
down_revision = "0100_drop_glens_render_spec_orphan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guard_teams",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", name="uq_guard_teams_workspace_id"),
    )


def downgrade() -> None:
    op.drop_table("guard_teams")
