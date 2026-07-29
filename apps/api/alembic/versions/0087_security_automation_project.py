"""feat(security): Security Automation project as authoritative dispatch target

Schema half of the epic (see conductai#1005). Four changes, all additive:

1. ``projects`` — partial unique index enforcing at most one ``security_automation``
   project per workspace. Reuses the existing ``project_type`` column (values
   ``user``/``security_automation``/``security_incident``) instead of adding
   a redundant ``kind`` column, since ``project_type == 'security_automation'``
   is already the value queried by ``app/worker.py:180,204``.

2. ``workspaces`` — ``security_automation_project_id`` FK (nullable, ON DELETE
   SET NULL). This is the authoritative pointer: dispatchers look up the
   security_loop / security_autopilot_fix workflow via this project, killing
   ``.first()`` roulette (conductai#998).

3. ``workflows`` — partial unique index on ``(project_id, playbook_slug)`` so
   the DB itself guarantees at most one workflow-per-slug-per-project. Once
   auto-provision lands, the dispatchers can safely ``.first()`` because
   uniqueness is enforced by the schema.

4. ``security_findings`` — ``source_project_id`` FK (nullable, ON DELETE SET
   NULL) for lineage. Fix routing still uses ``repo_full_name``; this column
   answers "which scanner project produced this finding" without a 2-hop JOIN
   later when Guard Activity renders Source · Owner · Target.

All partial indexes use ``CONCURRENTLY`` — safe on live tables. Column adds
are all nullable with no default, so no table rewrite.

Revision ID: 0087
Revises: 0086
Create Date: 2026-07-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 2. workspaces.security_automation_project_id — the authoritative pointer.
    op.add_column(
        "workspaces",
        sa.Column(
            "security_automation_project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 4. security_findings.source_project_id — lineage back to scanner project.
    op.add_column(
        "security_findings",
        sa.Column(
            "source_project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # CONCURRENTLY requires we exit the migration transaction first.
    op.execute("COMMIT")

    # 1. At most one security_automation project per workspace.
    op.execute(
        "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
        "projects_workspace_security_automation_uniq "
        "ON projects (workspace_id) "
        "WHERE project_type = 'security_automation'"
    )

    # 3. At most one workflow-per-slug-per-project (once installed under a project).
    op.execute(
        "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "
        "workflows_project_playbook_uniq "
        "ON workflows (project_id, playbook_slug) "
        "WHERE project_id IS NOT NULL AND playbook_slug IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("COMMIT")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS workflows_project_playbook_uniq")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS projects_workspace_security_automation_uniq")
    op.drop_column("security_findings", "source_project_id")
    op.drop_column("workspaces", "security_automation_project_id")
