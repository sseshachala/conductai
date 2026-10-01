"""Add opt-in review state to registered MCP servers."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0159"
down_revision = "0158"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.add_column("mcp_servers", sa.Column("governance", postgresql.JSONB(), nullable=True))


def downgrade():
    # Removing active policy would silently restore access during rollback.
    op.execute("LOCK TABLE mcp_servers IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM mcp_servers WHERE governance IS NOT NULL)")).scalar_one():
        raise RuntimeError("MCP review state requires a data-preserving rollback plan")
    op.drop_column("mcp_servers", "governance")
