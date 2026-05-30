"""add check constraints for watchdog_events event_type and severity

Revision ID: 0033
Revises: 0032
"""
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

_VALID_TYPES = (
    "stale_worker",
    "approval_timeout",
    "repeated_failure",
    "credential_expiry",
    "queue_backup",
    "silent_playbook",
)
_VALID_SEVERITIES = ("info", "warning", "error")


def upgrade():
    op.create_check_constraint(
        "ck_watchdog_events_event_type",
        "watchdog_events",
        f"event_type IN ({', '.join(repr(t) for t in _VALID_TYPES)})",
    )
    op.create_check_constraint(
        "ck_watchdog_events_severity",
        "watchdog_events",
        f"severity IN ({', '.join(repr(s) for s in _VALID_SEVERITIES)})",
    )


def downgrade():
    op.drop_constraint("ck_watchdog_events_event_type", "watchdog_events")
    op.drop_constraint("ck_watchdog_events_severity", "watchdog_events")
