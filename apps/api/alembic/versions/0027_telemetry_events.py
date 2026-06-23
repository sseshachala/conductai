"""telemetry_events — CLI/booster process-health events

Captures structured events from conduct-cli and agent-booster: errors with
traceback, warnings, and the occasional info ping. Correlation keys
(workspace_id, run_id, session_id) are all nullable — only what's known at
log time gets recorded. Soft links only (no FKs) so telemetry ingestion never
fails on a missing parent row.

Correlation model:
  workspace_id → tenant (kept on the row for fast filter without join)
  run_id       → which run (nullable; JOIN runs → workflows → projects derives
                  project, agent context — no need to denormalize)
  session_id   → guard_audit_events.hook_session_id (soft link to Guard activity)

Anything finer-grained (agent/block id, custom labels) goes in `context` jsonb.

Part of #718 Phase 1.

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telemetry_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_id",       postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tool",         sa.Text,                       nullable=False),
        sa.Column("version",      sa.Text,                       nullable=False),
        sa.Column("event_type",   sa.Text,                       nullable=False),
        sa.Column("message",      sa.Text,                       nullable=False),
        sa.Column("traceback",    sa.Text,                       nullable=True),
        sa.Column("session_id",   sa.Text,                       nullable=True),
        sa.Column(
            "context",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "ts",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "event_type IN ('info','warning','error')",
            name="telemetry_events_event_type_chk",
        ),
        sa.CheckConstraint(
            "tool IN ('conduct-cli','agent-booster')",
            name="telemetry_events_tool_chk",
        ),
    )
    op.create_index(
        "ix_telemetry_ws_type_ts",
        "telemetry_events",
        ["workspace_id", "event_type", sa.text("ts DESC")],
    )
    op.create_index(
        "ix_telemetry_ws_run",
        "telemetry_events",
        ["workspace_id", "run_id"],
    )
    op.create_index(
        "ix_telemetry_session",
        "telemetry_events",
        ["workspace_id", "session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_telemetry_session",    table_name="telemetry_events")
    op.drop_index("ix_telemetry_ws_run",     table_name="telemetry_events")
    op.drop_index("ix_telemetry_ws_type_ts", table_name="telemetry_events")
    op.drop_table("telemetry_events")
