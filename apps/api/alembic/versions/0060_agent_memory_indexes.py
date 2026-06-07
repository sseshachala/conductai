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
    # CONCURRENTLY cannot run inside a transaction block — use autocommit_block().
    with op.get_context().autocommit_block():
        # Composite index for the WHERE clause filters before pgvector distance ordering.
        op.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_agent_memory_search
            ON agent_memory (workspace_id, playbook_slug, scope, key)
            WHERE embedding IS NOT NULL
        """)
        # IVFFlat index for cosine similarity search.
        # lists=100 is safe up to ~1M rows; tune upward as data grows.
        op.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_agent_memory_embedding
            ON agent_memory USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
            WHERE embedding IS NOT NULL
        """)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_agent_memory_embedding")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_agent_memory_search")
