"""Draft federation trust configuration, independent of runtime activation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0154"
down_revision = "0153"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_integrations_workspace_id", "integrations", ["workspace_id", "id"])
    op.create_table(
        "federation_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "id", name="uq_federation_workspace_id"),
        sa.ForeignKeyConstraint(["workspace_id", "integration_id"], ["integrations.workspace_id", "integrations.id"],
                                name="fk_federation_integration_workspace"),
        sa.CheckConstraint("revision > 0", name="ck_federation_revision"),
    )
    op.create_index("ix_federation_connections_workspace_id", "federation_connections", ["workspace_id"])


def downgrade():
    op.execute("LOCK TABLE federation_connections IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM federation_connections)")).scalar_one():
        raise RuntimeError("Federation configuration requires an explicit data-preserving rollback plan")
    op.drop_table("federation_connections")
    op.drop_constraint("uq_integrations_workspace_id", "integrations", type_="unique")
