"""Move Gateway limits to stable profile IDs, retaining legacy limits."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0163"
down_revision = "0162"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.create_unique_constraint("uq_gateway_profiles_id_workspace", "gateway_profiles", ["id", "workspace_id"])
    op.create_table(
        "gateway_profile_rate_limits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", UUID(as_uuid=True), nullable=False),
        sa.Column("agent_identity_id", sa.String(36), sa.ForeignKey("agent_identities.id", ondelete="CASCADE")),
        sa.Column("rpm", sa.Integer), sa.Column("tpm", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["profile_id", "workspace_id"], ["gateway_profiles.id", "gateway_profiles.workspace_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id", "agent_identity_id"], ["agent_identities.workspace_id", "agent_identities.id"], ondelete="CASCADE"),
        sa.CheckConstraint("rpm IS NULL OR rpm > 0", name="ck_gateway_profile_rate_rpm"),
        sa.CheckConstraint("tpm IS NULL OR tpm > 0", name="ck_gateway_profile_rate_tpm"),
    )
    op.create_index("uq_gateway_profile_rate_default", "gateway_profile_rate_limits", ["profile_id"], unique=True, postgresql_where=sa.text("agent_identity_id IS NULL"))
    op.create_index("uq_gateway_profile_rate_agent", "gateway_profile_rate_limits", ["profile_id", "agent_identity_id"], unique=True, postgresql_where=sa.text("agent_identity_id IS NOT NULL"))
    op.create_index("ix_gateway_profile_rate_workspace", "gateway_profile_rate_limits", ["workspace_id"])
    # Old default rows may be duplicated because NULL bypassed their unique
    # constraint. Preserve the strictest non-null cap rather than dropping one.
    op.execute("""
        INSERT INTO gateway_profile_rate_limits (workspace_id, profile_id, agent_identity_id, rpm, tpm)
        SELECT p.workspace_id, p.id, r.agent_identity_id, min(r.rpm), min(r.tpm)
        FROM gateway_profiles p JOIN guard_rate_limits r ON r.workspace_id = p.workspace_id
        WHERE p.schema_version = '2'
        GROUP BY p.workspace_id, p.id, r.agent_identity_id
    """)
    op.execute("ALTER TABLE gateway_profile_rate_limits ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gateway_profile_rate_limits FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY gateway_profile_rate_workspace ON gateway_profile_rate_limits
        USING (workspace_id = NULLIF(current_setting('app.current_workspace', true), '')::uuid)
        WITH CHECK (workspace_id = NULLIF(current_setting('app.current_workspace', true), '')::uuid)""")


def downgrade():
    # Legacy rows are untouched and remain available to the old application.
    # Do not discard newly edited profile limits during a schema rollback.
    bind = op.get_bind()
    for workspace_id in bind.execute(sa.text("SELECT id FROM workspaces")).scalars():
        bind.execute(sa.text("SELECT set_config('app.current_workspace', :ws, true)"), {"ws": str(workspace_id)})
        if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM gateway_profile_rate_limits)")).scalar():
            raise RuntimeError("Export profile rate limits before downgrading migration 0163")
    op.drop_table("gateway_profile_rate_limits")
    op.drop_constraint("uq_gateway_profiles_id_workspace", "gateway_profiles", type_="unique")
