"""Persisted canonical gateway profiles (v3 schema — #2007 follow-up).

Two ORM classes live here:

- ``GatewayProfile`` — the mutable profile row. Draft edits live on
  ``working_copy``. ``active_revision_id`` names the currently-serving
  revision (NULL means no live config yet). ``cond_code`` is the
  server-generated public identifier — every profile gets one at create
  time and it never changes; forms the client-facing routing key
  ``cond-<code>-<alias>``.
- ``GatewayProfileRevision`` — immutable snapshots, one row per publish.
  Nothing UPDATEs or DELETEs these from application code — rollback
  points ``active_revision_id`` at an earlier revision instead.

Environment no longer appears at the profile level. Vault refs
(``vault://<env_id>/<handle>``) live inside each target's
``credential_ref`` field in the working_copy / snapshot; the gateway
resolves those at request time.
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
    # environment_id stays on the ORM for v1 backwards compat only; v2/v3
    # profiles ignore it. Not part of the client-facing contract.
    environment_id = Column(UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(128), nullable=False)
    schema_version = Column(String(16), nullable=False, default="1")
    config = Column(JSONB, nullable=False, default=dict)

    # v2 (#2001) additions — nullable during rollout. v2 publish enforces
    # non-null model_alias; v1 rows keep both empty.
    working_copy = Column(JSONB, nullable=True)
    model_alias = Column(String(128), nullable=True)

    # v3 (#2007 follow-up) additions:
    # - cond_code is the server-generated public identifier. Immutable
    #   after create. Unique per workspace.
    # - active_revision_id names the revision the gateway serves. NULL
    #   for drafts. Rollback re-points this; publish sets it.
    cond_code = Column(String(32), nullable=False)
    active_revision_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "gateway_profile_revisions.id",
            ondelete="RESTRICT",
            name="fk_gateway_profiles_active_revision",
        ),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("workspace_id", "environment_id", "name", name="uq_gateway_profiles_workspace_env_name"),
        UniqueConstraint("workspace_id", "cond_code", name="uq_gateway_profiles_workspace_cond_code"),
        Index("ix_gateway_profiles_workspace_id", "workspace_id"),
        Index("ix_gateway_profiles_workspace_environment", "workspace_id", "environment_id"),
        Index("ix_gateway_profiles_model_alias", "workspace_id", "environment_id", "model_alias"),
        Index("ix_gateway_profiles_active_revision", "active_revision_id"),
    )


class GatewayProfileRevision(Base):
    """Immutable publish snapshot.

    One row per publish. Nothing UPDATEs or DELETEs these from application
    code — rollback re-points the owning profile's ``active_revision_id``
    at an earlier revision.
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
