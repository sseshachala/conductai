"""Workspace-scoped LLM Model Primitives — see #1347.

One row per workspace. Holds routing config (preferred_provider + tier_map)
consumed by all LLM callers (workflows, Lens, Guard). API keys stay in
Vault (Environment); this table is config-only.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class WorkspaceLLMPrimitives(Base):
    __tablename__ = "workspace_llm_primitives"

    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    preferred_provider = Column(String(50), nullable=False, default="anthropic")
    # tier_map: {"cheap": "haiku-...", "balanced": "sonnet-...", "smart": "opus-..."}
    tier_map = Column(JSONB, nullable=False, default=dict)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
