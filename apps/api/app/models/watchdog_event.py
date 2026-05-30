import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class WatchdogEvent(Base):
    __tablename__ = "watchdog_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(String(255), nullable=False)
    run_id = Column(UUID(as_uuid=True), nullable=True)
    workflow_id = Column(UUID(as_uuid=True), nullable=True)
    # stale_worker | approval_timeout | run_failed | run_recovered
    event_type = Column(String(50), nullable=False)
    # info | warning | error
    severity = Column(String(20), nullable=False, default="info")
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
