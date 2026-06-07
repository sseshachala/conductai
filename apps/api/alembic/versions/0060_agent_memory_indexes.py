"""perf: add composite + ivfflat indexes on agent_memory for vector search

Revision ID: 0060
Revises: 0059
Create Date: 2026-06-07
"""
from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Composite index for the WHERE clause filters — covers workspace_id,
    # playbook_slug, scope, key lookups before pgvector distance ordering.
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_agent_memory_search
        ON agent_memory (workspace_id, playbook_slug, scope, key)
        WHERE embedding IS NOT NULL
    """)

    # IVFFlat index for cosine similarity — accelerates ORDER BY distance.
    # lists=100 is a safe default for up to ~1M rows; tune upward as data grows.
    # Requires pgvector extension (already enabled via earlier migration).
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_agent_memory_embedding
        ON agent_memory USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        WHERE embedding IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_agent_memory_embedding")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_agent_memory_search")
