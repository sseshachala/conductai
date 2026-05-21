"""full isolation: migrate credentials to Default environment, make environment_id NOT NULL

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-21
"""
from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KNOWN_WORKFLOW_ID = "3638c5eb-ccb9-41da-aecf-b8bd6322e23c"


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Find all distinct workspace_ids that have integrations (global or not)
    workspace_rows = conn.execute(
        sa.text("SELECT DISTINCT workspace_id FROM integrations")
    ).fetchall()

    # Also include workspaces that have credentials but no integrations yet
    all_workspace_rows = conn.execute(
        sa.text("SELECT DISTINCT workspace_id FROM workspaces")
    ).fetchall()

    # Union both sets
    all_workspace_ids = {str(r[0]) for r in workspace_rows} | {str(r[0]) for r in all_workspace_rows}

    # 2. For each workspace, create a "Default" environment (skip if already exists)
    workspace_to_default_env: dict[str, str] = {}
    for ws_id in all_workspace_ids:
        existing = conn.execute(
            sa.text(
                "SELECT id FROM environments WHERE workspace_id = :ws AND name = 'Default'"
            ),
            {"ws": ws_id},
        ).fetchone()

        if existing:
            workspace_to_default_env[ws_id] = str(existing[0])
        else:
            env_id = str(uuid.uuid4())
            conn.execute(
                sa.text(
                    "INSERT INTO environments (id, workspace_id, name, created_at) "
                    "VALUES (:id, :ws, 'Default', now())"
                ),
                {"id": env_id, "ws": ws_id},
            )
            workspace_to_default_env[ws_id] = env_id

    # 3. Migrate all global credentials (environment_id IS NULL) to their workspace's Default env
    for ws_id, env_id in workspace_to_default_env.items():
        conn.execute(
            sa.text(
                "UPDATE integrations SET environment_id = :env_id "
                "WHERE workspace_id = :ws AND environment_id IS NULL"
            ),
            {"env_id": env_id, "ws": ws_id},
        )

    # 4. Make environment_id NOT NULL on integrations (all rows now have a value)
    op.alter_column("integrations", "environment_id", nullable=False)

    # 5. Assign the known working workflow to its workspace's Default environment
    wf_row = conn.execute(
        sa.text("SELECT workspace_id FROM workflows WHERE id = :wid"),
        {"wid": KNOWN_WORKFLOW_ID},
    ).fetchone()

    if wf_row:
        ws_id = str(wf_row[0])
        default_env_id = workspace_to_default_env.get(ws_id)
        if default_env_id:
            conn.execute(
                sa.text(
                    "UPDATE workflows SET environment_id = :env_id WHERE id = :wid"
                ),
                {"env_id": default_env_id, "wid": KNOWN_WORKFLOW_ID},
            )


def downgrade() -> None:
    # Make environment_id nullable again
    op.alter_column("integrations", "environment_id", nullable=True)

    # Restore global credentials (set environment_id back to NULL for Default-env credentials)
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE integrations SET environment_id = NULL "
            "WHERE environment_id IN (SELECT id FROM environments WHERE name = 'Default')"
        )
    )

    # Clear the known workflow's environment assignment
    conn.execute(
        sa.text("UPDATE workflows SET environment_id = NULL WHERE id = :wid"),
        {"wid": KNOWN_WORKFLOW_ID},
    )
