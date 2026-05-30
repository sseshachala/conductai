"""0030 online_eval_tables — run_online_scores + run_fixture_candidates

Revision ID: 0030
Revises: 0029
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "run_online_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("grade", sa.String(5), nullable=False),
        sa.Column("pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("mechanical_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mechanical_max", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("judge_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("judge_max", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("judge_used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("run_status", sa.String(50), nullable=True),
        sa.Column("outcome_type", sa.String(255), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("anonymized_outcome", postgresql.JSONB(), nullable=True),
        sa.Column(
            "scored_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_run_online_scores_run_id", "run_online_scores", ["run_id"], unique=True)
    op.create_index("ix_run_online_scores_slug", "run_online_scores", ["slug"])
    op.create_index("ix_run_online_scores_grade", "run_online_scores", ["grade"])
    op.create_index("ix_run_online_scores_scored_at", "run_online_scores", ["scored_at"])

    op.create_table(
        "run_fixture_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("grade", sa.String(5), nullable=False),
        sa.Column("pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("anon_trigger_payload", postgresql.JSONB(), nullable=True),
        sa.Column("anon_state", postgresql.JSONB(), nullable=True),
        sa.Column("expected_outcome_type", sa.String(255), nullable=True),
        # pending | promoted | dismissed
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("promoted_pr_url", sa.Text(), nullable=True),
        sa.Column("promoted_by", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_run_fixture_candidates_run_id", "run_fixture_candidates", ["run_id"], unique=True)
    op.create_index("ix_run_fixture_candidates_slug", "run_fixture_candidates", ["slug"])
    op.create_index("ix_run_fixture_candidates_status", "run_fixture_candidates", ["status"])


def downgrade():
    op.drop_index("ix_run_fixture_candidates_status", table_name="run_fixture_candidates")
    op.drop_index("ix_run_fixture_candidates_slug", table_name="run_fixture_candidates")
    op.drop_index("ix_run_fixture_candidates_run_id", table_name="run_fixture_candidates")
    op.drop_table("run_fixture_candidates")

    op.drop_index("ix_run_online_scores_scored_at", table_name="run_online_scores")
    op.drop_index("ix_run_online_scores_grade", table_name="run_online_scores")
    op.drop_index("ix_run_online_scores_slug", table_name="run_online_scores")
    op.drop_index("ix_run_online_scores_run_id", table_name="run_online_scores")
    op.drop_table("run_online_scores")
