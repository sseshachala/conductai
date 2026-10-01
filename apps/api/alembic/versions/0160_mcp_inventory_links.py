"""Keep administrator MCP inventory associations separate from scan evidence."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0160"
down_revision = "0159"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.add_column("discovered_agents", sa.Column("mcp_links", postgresql.JSONB(), nullable=True))


def downgrade():
    op.execute("LOCK TABLE discovered_agents IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM discovered_agents WHERE mcp_links IS NOT NULL)"
    )).scalar_one():
        raise RuntimeError("MCP inventory associations require a data-preserving rollback plan")
    op.drop_column("discovered_agents", "mcp_links")
