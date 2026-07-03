"""unique constraint on discovered_agents (workspace_id, framework, source)

Revision ID: 0051
Revises: 0050
Create Date: 2026-07-03
"""
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade():
    # Remove duplicate rows first, keeping the most recently seen one per key
    op.execute("""
        DELETE FROM discovered_agents a
        USING discovered_agents b
        WHERE a.id < b.id
          AND a.workspace_id = b.workspace_id
          AND a.framework    = b.framework
          AND a.source       = b.source
    """)
    op.create_unique_constraint(
        "uq_discovered_agents_workspace_framework_source",
        "discovered_agents",
        ["workspace_id", "framework", "source"],
    )


def downgrade():
    op.drop_constraint(
        "uq_discovered_agents_workspace_framework_source",
        "discovered_agents",
        type_="unique",
    )
