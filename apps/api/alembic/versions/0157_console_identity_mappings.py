"""Explicit deployment console identity mappings; no automatic account linking."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0157"
down_revision = "0156"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.execute("SET LOCAL statement_timeout = '60s'")
    op.create_table(
        "console_identity_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("issuer", sa.String(2048), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200)),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("issuer", "subject", name="uq_console_issuer_subject"),
    )


def downgrade():
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.execute("SET LOCAL statement_timeout = '60s'")
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM console_identity_mappings)")).scalar():
        raise RuntimeError("Console identity mappings exist; export and explicitly retire them before rollback")
    op.drop_table("console_identity_mappings")
