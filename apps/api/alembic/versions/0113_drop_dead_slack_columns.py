"""Drop dead Slack columns from guard_config + security_config (#1574 follow-up).

Cleanup pass after PR #1575 shipped the drift alerter on the per-action fanout
table. Three columns exist on ORM models and DB tables but no code path reads
them:

1. ``guard_config.slack_integration_id`` — accepted in the token_guardrails
   PATCH body and echoed back in the GET response, but no UI component
   renders or sets it, and the drift fanout switched to
   ``resolve_channels("drift")`` in #1575. The alert_slack_integration_id
   sibling (used by the settings page Slack card) is untouched.

2. ``security_config.slack_webhook_url`` — the only reader of the
   security_config table (``_load_security_config_defaults`` in
   app/routers/security.py) selects three columns, and this isn't one of
   them. Never referenced elsewhere.

3. ``security_config.slack_integration_id`` — same story as #2.

Revision ID: 0113
Revises: 0112
Create Date: 2026-09-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "0113"
down_revision = "0112"
branch_labels = None
depends_on = None


_DEAD_COLUMNS = (
    ("guard_config", "slack_integration_id"),
    ("security_config", "slack_webhook_url"),
    ("security_config", "slack_integration_id"),
)


def upgrade() -> None:
    # Log a NOTICE for any workspace that happens to have a non-null value in
    # a column we're dropping, so operators can see who was writing to a
    # field nothing read. Same pattern as migration 0112.
    for table, col in _DEAD_COLUMNS:
        op.execute(
            f"DO $$ BEGIN "
            f"IF EXISTS (SELECT 1 FROM {table} WHERE {col} IS NOT NULL) THEN "
            f"RAISE NOTICE 'Dropping {table}.{col} with % non-null rows (never read by any code path)', "
            f"(SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL); "
            f"END IF; END $$;"
        )
        op.drop_column(table, col)


def downgrade() -> None:
    op.add_column(
        "security_config",
        sa.Column("slack_integration_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "security_config",
        sa.Column("slack_webhook_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "guard_config",
        sa.Column("slack_integration_id", UUID(as_uuid=True), nullable=True),
    )
