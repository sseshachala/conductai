"""allow same integration handle per environment (workspace+handle+env unique)

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-24
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old (workspace_id, handle) constraint that prevented the same
    # handle (e.g. "github") from existing in more than one environment.
    op.drop_constraint("uq_integrations_workspace_handle", "integrations", type_="unique")

    # New constraint: unique per (workspace, handle, environment).
    # NULLS are treated as distinct by Postgres, so two rows with the same
    # workspace+handle but environment_id=NULL would both be allowed — that
    # edge case doesn't arise in practice because we always resolve an env.
    op.create_unique_constraint(
        "uq_integrations_workspace_handle_env",
        "integrations",
        ["workspace_id", "handle", "environment_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_integrations_workspace_handle_env", "integrations", type_="unique")
    op.create_unique_constraint(
        "uq_integrations_workspace_handle",
        "integrations",
        ["workspace_id", "handle"],
    )
