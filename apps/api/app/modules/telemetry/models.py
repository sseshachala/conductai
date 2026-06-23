"""SQLAlchemy model for telemetry_events (#718 Phase 1)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.types import TIMESTAMP

from app.core.database import Base


class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id  = Column(UUID(as_uuid=True), nullable=True)
    run_id        = Column(UUID(as_uuid=True), nullable=True)
    tool          = Column(Text, nullable=False)
    version       = Column(Text, nullable=False)
    event_type    = Column(Text, nullable=False)
    message       = Column(Text, nullable=False)
    traceback     = Column(Text, nullable=True)
    session_id    = Column(Text, nullable=True)
    context       = Column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    ts = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('info','warning','error')",
            name="telemetry_events_event_type_chk",
        ),
        CheckConstraint(
            "tool IN ('conduct-cli','agent-booster')",
            name="telemetry_events_tool_chk",
        ),
        Index("ix_telemetry_ws_type_ts",  "workspace_id", "event_type", text("ts DESC")),
        Index("ix_telemetry_ws_run",      "workspace_id", "run_id"),
        Index("ix_telemetry_session",     "workspace_id", "session_id"),
    )
