"""0026 agent_memory — persistent vector memory for agents

Adds agent_memory table for the memory block type. Each row stores a
plain-text summary plus a vector embedding for semantic similarity search.

Uses pgvector extension (must be enabled on the Postgres instance).
Embedding dimensions: 1536 (OpenAI text-embedding-3-small).
Swap to 512 for Voyage voyage-3-lite by changing the column definition
and updating OPENAI_DIMENSIONS in embedding_client.py.

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    # Enable pgvector extension if not already present
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "agent_memory",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("playbook_slug", sa.String(100), nullable=False),
        sa.Column("scope", sa.String(50), nullable=False),   # repo | issue_type | agent
        sa.Column("key", sa.Text, nullable=False),           # owner/repo, slug:category, etc.
        sa.Column("summary", sa.Text, nullable=False),       # plain text written by memory block
        sa.Column("embedding", sa.Text, nullable=True),      # stored as text, cast to vector at query time
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_index(
        "ix_agent_memory_lookup",
        "agent_memory",
        ["workspace_id", "playbook_slug", "scope", "key"],
    )
    op.create_index(
        "ix_agent_memory_created",
        "agent_memory",
        ["workspace_id", "playbook_slug", "scope", "key", "created_at"],
    )


def downgrade():
    op.drop_index("ix_agent_memory_created", table_name="agent_memory")
    op.drop_index("ix_agent_memory_lookup", table_name="agent_memory")
    op.drop_table("agent_memory")
