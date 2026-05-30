"""0031 watchdog_events — observability event log + heartbeat column

Revision ID: 0031
Revises: 0030
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "runs",
        sa.Column("last_heartbeat_time", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "watchdog_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.String(255), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="info"),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_watchdog_events_workspace_id", "watchdog_events", ["workspace_id"])
    op.create_index("ix_watchdog_events_created_at", "watchdog_events", ["created_at"])


def downgrade():
    op.drop_index("ix_watchdog_events_created_at", table_name="watchdog_events")
    op.drop_index("ix_watchdog_events_workspace_id", table_name="watchdog_events")
    op.drop_table("watchdog_events")
    op.drop_column("runs", "last_heartbeat_time")
