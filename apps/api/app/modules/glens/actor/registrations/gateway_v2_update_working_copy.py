"""#2012 — Lens actor: overwrite a Gateway Profile v2's working copy.

Two-step; the write path is the router's `update_working_copy` endpoint
so the schema-validation error message the caller sees is the same one
the API surfaces on a direct PUT.

The whole working_copy is replaced — partial updates aren't supported
(the API doesn't support them either; keeps the "one revision, one full
snapshot" invariant clean). If the caller wants to edit a single field,
they should call `get_gateway_v2_profile` first, mutate the returned
JSON, and pass the whole thing.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.modules.glens.actor.registry import default_action_registry
from app.modules.glens.actor.types import ActionCtx, ActionSpec, ProposeResult


def _propose(ctx: ActionCtx, args: dict[str, Any]) -> ProposeResult:
    profile_id_raw = str(args.get("profile_id") or "").strip()
    if not profile_id_raw:
        return ProposeResult(rejected=True, reason="profile_id required",
                             summary="", resolved_input={})
    try:
        profile_uuid = UUID(profile_id_raw)
    except ValueError:
        return ProposeResult(rejected=True,
                             reason=f"{profile_id_raw!r} is not a valid UUID",
                             summary="", resolved_input={})

    working_copy = args.get("working_copy")
    if not isinstance(working_copy, dict) or not working_copy:
        return ProposeResult(rejected=True,
                             reason="working_copy must be a non-empty JSON object",
                             summary="", resolved_input={})

    from app.models.gateway_profile import GatewayProfile as _Row
    profile = ctx.db.query(_Row).filter(
        _Row.id == profile_uuid,
        _Row.workspace_id == ctx.workspace_id,
    ).first()
    if profile is None:
        return ProposeResult(rejected=True,
                             reason=f"Profile {profile_id_raw!r} not found",
                             summary="", resolved_input={})

    alias = working_copy.get("model_alias")
    targets = working_copy.get("targets") or []
    summary = (
        f"Overwrite working copy of {profile.name!r} — "
        f"alias {alias!r}, {len(targets)} target(s)"
    )
    return ProposeResult(
        summary=summary,
        resolved_input={
            "profile_id": str(profile.id),
            "working_copy": working_copy,
        },
    )


def _execute(ctx: ActionCtx, resolved: dict[str, Any]) -> dict[str, Any]:
    from app.routers.gateway_profiles_v2 import (
        UpdateWorkingCopyBody,
        update_working_copy as _http_update,
    )

    body = UpdateWorkingCopyBody(working_copy=resolved["working_copy"])
    profile = _http_update(
        workspace_id=ctx.workspace_id,
        profile_id=UUID(resolved["profile_id"]),
        body=body, db=ctx.db,
        _ws=ctx.workspace_id, _=ctx.user_email or ctx.clerk_user_id or "lens",
    )
    return {
        "id": str(profile.id),
        "name": profile.name,
        "model_alias": profile.model_alias,
    }


default_action_registry.register(ActionSpec(
    name="gateway_v2_update_working_copy",
    guard_permission="platform.credentials.manage",
    propose=_propose,
    execute=_execute,
    description=(
        "Overwrite the working copy of a Gateway Profile v2 draft. "
        "Two-step: returns a pending action for the user to confirm; "
        "the confirm click writes the new working_copy."
    ),
))
