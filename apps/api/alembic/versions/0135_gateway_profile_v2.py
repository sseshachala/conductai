"""Gateway Profile v2 tables — working_copy + immutable revisions + bindings.

#2001 delivery step 1 of 4.

Three shape changes on top of the existing ``gateway_profiles`` table:

1. Add ``working_copy jsonb`` to ``gateway_profiles``. Save writes here
   only; editing never touches served traffic. Existing ``config``
   stays put so the legacy resolver keeps working while the
   ``guard_gateway_profile_v2`` flag is off.
2. New ``gateway_profile_revisions`` — immutable snapshots. Every
   publish inserts one row here; nothing ever updates it.
3. New ``gateway_profile_bindings`` — the explicit selection table.
   One row per ``(workspace_id, environment_id, model_alias)``. The v2
   resolver reads this and pins the revision through every attempt of
   the request.

Nothing about v1 is dropped. A workspace stays on v1 until an admin
publishes at least one v2 profile through the new endpoints.

Revision ID: 0135
Revises: 0134
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "0135"
down_revision = "0134"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Working copy on the mutable profiles table.
    #    Nullable — legacy v1 rows will have config populated + working_copy
    #    NULL, and the v2 endpoints only touch working_copy.
    op.add_column(
        "gateway_profiles",
        sa.Column("working_copy", JSONB, nullable=True),
    )
    # A v2 profile carries its ``model_alias`` at the row level so the
    # bindings table can key on (workspace, environment, model_alias)
    # without cracking JSON on every request. Nullable during rollout;
    # v2 publish path enforces it.
    op.add_column(
        "gateway_profiles",
        sa.Column("model_alias", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_gateway_profiles_model_alias",
        "gateway_profiles",
        ["workspace_id", "environment_id", "model_alias"],
        unique=False,
    )

    # 2. Immutable revisions — one row per publish. No UPDATE, no DELETE
    #    from application code; rollback is a NEW row that points at an
    #    older snapshot's binding.
    op.create_table(
        "gateway_profile_revisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("gateway_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("published_by", sa.String(length=128), nullable=False),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "profile_id", "version",
            name="uq_gateway_profile_revisions_profile_version",
        ),
    )
    op.create_index(
        "ix_gateway_profile_revisions_profile",
        "gateway_profile_revisions",
        ["profile_id"],
        unique=False,
    )

    # 3. Bindings — explicit selection. The v2 resolver looks up
    #    (workspace_id, environment_id, model_alias) and follows to the
    #    revision. Zero alphabetical fallback.
    op.create_table(
        "gateway_profile_bindings",
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "environment_id",
            UUID(as_uuid=True),
            sa.ForeignKey("environments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("model_alias", sa.String(length=128), primary_key=True),
        sa.Column(
            "revision_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "gateway_profile_revisions.id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_gateway_profile_bindings_revision",
        "gateway_profile_bindings",
        ["revision_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_gateway_profile_bindings_revision", table_name="gateway_profile_bindings")
    op.drop_table("gateway_profile_bindings")
    op.drop_index("ix_gateway_profile_revisions_profile", table_name="gateway_profile_revisions")
    op.drop_table("gateway_profile_revisions")
    op.drop_index("ix_gateway_profiles_model_alias", table_name="gateway_profiles")
    op.drop_column("gateway_profiles", "model_alias")
    op.drop_column("gateway_profiles", "working_copy")
