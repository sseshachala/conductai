import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class RunOnlineScore(Base):
    """One quality score row per completed production run."""

    __tablename__ = "run_online_scores"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id           = Column(UUID(as_uuid=True), nullable=False, index=True, unique=True)
    workflow_id      = Column(UUID(as_uuid=True), nullable=True)
    slug             = Column(String(255), nullable=False, index=True)
    grade            = Column(String(5), nullable=False)
    pct              = Column(Numeric(5, 2), nullable=False)
    mechanical_score = Column(Integer, nullable=False, default=0)
    mechanical_max   = Column(Integer, nullable=False, default=40)
    judge_score      = Column(Integer, nullable=False, default=0)
    judge_max        = Column(Integer, nullable=False, default=0)
    judge_used       = Column(Boolean, nullable=False, default=False)
    run_status       = Column(String(50), nullable=True)
    outcome_type     = Column(String(255), nullable=True)
    token_count      = Column(Integer, nullable=True)
    anonymized_outcome = Column(JSONB, nullable=True)
    scored_at        = Column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class RunFixtureCandidate(Base):
    """Low-scoring production run queued for fixture promotion."""

    __tablename__ = "run_fixture_candidates"

    id                    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id                = Column(UUID(as_uuid=True), nullable=False, index=True, unique=True)
    slug                  = Column(String(255), nullable=False, index=True)
    grade                 = Column(String(5), nullable=False)
    pct                   = Column(Numeric(5, 2), nullable=False)
    anon_trigger_payload  = Column(JSONB, nullable=True)
    anon_state            = Column(JSONB, nullable=True)
    expected_outcome_type = Column(String(255), nullable=True)
    status                = Column(String(50), nullable=False, default="pending", index=True)
    promoted_pr_url       = Column(String, nullable=True)
    promoted_by           = Column(String(255), nullable=True)
    created_at            = Column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    promoted_at = Column(sa.DateTime(timezone=True), nullable=True)
