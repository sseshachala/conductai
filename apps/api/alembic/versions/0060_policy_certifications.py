"""policy_certifications: quarterly review audit table

Revision ID: 0060
Revises: 0059
"""
from alembic import op
import sqlalchemy as sa

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS policy_certifications (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            pack_slug       TEXT NOT NULL,
            certified_by    TEXT NOT NULL,
            policy_version  TEXT,
            certified_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_policy_cert_ws_pack_ts
        ON policy_certifications(workspace_id, pack_slug, certified_at DESC)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS policy_certifications")
