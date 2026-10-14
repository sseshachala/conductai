"""Gateway profiles: soft delete (deleted_at) + live-only unique name

Lifecycle change: unpublished profiles are soft-deleted so their immutable
revisions survive. The (workspace_id, environment_id, name) unique
constraint becomes a partial unique index over live rows so a name can be
reused after soft delete.

Revision ID: 0169
Revises: 0168
Create Date: 2026-10-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0169"
down_revision = "0168"
branch_labels = None
depends_on = None

_OLD = "uq_gateway_profiles_workspace_env_name"
_NEW = "uq_gateway_profiles_workspace_env_name_live"


def upgrade() -> None:
    op.add_column(
        "gateway_profiles",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint(_OLD, "gateway_profiles", type_="unique")
    op.create_index(
        _NEW,
        "gateway_profiles",
        ["workspace_id", "environment_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    # Soft-deleted rows may share a name with a live row; the full unique
    # constraint cannot be restored until they are gone. Hard-delete them
    # (revisions + rate limits cascade via their FKs). Rows are unpublished
    # by construction (publish-state is a precondition of soft delete).
    op.execute("DELETE FROM gateway_profiles WHERE deleted_at IS NOT NULL")
    op.drop_index(_NEW, table_name="gateway_profiles")
    op.create_unique_constraint(
        _OLD, "gateway_profiles", ["workspace_id", "environment_id", "name"],
    )
    op.drop_column("gateway_profiles", "deleted_at")
