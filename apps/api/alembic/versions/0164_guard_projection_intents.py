"""Add durable Guard projection intents and bounded allowed summaries."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0164"
down_revision = "0163"
branch_labels = None
depends_on = None


def _enable_workspace_rls(table: str, policy: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"""CREATE POLICY {policy} ON {table}
        USING (workspace_id = NULLIF(current_setting('app.current_workspace', true), '')::uuid)
        WITH CHECK (workspace_id = NULLIF(current_setting('app.current_workspace', true), '')::uuid)""")


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.add_column(
        "guard_knowledge_index",
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "guard_knowledge_index",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_guard_knowledge_index_expires_at", "guard_knowledge_index", ["expires_at"]
    )

    op.create_table(
        "guard_projection_intents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("source_version", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_guard_projection_intents_workspace_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "source_kind",
            "source_id",
            "source_version",
            name="uq_guard_projection_intent_source_version",
        ),
        sa.CheckConstraint(
            "attempts >= 0", name="ck_guard_projection_intents_attempts"
        ),
        sa.CheckConstraint(
            "max_attempts > 0", name="ck_guard_projection_intents_max_attempts"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'retry', 'completed', 'dead_letter', 'superseded', 'expired', 'missing')",
            name="ck_guard_projection_intents_status",
        ),
        sa.CheckConstraint(
            "source_kind IN ('audit_event', 'rule', 'discovered_agent', 'audit_summary')",
            name="ck_guard_projection_intents_source_kind",
        ),
    )
    op.create_index(
        "ix_guard_projection_intents_pending",
        "guard_projection_intents",
        ["available_at", "created_at"],
        postgresql_where=sa.text("status IN ('pending', 'retry')"),
    )
    op.create_index(
        "ix_guard_projection_intents_lease",
        "guard_projection_intents",
        ["lease_expires_at"],
        postgresql_where=sa.text("status = 'processing'"),
    )
    _enable_workspace_rls(
        "guard_projection_intents", "guard_projection_intents_workspace"
    )

    op.create_table(
        "guard_projection_summaries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dimension_key", sa.String(64), nullable=False),
        sa.Column("ai_tool", sa.String(50), nullable=False),
        sa.Column("tool_call", sa.String(255), nullable=False),
        sa.Column("rule_id", sa.String(255), nullable=False, server_default=""),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("canonical_facts", postgresql.JSONB(), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_guard_projection_summaries_workspace_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "window_start",
            "dimension_key",
            name="uq_guard_projection_summary_window_dimension",
        ),
        sa.CheckConstraint(
            "window_end > window_start", name="ck_guard_projection_summary_window"
        ),
        sa.CheckConstraint(
            "event_count > 0", name="ck_guard_projection_summary_event_count"
        ),
        sa.CheckConstraint("version > 0", name="ck_guard_projection_summary_version"),
        sa.CheckConstraint(
            "expires_at > source_timestamp", name="ck_guard_projection_summary_expiry"
        ),
    )
    op.create_index(
        "ix_guard_projection_summaries_workspace_window",
        "guard_projection_summaries",
        ["workspace_id", "window_start"],
    )
    op.create_index(
        "ix_guard_projection_summaries_expires_at",
        "guard_projection_summaries",
        ["expires_at"],
    )
    _enable_workspace_rls(
        "guard_projection_summaries", "guard_projection_summaries_workspace"
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '3s'")
    bind = op.get_bind()
    workspace_ids = bind.execute(sa.text("SELECT id FROM workspaces")).scalars().all()
    for workspace_id in workspace_ids:
        bind.execute(
            sa.text("SELECT set_config('app.current_workspace', :ws, true)"),
            {"ws": str(workspace_id)},
        )
        for table in ("guard_projection_intents", "guard_projection_summaries"):
            if bind.execute(
                sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")
            ).scalar_one():
                raise RuntimeError(
                    f"Export or drain {table} before downgrading migration 0164"
                )
    if bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM guard_knowledge_index WHERE source_timestamp IS NOT NULL OR expires_at IS NOT NULL)"
        )
    ).scalar_one():
        raise RuntimeError(
            "Export projection retention metadata before downgrading migration 0164"
        )
    op.drop_table("guard_projection_summaries")
    op.drop_table("guard_projection_intents")
    op.drop_index(
        "ix_guard_knowledge_index_expires_at", table_name="guard_knowledge_index"
    )
    op.drop_column("guard_knowledge_index", "expires_at")
    op.drop_column("guard_knowledge_index", "source_timestamp")
