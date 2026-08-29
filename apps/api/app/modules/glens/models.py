import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.core.database import Base


class GlensChatSession(Base):
    __tablename__ = "glens_chat_sessions"

    id           = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE", name="glens_chat_sessions_workspace_id_fkey"),
        nullable=False,
        index=True,
    )
    title        = Column(String, nullable=False)
    messages     = Column(Text, nullable=False, default="[]")
    context_summary = Column(Text, nullable=True)
    # Session-scoped token — SHA-256 of the raw cond_lens_* token.
    # #1218 Step 3b — Guard-enforced Lens with per-session blast-radius.
    token_hash       = Column(String(64), nullable=True, index=True)
    token_revoked_at = Column(DateTime(timezone=True), nullable=True)
    # Session-scoped AgentIdentity minted at session start (migration 0090).
    # Threaded through guarded_llm_call/stream so SpendCap + ThroughputCap
    # apply to Lens usage.
    agent_identity_id = Column(String(36), nullable=True)
    created_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_glens_chat_sessions_updated_at", "updated_at"),
    )


class GlensChatFeedback(Base):
    """Per-message thumbs up/down feedback for Lens chat responses.

    Aggregated to feed the LLM tuning / prompt regression loop — every
    response gets a data point of "did this actually help?". One row per
    (session, message, user); latest verdict wins on upsert.
    """
    __tablename__ = "glens_chat_feedback"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE", name="glens_chat_feedback_workspace_id_fkey"),
        nullable=False,
    )
    session_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("glens_chat_sessions.id", ondelete="CASCADE", name="glens_chat_feedback_session_id_fkey"),
        nullable=False,
    )
    # Position of the assistant message within GlensChatSession.messages —
    # kept as a plain string so we can accept UUIDs later without a schema
    # change. Today it's the array index or a client-supplied stable id.
    message_id = Column(String(64), nullable=False)
    verdict = Column(String(4), nullable=False)                   # "up" | "down"
    comment = Column(Text, nullable=True)                          # optional freeform (mostly on downs)
    clerk_user_id = Column(Text, nullable=True)                    # who left the feedback
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

    __table_args__ = (
        # One feedback per (session, message, user) — verdict can be updated (upsert).
        UniqueConstraint(
            "session_id", "message_id", "clerk_user_id",
            name="uq_glens_chat_feedback_session_msg_user",
        ),
        # Fast per-workspace analytics rollups.
        Index(
            "ix_glens_chat_feedback_workspace_created",
            "workspace_id", "created_at",
        ),
        CheckConstraint(
            "verdict IN ('up', 'down')",
            name="ck_glens_chat_feedback_verdict",
        ),
    )
