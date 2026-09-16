"""#2012 — Lens actor: revert a Gateway Profile v2 to a historical revision.

Two-step; confirm delegates to the router's `rollback_profile` which
already enforces revision-belongs-to-profile and updates
`active_revision_id` + the working_copy to match the rolled-back
revision.

v3 schema (#2007 follow-up): no environment picker. Rollback repoints
the single `active_revision_id` on the profile row.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.modules.glens.actor.registry import default_action_registry
from app.modules.glens.actor.types import ActionCtx, ActionSpec, ProposeResult


def _propose(ctx: ActionCtx, args: dict[str, Any]) -> ProposeResult:
    profile_id_raw = str(args.get("profile_id") or "").strip()
    revision_id_raw = str(args.get("revision_id") or "").strip()
    if not (profile_id_raw and revision_id_raw):
        return ProposeResult(
            rejected=True,
            reason="profile_id and revision_id are required",
            summary="", resolved_input={},
        )
    try:
        profile_uuid = UUID(profile_id_raw)
        rev_uuid = UUID(revision_id_raw)
    except ValueError:
        return ProposeResult(
            rejected=True,
            reason="profile_id and revision_id must be UUIDs",
            summary="", resolved_input={},
        )

    from app.models.gateway_profile import (
        GatewayProfile as _Row,
        GatewayProfileRevision as _Revision,
    )

    profile = ctx.db.query(_Row).filter(
        _Row.id == profile_uuid,
        _Row.workspace_id == ctx.workspace_id,
    ).first()
    if profile is None:
        return ProposeResult(rejected=True,
                             reason=f"Profile {profile_id_raw!r} not found",
                             summary="", resolved_input={})

    revision = ctx.db.query(_Revision).filter(
        _Revision.id == rev_uuid,
        _Revision.profile_id == profile_uuid,
    ).first()
    if revision is None:
        return ProposeResult(
            rejected=True,
            reason=f"Revision {revision_id_raw!r} does not belong to profile {profile.name!r}",
            summary="", resolved_input={},
        )

    summary = (
        f"Revert {profile.name!r} to revision v{revision.version} "
        f"(published by {revision.published_by})"
    )
    return ProposeResult(
        summary=summary,
        resolved_input={
            "profile_id": str(profile_uuid),
            "revision_id": str(rev_uuid),
        },
    )


def _execute(ctx: ActionCtx, resolved: dict[str, Any]) -> dict[str, Any]:
    from app.routers.gateway_profiles_v2 import (
        RollbackBody,
        rollback_profile as _http_rollback,
    )

    profile = _http_rollback(
        workspace_id=ctx.workspace_id,
        profile_id=UUID(resolved["profile_id"]),
        body=RollbackBody(revision_id=UUID(resolved["revision_id"])),
        db=ctx.db,
        _ws=ctx.workspace_id,
        caller=ctx.user_email or ctx.clerk_user_id or "lens",
    )
    return {
        "id": str(profile.id),
        "name": profile.name,
        "cond_code": profile.cond_code,
        "active_revision_id": str(profile.active_revision_id) if profile.active_revision_id else None,
    }


default_action_registry.register(ActionSpec(
    name="gateway_v2_rollback",
    guard_permission="platform.credentials.manage",
    propose=_propose,
    execute=_execute,
    description=(
        "Revert a Gateway Profile v2 to a historical revision. Two-step: "
        "returns a pending action for the user to confirm; the confirm "
        "click sets ``active_revision_id`` to the chosen revision and "
        "refreshes the working_copy to match. Working_copy stays locked "
        "after — duplicate to make changes."
    ),
))
