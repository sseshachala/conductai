"""add guard_knowledge_index table for GLens semantic search

Revision ID: 0079
Revises: 0078
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE guard_knowledge_index (
            id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID        NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            source_kind  TEXT        NOT NULL,
            source_id    TEXT        NOT NULL,
            canonical_text TEXT      NOT NULL,
            metadata     JSONB       NOT NULL DEFAULT '{}',
            content_hash TEXT        NOT NULL,
            embedding    vector(1536),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (workspace_id, source_kind, source_id)
        )
    """)
    op.execute("""
        CREATE INDEX ON guard_knowledge_index
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
    """)
    op.execute("""
        CREATE INDEX ON guard_knowledge_index (workspace_id, source_kind)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS guard_knowledge_index")
