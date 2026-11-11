"""Caller-reported tool executions joined to gateway audit rows by correlation id (#2169)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class GuardToolExecution(Base):
    __tablename__ = "guard_tool_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE", name="fk_guard_tool_executions_workspace_id"),
        nullable=False,
    )
    # 16 hex chars assigned by the gateway (tool_call_correlation_ids).
    correlation_id = Column(String(32), nullable=False)
    tool_use_id = Column(Text, nullable=True)
    tool_name = Column(String(255), nullable=True)
    hook_session_id = Column(Text, nullable=True)
    clerk_user_id = Column(Text, nullable=True)
    execution_status = Column(String(20), nullable=True)  # success | error | timeout
    duration_ms = Column(Integer, nullable=True)
    # 'reported' = caller sent the id; 'resolved' = API matched tool_use_id to the gateway row.
    correlation_source = Column(String(20), nullable=False, default="reported")
    ts = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "correlation_id", name="uq_guard_tool_executions_ws_corr"),
    )
