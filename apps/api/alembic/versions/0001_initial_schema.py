"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-29
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    op.create_table(
        "workspaces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("plan", sa.String(50), nullable=False, server_default="free"),
        sa.Column("kms_key_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Seed a dev workspace so Phase 1 works without auth
    op.execute(
        "INSERT INTO workspaces (id, name, plan) VALUES "
        "('00000000-0000-0000-0000-000000000001', 'dev-workspace', 'free')"
    )

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="editor"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "workflow_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workflow_id", UUID(as_uuid=True), nullable=False),  # FK added after workflows table
        sa.Column("graph", JSONB, nullable=False, server_default="{}"),
        sa.Column("compiled_artifacts", JSONB, nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "workflows",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("current_version_id", UUID(as_uuid=True), sa.ForeignKey("workflow_versions.id"), nullable=True),
        sa.Column("default_mode", sa.String(50), nullable=False, server_default="dag"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_foreign_key(
        "fk_workflow_versions_workflow_id",
        "workflow_versions", "workflows",
        ["workflow_id"], ["id"],
    )

    op.create_table(
        "integrations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("service", sa.String(100), nullable=False),
        sa.Column("auth_method", sa.String(50), nullable=False),
        sa.Column("handle", sa.String(100), nullable=False),
        sa.Column("scopes", ARRAY(sa.String), nullable=True),
        sa.Column("encrypted_credentials", sa.Text, nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "handle", name="uq_integrations_workspace_handle"),
    )

    op.create_table(
        "runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workflow_version_id", UUID(as_uuid=True), sa.ForeignKey("workflow_versions.id"), nullable=False),
        sa.Column("triggered_by", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_block_id", sa.String(255), nullable=True),
        sa.Column("state", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "run_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("block_id", sa.String(255), nullable=True),
        sa.Column("kind", sa.String(100), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Indexes for common queries
    op.create_index("ix_runs_workflow_version_id", "runs", ["workflow_version_id"])
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])
    op.create_index("ix_workflows_workspace_id", "workflows", ["workspace_id"])


def downgrade() -> None:
    op.drop_table("run_events")
    op.drop_table("runs")
    op.drop_table("integrations")
    op.drop_constraint("fk_workflow_versions_workflow_id", "workflow_versions", type_="foreignkey")
    op.drop_table("workflows")
    op.drop_table("workflow_versions")
    op.drop_table("users")
    op.drop_table("workspaces")
