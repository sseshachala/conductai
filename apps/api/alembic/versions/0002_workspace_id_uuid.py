"""Standardize workspace_id to UUID on audit_log, watchdog_events, security_findings, conduct_api_keys.

All four tables stored workspace_id as VARCHAR, causing implicit casts on joins
and defeating index use when joining against UUID-typed workspace_id columns on
other tables. This migration casts them to native UUID in-place.

IMPORTANT: existing databases must have only valid UUID strings in these columns.
Run the following check before upgrading:

  SELECT table_name, workspace_id FROM (
    SELECT 'audit_log' AS table_name, workspace_id FROM audit_log
    UNION ALL
    SELECT 'watchdog_events', workspace_id FROM watchdog_events
    UNION ALL
    SELECT 'security_findings', workspace_id FROM security_findings
    UNION ALL
    SELECT 'conduct_api_keys', workspace_id FROM conduct_api_keys
  ) t
  WHERE workspace_id !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';

If that returns rows, fix them before running this migration.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── audit_log ─────────────────────────────────────────────────────────────
    op.drop_index("ix_audit_log_workspace_created", table_name="audit_log")
    op.drop_index("ix_audit_log_workspace_action", table_name="audit_log")
    op.execute("ALTER TABLE audit_log ALTER COLUMN workspace_id TYPE UUID USING workspace_id::uuid")
    op.create_index("ix_audit_log_workspace_created", "audit_log", ["workspace_id", "created_at"])
    op.create_index("ix_audit_log_workspace_action", "audit_log", ["workspace_id", "action"])

    # ── watchdog_events ───────────────────────────────────────────────────────
    op.drop_index("ix_watchdog_events_workspace_id", table_name="watchdog_events")
    op.execute("ALTER TABLE watchdog_events ALTER COLUMN workspace_id TYPE UUID USING workspace_id::uuid")
    op.create_index("ix_watchdog_events_workspace_id", "watchdog_events", ["workspace_id"])

    # ── security_findings ─────────────────────────────────────────────────────
    op.drop_index("ix_security_findings_workspace_id", table_name="security_findings")
    op.drop_index("ix_security_findings_status", table_name="security_findings")
    op.execute("ALTER TABLE security_findings ALTER COLUMN workspace_id TYPE UUID USING workspace_id::uuid")
    op.create_index("ix_security_findings_workspace_id", "security_findings", ["workspace_id"])
    op.create_index("ix_security_findings_status", "security_findings", ["workspace_id", "status"])

    # ── conduct_api_keys ──────────────────────────────────────────────────────
    op.drop_index("ix_conduct_api_keys_workspace_id", table_name="conduct_api_keys")
    op.execute("ALTER TABLE conduct_api_keys ALTER COLUMN workspace_id TYPE UUID USING workspace_id::uuid")
    op.create_index("ix_conduct_api_keys_workspace_id", "conduct_api_keys", ["workspace_id"])


def downgrade() -> None:
    # ── conduct_api_keys ──────────────────────────────────────────────────────
    op.drop_index("ix_conduct_api_keys_workspace_id", table_name="conduct_api_keys")
    op.execute("ALTER TABLE conduct_api_keys ALTER COLUMN workspace_id TYPE VARCHAR(36) USING workspace_id::text")
    op.create_index("ix_conduct_api_keys_workspace_id", "conduct_api_keys", ["workspace_id"])

    # ── security_findings ─────────────────────────────────────────────────────
    op.drop_index("ix_security_findings_workspace_id", table_name="security_findings")
    op.drop_index("ix_security_findings_status", table_name="security_findings")
    op.execute("ALTER TABLE security_findings ALTER COLUMN workspace_id TYPE VARCHAR USING workspace_id::text")
    op.create_index("ix_security_findings_workspace_id", "security_findings", ["workspace_id"])
    op.create_index("ix_security_findings_status", "security_findings", ["workspace_id", "status"])

    # ── watchdog_events ───────────────────────────────────────────────────────
    op.drop_index("ix_watchdog_events_workspace_id", table_name="watchdog_events")
    op.execute("ALTER TABLE watchdog_events ALTER COLUMN workspace_id TYPE VARCHAR(255) USING workspace_id::text")
    op.create_index("ix_watchdog_events_workspace_id", "watchdog_events", ["workspace_id"])

    # ── audit_log ─────────────────────────────────────────────────────────────
    op.drop_index("ix_audit_log_workspace_created", table_name="audit_log")
    op.drop_index("ix_audit_log_workspace_action", table_name="audit_log")
    op.execute("ALTER TABLE audit_log ALTER COLUMN workspace_id TYPE VARCHAR(255) USING workspace_id::text")
    op.create_index("ix_audit_log_workspace_created", "audit_log", ["workspace_id", "created_at"])
    op.create_index("ix_audit_log_workspace_action", "audit_log", ["workspace_id", "action"])
