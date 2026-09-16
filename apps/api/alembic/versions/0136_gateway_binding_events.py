"""Gateway Profile v2 — binding-event audit trail.

#2001 review fix. Rollback previously mutated a binding row in place
without recording actor / from / to, and publish did the same.
Adds one append-only table capturing every binding change so history
is reliably preserved regardless of what happens to the binding row.

    gateway_profile_binding_events(
        id, workspace_id, environment_id, model_alias,
        prior_revision_id, new_revision_id,
        actor, action, occurred_at
    )

``action`` is 'publish' | 'rollback'. ``prior_revision_id`` is NULL for
the first publish. Nothing UPDATEs or DELETEs from this table.

Revision ID: 0136
Revises: 0135
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0136"
down_revision = "0135"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gateway_profile_binding_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "environment_id",
            UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_alias", sa.String(length=128), nullable=False),
        # First publish has prior=NULL. Every subsequent event names a prior.
        sa.Column(
            "prior_revision_id",
            UUID(as_uuid=True),
            sa.ForeignKey("gateway_profile_revisions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "new_revision_id",
            UUID(as_uuid=True),
            sa.ForeignKey("gateway_profile_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("actor", sa.String(length=256), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "action IN ('publish','rollback')",
            name="ck_gateway_profile_binding_events_action",
        ),
    )
    op.create_index(
        "ix_gateway_profile_binding_events_lookup",
        "gateway_profile_binding_events",
        ["workspace_id", "environment_id", "model_alias", "occurred_at"],
    )


def downgrade():
    op.drop_index(
        "ix_gateway_profile_binding_events_lookup",
        table_name="gateway_profile_binding_events",
    )
    op.drop_table("gateway_profile_binding_events")
