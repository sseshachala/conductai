"""add yaml_source to workflow_versions and source repo fields to workflows

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The YAML text — canonical source for a workflow definition. The existing
    # `graph` JSONB column becomes a derived cache produced by the loader.
    op.add_column(
        "workflow_versions",
        sa.Column("yaml_source", sa.Text, nullable=True),
    )

    # Optional link to a YAML file in a customer's GitHub repo. The presence
    # of source_repo + source_path means the runtime should re-fetch the YAML
    # at run time (phase 2 — sync layer); for now it's metadata only.
    op.add_column(
        "workflows",
        sa.Column("source_repo", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "workflows",
        sa.Column("source_path", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workflows", "source_path")
    op.drop_column("workflows", "source_repo")
    op.drop_column("workflow_versions", "yaml_source")
