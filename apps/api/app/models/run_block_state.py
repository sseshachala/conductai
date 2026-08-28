import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class RunBlockState(Base):
    """Atomic per-block checkpoint row.

    PRIMARY KEY is (run_id, block_id) so an upsert on conflict replaces
    the row in place — a single DB round-trip with no crash window.

    partial=True means the block is mid-execution (turn-level checkpoint).
    partial=False means the block completed; output holds the final result.
    """

    __tablename__ = "run_block_states"

    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    block_id = Column(String(255), primary_key=True, nullable=False)
    attempt_id = Column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    output = Column(JSONB, nullable=False, default=dict)
    partial = Column(Boolean, nullable=False, default=False)
    resume_from_turn = Column(Integer, nullable=False, default=0)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_run_block_states_run_id", "run_id"),
    )
