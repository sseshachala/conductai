import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, String, Integer, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class PlaybookSubmission(Base):
    """
    Tracks eval scores and promotion status for each playbook.

    Populated by the eval promotion loop (eval/promotion.py).  One row per
    playbook per eval run; upserted so re-runs overwrite stale data.
    """
    __tablename__ = "playbook_submissions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    slug = Column(String(255), nullable=False)
    source = Column(String(50), nullable=False, default="builtin")   # builtin | community
    structural_score = Column(Integer, nullable=False, default=0)
    quality_score = Column(Integer, nullable=False, default=0)
    grade = Column(String(5), nullable=False)                        # A/B/C/D/F
    status = Column(
        String(50), nullable=False, default="pending",
    )                                                                 # pending | promoted | needs_work
    criteria_json = Column(Text, nullable=True)                      # JSON blob of full criteria list
    eval_run_at = Column(DateTime(timezone=True), nullable=False)
    promoted_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
