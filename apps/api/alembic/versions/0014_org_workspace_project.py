"""add organizations and projects tables (closes #191)

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. organizations — top-level billing/SSO unit
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_organizations_slug", "organizations", ["slug"])

    # 2. workspaces → org
    op.add_column("workspaces", sa.Column("org_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_workspaces_org_id",
        "workspaces", "organizations",
        ["org_id"], ["id"],
        ondelete="SET NULL",
    )

    # 3. projects — grouping within a workspace
    op.create_table(
        "projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_foreign_key(
        "fk_projects_workspace_id",
        "projects", "workspaces",
        ["workspace_id"], ["id"],
        ondelete="CASCADE",
    )

    # 4. workflows → project (nullable for now; populated by data migration below)
    op.add_column("workflows", sa.Column("project_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_workflows_project_id",
        "workflows", "projects",
        ["project_id"], ["id"],
        ondelete="SET NULL",
    )

    # 5. Data migration:
    #    a. Create one org per workspace (name = workspace name, slug = workspace id)
    #    b. Link workspace → org
    #    c. Create one default project per workspace
    #    d. Assign all existing workflows to that default project
    op.execute("""
        WITH inserted_orgs AS (
            INSERT INTO organizations (id, name, slug, created_at)
            SELECT gen_random_uuid(), name, id::text, now()
            FROM workspaces
            RETURNING id, slug
        )
        UPDATE workspaces
        SET org_id = inserted_orgs.id
        FROM inserted_orgs
        WHERE workspaces.id::text = inserted_orgs.slug
    """)

    op.execute("""
        WITH inserted_projects AS (
            INSERT INTO projects (id, workspace_id, name, created_at)
            SELECT gen_random_uuid(), id, 'Default', now()
            FROM workspaces
            RETURNING id, workspace_id
        )
        UPDATE workflows
        SET project_id = inserted_projects.id
        FROM inserted_projects
        WHERE workflows.workspace_id = inserted_projects.workspace_id
    """)


def downgrade() -> None:
    op.drop_constraint("fk_workflows_project_id", "workflows", type_="foreignkey")
    op.drop_column("workflows", "project_id")

    op.drop_constraint("fk_projects_workspace_id", "projects", type_="foreignkey")
    op.drop_table("projects")

    op.drop_constraint("fk_workspaces_org_id", "workspaces", type_="foreignkey")
    op.drop_column("workspaces", "org_id")

    op.drop_constraint("uq_organizations_slug", "organizations", type_="unique")
    op.drop_table("organizations")
