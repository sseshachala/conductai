"""Single-use reviewed security fixture approvals, independent of rule overrides."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0161"
down_revision = "0160"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.create_table(
        "guard_fixture_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subject_id", sa.String(255), nullable=False),
        sa.Column("approved_by", sa.String(255), nullable=False),
        sa.Column("action_digest", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_guard_fixture_approval_lookup",
        "guard_fixture_approvals",
        ["workspace_id", "subject_id", "action_digest"],
    )


def downgrade():
    op.execute("LOCK TABLE guard_fixture_approvals IN ACCESS EXCLUSIVE MODE")
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM guard_fixture_approvals)"))
        .scalar_one()
    ):
        raise RuntimeError("Fixture approvals require a data-preserving rollback plan")
    op.drop_table("guard_fixture_approvals")
