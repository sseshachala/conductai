"""fix watchdog_events check constraint to include queue_backup and silent_playbook

Revision ID: 0071
Revises: 0070
"""
from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None

_VALID_TYPES = (
    "stale_worker",
    "approval_timeout",
    "repeated_failure",
    "credential_expiry",
    "queue_backup",
    "silent_playbook",
    "unknown",
)


def upgrade():
    op.drop_constraint("ck_watchdog_events_event_type", "watchdog_events", type_="check")
    op.create_check_constraint(
        "ck_watchdog_events_event_type",
        "watchdog_events",
        f"event_type IN ({', '.join(repr(t) for t in _VALID_TYPES)})",
    )


def downgrade():
    op.drop_constraint("ck_watchdog_events_event_type", "watchdog_events", type_="check")
    _old = ("stale_worker", "approval_timeout", "repeated_failure", "credential_expiry", "unknown")
    op.create_check_constraint(
        "ck_watchdog_events_event_type",
        "watchdog_events",
        f"event_type IN ({', '.join(repr(t) for t in _old)})",
    )
