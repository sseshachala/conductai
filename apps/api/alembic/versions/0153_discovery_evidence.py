"""Installation-scoped discovery and separately retained hook evidence."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0153"
down_revision = "0152"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("discovered_agents", sa.Column("device_id", postgresql.UUID(as_uuid=True)))
    op.add_column("discovered_agents", sa.Column("installation_id", sa.String(64)))
    op.add_column("discovered_agents", sa.Column("detection", sa.String(30)))
    op.add_column("discovered_agents", sa.Column("hook_observed_at", sa.DateTime(timezone=True)))
    op.add_column("discovered_agents", sa.Column("hook_event_id", postgresql.UUID(as_uuid=True)))
    # Retain the legacy unique key for rolling deployments. Normalized rows use
    # NULL source and the installation key; PostgreSQL allows distinct NULLs.
    op.create_unique_constraint("uq_discovered_agents_installation", "discovered_agents", ["workspace_id", "device_id", "installation_id"])
    # Legacy flags are configuration assertions, not evidence of enforcement.
    # Discard unstructured evidence that may include process arguments.
    op.execute("UPDATE discovered_agents SET under_guard = false, proxy_routed = false, evidence = NULL, location = NULL")
    op.execute("DELETE FROM guard_knowledge_index WHERE source_kind = 'discovered_agent'")


def downgrade():
    # Prevent a concurrent writer from adding evidence after the safety check.
    op.execute("LOCK TABLE discovered_agents IN ACCESS EXCLUSIVE MODE")
    populated = op.get_bind().execute(sa.text("""SELECT EXISTS (
        SELECT 1 FROM discovered_agents WHERE device_id IS NOT NULL
        OR installation_id IS NOT NULL OR detection IS NOT NULL
        OR hook_observed_at IS NOT NULL OR hook_event_id IS NOT NULL
    )""")).scalar_one()
    if populated:
        raise RuntimeError("Discovery identity migration requires an explicit data-preserving rollback plan")
    op.drop_constraint("uq_discovered_agents_installation", "discovered_agents", type_="unique")
    for column in ("hook_event_id", "hook_observed_at", "detection", "installation_id", "device_id"):
        op.drop_column("discovered_agents", column)
