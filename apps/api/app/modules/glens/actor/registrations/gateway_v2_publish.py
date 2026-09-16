"""#2012 — Lens actor: publish a Gateway Profile v2 draft.

Two-step; confirm fires the router's `publish_profile` endpoint, which
runs the full publish lifecycle: schema validation, capability catalog
check, env/credential ownership checks, revision insert with retry, and
binding upsert with row-lock. Any of those failing surfaces the exact
same detail message the API returns on a direct POST.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.modules.glens.actor.registry import default_action_registry
from app.modules.glens.actor.types import ActionCtx, ActionSpec, ProposeResult


def _propose(ctx: ActionCtx, args: dict[str, Any]) -> ProposeResult:
    profile_id_raw = str(args.get("profile_id") or "").strip()
    env_id_raw = str(args.get("environment_id") or "").strip()
    if not profile_id_raw:
        return ProposeResult(rejected=True, reason="profile_id required",
                             summary="", resolved_input={})
    if not env_id_raw:
        return ProposeResult(rejected=True, reason="environment_id required",
                             summary="", resolved_input={})
    try:
        profile_uuid = UUID(profile_id_raw)
        env_uuid = UUID(env_id_raw)
    except ValueError:
        return ProposeResult(rejected=True,
                             reason="profile_id and environment_id must be UUIDs",
                             summary="", resolved_input={})

    from app.models.environment import Environment
    from app.models.gateway_profile import (
        GatewayProfile as _Row,
        GatewayProfileBinding as _Binding,
    )

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

    env = ctx.db.query(Environment).filter(
        Environment.id == env_uuid,
        Environment.workspace_id == ctx.workspace_id,
    ).first()
    if env is None:
        return ProposeResult(
            rejected=True,
            reason=f"Environment {env_id_raw!r} does not belong to this workspace",
            summary="", resolved_input={},
        )

    alias = profile.working_copy.get("model_alias") if isinstance(profile.working_copy, dict) else None
    existing = ctx.db.query(_Binding).filter(
        _Binding.workspace_id == ctx.workspace_id,
        _Binding.environment_id == env_uuid,
        _Binding.model_alias == alias,
    ).first() if alias else None
    prior_note = " (replaces the current binding)" if existing else " (first publish for this env × alias)"
    summary = (
        f"Publish profile {profile.name!r} to {env.name} "
        f"for alias {alias!r}{prior_note}"
    )
    return ProposeResult(
        summary=summary,
        resolved_input={
            "profile_id": str(profile.id),
            "environment_id": str(env_uuid),
        },
    )


def _execute(ctx: ActionCtx, resolved: dict[str, Any]) -> dict[str, Any]:
    from app.routers.gateway_profiles_v2 import (
        PublishBody,
        publish_profile as _http_publish,
    )

    body = PublishBody(environment_id=UUID(resolved["environment_id"]))
    profile = _http_publish(
        workspace_id=ctx.workspace_id,
        profile_id=UUID(resolved["profile_id"]),
        body=body, db=ctx.db,
        _ws=ctx.workspace_id,
        caller=ctx.user_email or ctx.clerk_user_id or "lens",
    )
    return {
        "id": str(profile.id),
        "name": profile.name,
        "model_alias": profile.model_alias,
        "revisions": len(profile.revisions),
        "bindings": [
            {
                "environment_id": str(b.environment_id),
                "model_alias": b.model_alias,
                "revision_id": str(b.revision_id),
            }
            for b in profile.bindings
        ],
    }


default_action_registry.register(ActionSpec(
    name="gateway_v2_publish",
    guard_permission="platform.credentials.manage",
    propose=_propose,
    execute=_execute,
    description=(
        "Publish a Gateway Profile v2 draft as a new revision and pin it "
        "to an environment × alias binding. Two-step: returns a pending "
        "action for the user to confirm; the confirm click runs the full "
        "publish lifecycle (schema validation, capability catalog check, "
        "credential + environment ownership check)."
    ),
))
