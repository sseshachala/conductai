"""Gateway Profile v3 schema — cond_code + active_revision_id.

Collapses the environment binding model into a much simpler shape.

Old model:
- `gateway_profiles` has a mutable `working_copy`.
- `gateway_profile_bindings` maps `(workspace × env × alias)` to a revision.
- Publish creates a revision AND updates the binding.

New model:
- `gateway_profiles` gains:
    - `cond_code`         — server-generated, immutable, unique per workspace.
                            Becomes the client-facing routing key
                            (`cond-<code>-<alias>`).
    - `active_revision_id` — nullable FK to the currently published revision.
                            NULL = draft (no live config).
- Publish sets `active_revision_id`. Rollback re-points it to an older
  revision. Environment is not part of the profile abstraction anymore —
  vault refs live inside the working_copy's target `credential_ref`
  values.
- `gateway_profile_bindings` and `gateway_profile_binding_events`
  disappear. Revisions table is unchanged (still the immutable history
  the rollback endpoint walks).

Backfill

- `cond_code` is populated for every existing profile via
  `substring(md5(random() || id::text), 1, 8)` — 8 hex chars, uniform
  distribution, effectively zero collision risk within a workspace
  (fewer than a handful of profiles per workspace today). Unique
  constraint on `(workspace_id, cond_code)` catches the collision case
  if it ever fires.
- `active_revision_id` is populated with the latest revision id for
  each profile that has ever been published, so serving continuity is
  preserved. Profiles with no revisions get NULL.

Revision ID: 0137
Revises: 0136
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0137"
down_revision = "0136"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add cond_code + active_revision_id as nullable, backfill, then lock.
    op.add_column(
        "gateway_profiles",
        sa.Column("cond_code", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "gateway_profiles",
        sa.Column(
            "active_revision_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "gateway_profile_revisions.id",
                ondelete="RESTRICT",
                name="fk_gateway_profiles_active_revision",
            ),
            nullable=True,
        ),
    )

    # cond_code backfill. md5 -> 8 hex chars, then downcase for the
    # canonical form. Guarantees non-null for every row before we lock
    # the NOT NULL + unique constraint below.
    op.execute("""
        UPDATE gateway_profiles
        SET cond_code = substring(md5(random()::text || id::text), 1, 8)
        WHERE cond_code IS NULL
    """)

    # active_revision_id backfill — latest revision per profile.
    op.execute("""
        UPDATE gateway_profiles p
        SET active_revision_id = latest.rev_id
        FROM (
            SELECT DISTINCT ON (profile_id) profile_id, id AS rev_id
            FROM gateway_profile_revisions
            ORDER BY profile_id, version DESC
        ) latest
        WHERE p.id = latest.profile_id
    """)

    # Lock cond_code nullability + uniqueness now that it's backfilled.
    op.alter_column(
        "gateway_profiles", "cond_code",
        existing_type=sa.String(length=32), nullable=False,
    )
    op.create_unique_constraint(
        "uq_gateway_profiles_workspace_cond_code",
        "gateway_profiles",
        ["workspace_id", "cond_code"],
    )
    op.create_index(
        "ix_gateway_profiles_active_revision",
        "gateway_profiles",
        ["active_revision_id"],
    )

    # 2. Drop the binding tables and their audit trail. New model
    #    doesn't need them — active_revision_id on the profile row
    #    plus the revisions table is the whole story.
    op.drop_table("gateway_profile_binding_events")
    op.drop_table("gateway_profile_bindings")


def downgrade():
    # Recreate binding tables (empty), then drop the new columns.
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
            sa.ForeignKey("gateway_profile_revisions.id", ondelete="RESTRICT"),
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
    )

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

    op.drop_index(
        "ix_gateway_profiles_active_revision",
        table_name="gateway_profiles",
    )
    op.drop_constraint(
        "uq_gateway_profiles_workspace_cond_code",
        "gateway_profiles",
        type_="unique",
    )
    op.drop_column("gateway_profiles", "active_revision_id")
    op.drop_column("gateway_profiles", "cond_code")
