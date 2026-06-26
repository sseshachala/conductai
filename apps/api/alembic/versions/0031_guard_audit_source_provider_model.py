"""guard_audit_events — add source + provider + model columns

Today every audit row uses `tool_call` for everything:
  - hook events:  'Edit', 'Bash', 'Read'
  - proxy events: 'anthropic/claude-haiku-4-5-20251001'

Filtering and rollups need to parse strings. Splitting into structured columns:

  source    — 'hook' | 'proxy' | 'mcp'  (where this row came from)
  provider  — 'anthropic' | 'openai' | 'perplexity' | NULL
  model     — vendor model id (NULL for hook events)

Backwards compatible: tool_call kept. Hook ingest stays unchanged (defaults
to source='hook'). Proxy starts populating all three.

Revision ID: 0031
Revises: 0030
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa


revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guard_audit_events",
        sa.Column("source", sa.String(20), nullable=False, server_default="hook"),
    )
    op.add_column(
        "guard_audit_events",
        sa.Column("provider", sa.String(30), nullable=True),
    )
    op.add_column(
        "guard_audit_events",
        sa.Column("model", sa.String(100), nullable=True),
    )

    # Proxy events don't have a tool name (raw LLM call) — structured
    # provider+model replace it. Make tool_call nullable.
    op.alter_column("guard_audit_events", "tool_call", nullable=True)

    op.create_index(
        "ix_guard_audit_events_source", "guard_audit_events",
        ["workspace_id", "source", "ts"],
    )
    op.create_index(
        "ix_guard_audit_events_provider", "guard_audit_events",
        ["workspace_id", "provider", "ts"],
        postgresql_where=sa.text("provider IS NOT NULL"),
    )


def downgrade() -> None:
    op.alter_column("guard_audit_events", "tool_call", nullable=False)
    op.drop_index("ix_guard_audit_events_provider", table_name="guard_audit_events")
    op.drop_index("ix_guard_audit_events_source", table_name="guard_audit_events")
    op.drop_column("guard_audit_events", "model")
    op.drop_column("guard_audit_events", "provider")
    op.drop_column("guard_audit_events", "source")
