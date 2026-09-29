"""Workspace-owned principal approvals, sticky caller bindings and live grants."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0155"
down_revision = "0154"
branch_labels = None
depends_on = None


def common():
    return [sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("actions", JSONB, nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False)]


def upgrade():
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.execute("SET LOCAL statement_timeout = '60s'")
    op.create_index("uq_agent_identity_workspace_id", "agent_identities", ["workspace_id", "id"], unique=True)
    op.create_table("federation_principals", *common(),
                    sa.Column("issuer", sa.String(512), nullable=False),
                    sa.Column("subject", sa.String(512), nullable=False),
                    sa.Column("kind", sa.String(16), nullable=False),
                    sa.UniqueConstraint("workspace_id", "issuer", "subject", name="uq_federation_principal_subject"),
                    sa.UniqueConstraint("workspace_id", "id", name="uq_federation_principal_workspace"))
    op.create_table("federation_caller_bindings", *common(),
                    sa.Column("caller_id", sa.String(36), nullable=False, unique=True),
                    sa.Column("connection_id", UUID(as_uuid=True), nullable=False),
                    sa.ForeignKeyConstraint(["workspace_id", "caller_id"],
                                            ["agent_identities.workspace_id", "agent_identities.id"]),
                    sa.ForeignKeyConstraint(["workspace_id", "connection_id"],
                                            ["federation_connections.workspace_id", "federation_connections.id"]),
                    sa.UniqueConstraint("workspace_id", "id", name="uq_federation_binding_workspace"))
    op.create_table("federation_grants", *common(),
                    sa.Column("binding_id", UUID(as_uuid=True), nullable=False),
                    sa.Column("principal_id", UUID(as_uuid=True), nullable=False),
                    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                    sa.ForeignKeyConstraint(["workspace_id", "binding_id"],
                                            ["federation_caller_bindings.workspace_id", "federation_caller_bindings.id"]),
                    sa.ForeignKeyConstraint(["workspace_id", "principal_id"],
                                            ["federation_principals.workspace_id", "federation_principals.id"]),
                    sa.UniqueConstraint("binding_id", "principal_id", name="uq_federation_grant_principal"))
    for table in ("federation_connections", "federation_principals", "federation_caller_bindings", "federation_grants"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"""CREATE POLICY federation_workspace_isolation ON {table}
            USING (workspace_id = NULLIF(current_setting('app.current_workspace', true), '')::uuid)
            WITH CHECK (workspace_id = NULLIF(current_setting('app.current_workspace', true), '')::uuid)"""))


def downgrade():
    # Even disabled bindings are enforcement requirements. Removing populated
    # tables would silently downgrade required identity to legacy service mode.
    for table in ("federation_grants", "federation_caller_bindings", "federation_principals"):
        op.execute(sa.text(f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE"))
        if op.get_bind().execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar_one():
            raise RuntimeError("Federation delegation requires a data-preserving rollback plan")
    for table in ("federation_grants", "federation_caller_bindings", "federation_principals"):
        op.drop_table(table)
    op.execute("DROP POLICY federation_workspace_isolation ON federation_connections")
    op.execute("ALTER TABLE federation_connections NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE federation_connections DISABLE ROW LEVEL SECURITY")
    op.drop_index("uq_agent_identity_workspace_id", table_name="agent_identities")
