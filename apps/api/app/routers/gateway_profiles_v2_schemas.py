"""Request / response DTOs for the Gateway Profile v2 router (split from gateway_profiles_v2.py).
"""
from __future__ import annotations
from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


# ─── Request / response DTOs ──────────────────────────────────────────


class CreateProfileBody(BaseModel):
    """Minimum shape for creating a draft — name + initial working_copy."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    working_copy: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Initial GatewayProfileV2 shape. Empty dict = truly empty draft "
            "(admin will fill it via PUT before publishing)."
        ),
    )


class UpdateWorkingCopyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    working_copy: dict[str, Any] = Field(
        description="Full GatewayProfileV2 shape. Partial updates not supported."
    )


class PublishBody(BaseModel):
    """Publish takes no arguments — it snapshots the working_copy and
    points ``active_revision_id`` at the new revision. Env selection is
    gone from the profile abstraction; vault refs live inside targets."""

    model_config = ConfigDict(extra="forbid")


class RollbackBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_id: UUID = Field(
        description=(
            "The historical revision to revert to. Must belong to the same "
            "profile — cross-profile rollback is a security bug, not a feature."
        )
    )


class ImportProfileBody(BaseModel):
    """Import a profile from a portable JSON payload.

    ``working_copy`` is the same shape the editor's Save posts, i.e. a
    ``GatewayProfileV2`` dict. The server ALWAYS strips
    ``credential_ref`` from every target on import (defense against
    accidentally-committed vault refs in checked-in JSON, and to keep
    exports portable across workspaces + environments).

    ``name_override`` lets the caller land the imported profile under
    a different name than what's in the JSON's ``name`` field — useful
    when the source profile's name is already taken in the target
    workspace. When absent, the JSON's ``name`` wins (or falls back
    to ``imported-profile`` if the JSON has no name).
    """
    model_config = ConfigDict(extra="forbid")

    working_copy: dict[str, Any] = Field(
        description="Portable GatewayProfileV2 shape. credential_ref values are stripped on import."
    )
    name_override: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="Optional profile name for the imported draft (else use working_copy.name).",
    )


class ImportGap(BaseModel):
    """One target that needs credentials filled before publish."""
    target_index: int
    target_id: str
    transport: str
    reason: str


class ImportProfileOut(BaseModel):
    """Result of an import — created profile + gaps + a link the
    caller can open to finish setup."""
    profile: "ProfileOut"
    credential_gaps: list[ImportGap]
    next_url: str = Field(
        description="Absolute URL to the editor page for the created profile."
    )


class RevisionOut(BaseModel):
    id: UUID
    version: int
    published_by: str
    published_at: datetime
    # snapshot deliberately omitted from the list view — one revision can be
    # ~2KB of JSON and workspaces will accumulate many. Fetch via the
    # dedicated snapshot endpoint if the UI needs a diff.


class ProfileOut(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    model_alias: str | None
    cond_code: str
    active_revision_id: UUID | None
    working_copy: dict[str, Any] | None
    revisions: list[RevisionOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProfileRateCap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rpm: int | None = Field(default=None, strict=True, gt=0, le=2147483647)
    tpm: int | None = Field(default=None, strict=True, gt=0, le=2147483647)


class ProfileAgentRateCap(ProfileRateCap):
    agent_identity_id: UUID


class ProfileRateLimitsBody(ProfileRateCap):
    agent_limits: list[ProfileAgentRateCap] | None = Field(default=None, max_length=200)


class ProfileRateLimitsOut(ProfileRateCap):
    agent_limits: list[ProfileAgentRateCap] = Field(default_factory=list)
    available_agents: list[dict[str, str]] = Field(default_factory=list)


# Resolve the forward reference on ``ImportProfileOut.profile`` (which
# is typed as ``"ProfileOut"`` because ``ProfileOut`` is defined below
# ``ImportProfileOut``).
ImportProfileOut.model_rebuild()
