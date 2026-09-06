"""Workspace-scoped report-builder layouts — see #1450.

One row per (workspace, slug) — every workspace member with view perm
sees every row (shared by default, not per-user). `layout_spec` is an
ordered list of `{tool_name, hint}` widget entries; the frontend maps
`hint` to a render cell size.

Templates ("Operations", "Observability") live in code, not here — a
"use template" click copies the template widget list into a new row.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class WorkspaceReportLayout(Base):
    __tablename__ = "workspace_report_layouts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug = Column(String(64), nullable=False)
    name = Column(Text, nullable=False)
    layout_spec = Column(JSONB, nullable=False, default=list)
    created_by = Column(String(255), nullable=False)  # clerk_user_id
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
        UniqueConstraint(
            "workspace_id", "slug",
            name="uq_workspace_report_layouts_ws_slug",
        ),
        Index(
            "ix_workspace_report_layouts_workspace_id",
            "workspace_id",
        ),
    )
