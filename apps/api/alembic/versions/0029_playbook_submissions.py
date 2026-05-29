"""0029 playbook_submissions — add playbook_submissions table for eval promotion loop

Revision ID: 0029
Revises: 0028
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "playbook_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="builtin"),
        sa.Column("structural_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quality_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("grade", sa.String(5), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("criteria_json", sa.Text(), nullable=True),
        sa.Column("eval_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_playbook_submissions_slug", "playbook_submissions", ["slug"])
    op.create_index("ix_playbook_submissions_status", "playbook_submissions", ["status"])


def downgrade():
    op.drop_index("ix_playbook_submissions_status", table_name="playbook_submissions")
    op.drop_index("ix_playbook_submissions_slug", table_name="playbook_submissions")
    op.drop_table("playbook_submissions")
