"""Optional display labels; issuer and subject remain the identity key."""
from alembic import op
import sqlalchemy as sa

revision = "0156"
down_revision = "0155"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.execute("SET LOCAL statement_timeout = '60s'")
    op.add_column("federation_principals", sa.Column("display_name", sa.String(200), nullable=True))


def downgrade():
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.execute("SET LOCAL statement_timeout = '60s'")
    op.drop_column("federation_principals", "display_name")
