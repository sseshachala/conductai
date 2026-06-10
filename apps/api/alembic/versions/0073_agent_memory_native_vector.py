"""perf: migrate agent_memory.embedding from Text to native vector(1536) + HNSW index

Converts the JSON-serialised text column to a native pgvector column so that
the HNSW approximate-nearest-neighbour index can be built. Without native type
the database cannot build any ANN index and falls back to O(n) full table scan.

Previous state (0060): column is Text, cast to vector at query time via ::vector.
After this migration: column IS vector(1536), HNSW index enables sub-linear ANN.

Dimension note: 1536 matches OpenAI text-embedding-3-small. Voyage voyage-3-lite
uses 512d — if Voyage is ever activated as primary, a second column (vector(512))
should be added rather than changing this one.

Revision ID: 0073
Revises: 0072
Create Date: 2026-06-09
"""
from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the partial composite index from 0060 — it filtered on embedding IS NOT NULL
    # but referenced the Text column; we'll recreate it after the type change.
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_agent_memory_search")

    # Convert Text → vector(1536).
    # USING clause casts the stored JSON array string directly; pgvector accepts
    # '[0.1, 0.2, ...]' string literals in the same format Python json.dumps produces.
    # Rows with NULL embedding are unaffected. Rows with dimension != 1536 will fail
    # here — there should be none since Voyage (512d) was never activated.
    op.execute(
        "ALTER TABLE agent_memory "
        "ALTER COLUMN embedding TYPE vector(1536) "
        "USING embedding::vector"
    )

    # Rebuild the composite filter index now that the column type is correct.
    with op.get_context().autocommit_block():
        op.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_agent_memory_search
            ON agent_memory (workspace_id, playbook_slug, scope, key)
            WHERE embedding IS NOT NULL
        """)

        # HNSW index for approximate nearest-neighbour cosine search.
        # m=16 ef_construction=64 are pgvector defaults — good starting point.
        # Reindex with higher ef_construction if recall quality degrades at scale.
        op.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_agent_memory_hnsw
            ON agent_memory USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_agent_memory_hnsw")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_agent_memory_search")

    # Revert to Text; existing vectors are serialised back to JSON strings.
    op.execute(
        "ALTER TABLE agent_memory "
        "ALTER COLUMN embedding TYPE text "
        "USING embedding::text"
    )

    with op.get_context().autocommit_block():
        op.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_agent_memory_search
            ON agent_memory (workspace_id, playbook_slug, scope, key)
            WHERE embedding IS NOT NULL
        """)
