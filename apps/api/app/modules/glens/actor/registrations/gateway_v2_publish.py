"""#2012 — Lens actor: publish a Gateway Profile v2 draft.

Two-step; confirm fires the router's `publish_profile` endpoint, which
runs the full publish lifecycle: schema validation, capability catalog
check, credential ownership, revision insert, and activates the new
revision.

v3 schema (#2007 follow-up): environment is no longer part of publish.
Vault refs live inside each target's `credential_ref` in the working
copy. Publish just marks the current working_copy as the active
revision.
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

    from app.models.gateway_profile import GatewayProfile as _Row

    profile = ctx.db.query(_Row).filter(
        _Row.id == profile_uuid,
        _Row.workspace_id == ctx.workspace_id,
    ).first()
    if profile is None:
        return ProposeResult(rejected=True,
                             reason=f"Profile {profile_id_raw!r} not found",
                             summary="", resolved_input={})
    if not profile.working_copy:
        return ProposeResult(
            rejected=True,
            reason=(
                "Working copy is empty — populate it via "
                "gateway_v2_update_working_copy before publishing."
            ),
            summary="", resolved_input={},
        )
    if profile.active_revision_id is not None:
        return ProposeResult(
            rejected=True,
            reason=(
                "Profile is already published. To change it, duplicate "
                "into a new draft and publish that."
            ),
            summary="", resolved_input={},
        )

    alias = (
        profile.working_copy.get("model_alias")
        if isinstance(profile.working_copy, dict) else None
    )
    summary = (
        f"Publish profile {profile.name!r} — alias {alias!r} — "
        f"cond code {profile.cond_code}"
    )
    return ProposeResult(
        summary=summary,
        resolved_input={"profile_id": str(profile.id)},
    )


def _execute(ctx: ActionCtx, resolved: dict[str, Any]) -> dict[str, Any]:
    from app.routers.gateway_profiles_v2 import (
        PublishBody,
        publish_profile as _http_publish,
    )

    profile = _http_publish(
        workspace_id=ctx.workspace_id,
        profile_id=UUID(resolved["profile_id"]),
        body=PublishBody(),
        db=ctx.db,
        _ws=ctx.workspace_id,
        caller=ctx.user_email or ctx.clerk_user_id or "lens",
    )
    return {
        "id": str(profile.id),
        "name": profile.name,
        "cond_code": profile.cond_code,
        "active_revision_id": str(profile.active_revision_id) if profile.active_revision_id else None,
        "model_alias": profile.model_alias,
        "revisions": len(profile.revisions),
    }


default_action_registry.register(ActionSpec(
    name="gateway_v2_publish",
    guard_permission="platform.credentials.manage",
    propose=_propose,
    execute=_execute,
    description=(
        "Publish a Gateway Profile v2 draft as a new revision and set it "
        "as the profile's active revision. Two-step: returns a pending "
        "action for the user to confirm; the confirm click runs the full "
        "publish lifecycle (schema validation, capability catalog check, "
        "credential ownership check)."
    ),
))
