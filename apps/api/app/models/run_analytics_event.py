"""
RunAnalyticsEvent — structured, PII-free outcome record written at the end of
every agent run (success or failure). Feeds the benchmark, eval harness, and
cross-tenant analytics dashboards.

Distinct from RunEvent (per-block trace log). RunAnalyticsEvent is one row per
run; RunEvent is many rows per run.
"""
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class RunAnalyticsEvent(Base):
    """One row per completed (or failed) agent run — analytics only, no PII."""

    __tablename__ = "run_analytics_events"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id          = Column(UUID(as_uuid=True), nullable=False)
    workspace_id    = Column(String(16), nullable=False)   # sha256[:16] — hashed, never raw
    playbook_slug   = Column(String(255), nullable=False)
    model           = Column(String(255), nullable=False)
    trigger_type    = Column(String(50), nullable=False)   # webhook | cron | manual
    blocks_executed = Column(Integer, nullable=False, default=0)
    tool_calls      = Column(Integer, nullable=False, default=0)
    input_tokens    = Column(Integer, nullable=False, default=0)
    output_tokens   = Column(Integer, nullable=False, default=0)
    duration_ms     = Column(Integer, nullable=True)
    outcome         = Column(String(50), nullable=False)   # succeeded | failed
    human_verdict   = Column(String(50), nullable=True)    # approved | rejected | null
    cost_usd        = Column(Numeric(10, 6), nullable=True)
    error           = Column(Text, nullable=True)
    created_at      = Column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
