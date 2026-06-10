"""feat: team_session_memory table with HNSW vector index

Revision ID: 0074
Revises: 0073
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_session_memory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "developer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("tool", sa.String(50), nullable=False, server_default="claude_code"),
        sa.Column("repo_full_name", sa.Text(), nullable=True),
        sa.Column("topic_tags", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("light_summary", sa.Text(), nullable=False),
        sa.Column("deep_summary", sa.Text(), nullable=True),
        sa.Column("files_touched", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("decisions", postgresql.JSONB(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="team"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Add pgvector column after table creation (ALTER TABLE to keep DDL clean)
    op.execute("ALTER TABLE team_session_memory ADD COLUMN embedding vector(1536)")

    op.create_index(
        "ix_tsm_workspace_repo",
        "team_session_memory",
        ["workspace_id", "repo_full_name"],
    )

    with op.get_context().autocommit_block():
        op.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_tsm_hnsw
            ON team_session_memory USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            WHERE embedding IS NOT NULL
        """)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_tsm_hnsw")

    op.drop_index("ix_tsm_workspace_repo", table_name="team_session_memory")
    op.drop_table("team_session_memory")
