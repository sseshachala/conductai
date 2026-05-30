import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, CheckConstraint, event
from sqlalchemy.orm import validates
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base

WATCHDOG_EVENT_TYPES = (
    "stale_worker",
    "approval_timeout",
    "repeated_failure",
    "credential_expiry",
    "queue_backup",
    "silent_playbook",
    "unknown",
)


def normalize_event_type(event_type: str) -> str:
    """Return event_type if known, else 'unknown'. Prevents DB constraint violations."""
    return event_type if event_type in WATCHDOG_EVENT_TYPES else "unknown"

WATCHDOG_SEVERITIES = ("info", "warning", "error")


class WatchdogEvent(Base):
    __tablename__ = "watchdog_events"
    __table_args__ = (
        CheckConstraint(
            f"event_type IN ({', '.join(repr(t) for t in WATCHDOG_EVENT_TYPES)})",
            name="ck_watchdog_events_event_type",
        ),
        CheckConstraint(
            f"severity IN ({', '.join(repr(s) for s in WATCHDOG_SEVERITIES)})",
            name="ck_watchdog_events_severity",
        ),
    )

    @validates("event_type")
    def _validate_event_type(self, key, value):
        return normalize_event_type(value)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(String(255), nullable=False)
    run_id = Column(UUID(as_uuid=True), nullable=True)
    workflow_id = Column(UUID(as_uuid=True), nullable=True)
    event_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False, default="warning")
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime(timezone=True), nullable=True)
