"""Persisted canonical gateway profiles.

Three ORM classes live here:

- ``GatewayProfile`` — the mutable profile row. Legacy ``config`` column
  stays populated for v1 workspaces; ``working_copy`` + ``model_alias``
  are the v2 additions (#2001).
- ``GatewayProfileRevision`` — immutable snapshots, one row per publish.
  Rollback creates a new binding pointing at an older revision, never
  UPDATEs an existing row.
- ``GatewayProfileBinding`` — explicit selection. The v2 resolver looks
  up ``(workspace_id, environment_id, model_alias)`` and follows to the
  revision. Zero alphabetical fallback.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class GatewayProfile(Base):
    __tablename__ = "gateway_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    environment_id = Column(UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(128), nullable=False)
    schema_version = Column(String(16), nullable=False, default="1")
    config = Column(JSONB, nullable=False, default=dict)
    # v2 (#2001) — nullable during rollout. v2 publish endpoint enforces
    # non-null model_alias; v1 rows keep both fields empty.
    working_copy = Column(JSONB, nullable=True)
    model_alias = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("workspace_id", "environment_id", "name", name="uq_gateway_profiles_workspace_env_name"),
        Index("ix_gateway_profiles_workspace_id", "workspace_id"),
        Index("ix_gateway_profiles_workspace_environment", "workspace_id", "environment_id"),
        Index("ix_gateway_profiles_model_alias", "workspace_id", "environment_id", "model_alias"),
    )


class GatewayProfileRevision(Base):
    """Immutable publish snapshot for #2001.

    One row per publish. Nothing UPDATEs or DELETEs these from application
    code — rollback is a fresh binding pointing at an older revision.
    """
    __tablename__ = "gateway_profile_revisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    version = Column(Integer, nullable=False)
    snapshot = Column(JSONB, nullable=False)
    published_by = Column(String(128), nullable=False)
    published_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "profile_id", "version",
            name="uq_gateway_profile_revisions_profile_version",
        ),
        Index("ix_gateway_profile_revisions_profile", "profile_id"),
    )


class GatewayProfileBinding(Base):
    """Explicit selection table for #2001 — no alphabetical fallback.

    Composite primary key on ``(workspace_id, environment_id, model_alias)``
    means each ``model:`` value the client can send resolves to exactly
    one revision per environment.
    """
    __tablename__ = "gateway_profile_bindings"

    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    environment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("environments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    model_alias = Column(String(128), primary_key=True)
    revision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_profile_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_gateway_profile_bindings_revision", "revision_id"),
    )
