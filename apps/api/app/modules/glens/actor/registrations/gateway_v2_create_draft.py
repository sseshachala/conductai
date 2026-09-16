"""#2012 — Lens actor: create a draft Gateway Profile v2.

Two-step (per the actor substrate contract):
- `propose` validates the name isn't empty and doesn't collide with an
  existing profile in the workspace, then returns the confirm summary.
- `execute` delegates to the HTTP router's `create_profile` — same
  code path a POST /gateway-profiles-v2 request runs through — so the
  Lens surface can't drift from the API's validation rules.

The working_copy argument is optional; if omitted the draft is empty
and the admin can fill it via a follow-up `gateway_v2_update_working_copy`
tool call (also on the actor substrate).
"""
from __future__ import annotations

from typing import Any

from app.modules.glens.actor.registry import default_action_registry
from app.modules.glens.actor.types import ActionCtx, ActionSpec, ProposeResult


def _propose(ctx: ActionCtx, args: dict[str, Any]) -> ProposeResult:
    name = str(args.get("name") or "").strip()
    if not name:
        return ProposeResult(rejected=True, reason="name required",
                             summary="", resolved_input={})

    working_copy = args.get("working_copy") or {}
    if not isinstance(working_copy, dict):
        return ProposeResult(rejected=True,
                             reason="working_copy must be a JSON object",
                             summary="", resolved_input={})

    # Collision check — matches the DB constraint the router enforces so
    # the user sees the failure at propose time, not confirm time.
    from app.models.gateway_profile import GatewayProfile as _Row
    existing = ctx.db.query(_Row).filter(
        _Row.workspace_id == ctx.workspace_id,
        _Row.name == name,
    ).first()
    if existing is not None:
        return ProposeResult(
            rejected=True,
            reason=f"A profile named {name!r} already exists in this workspace.",
            summary="", resolved_input={},
        )

    alias = working_copy.get("model_alias")
    summary = (
        f"Create draft Gateway Profile v2 named {name!r}"
        + (f" for alias {alias!r}" if alias else " (empty working copy)")
    )
    return ProposeResult(
        summary=summary,
        resolved_input={"name": name, "working_copy": working_copy or None},
    )


def _execute(ctx: ActionCtx, resolved: dict[str, Any]) -> dict[str, Any]:
    from app.routers.gateway_profiles_v2 import (
        CreateProfileBody,
        create_profile as _http_create,
    )

    body = CreateProfileBody(
        name=resolved["name"],
        working_copy=resolved.get("working_copy") or {},
    )
    profile = _http_create(
        workspace_id=ctx.workspace_id, body=body, db=ctx.db,
        _ws=ctx.workspace_id, _=ctx.user_email or ctx.clerk_user_id or "lens",
    )
    return {
        "id": str(profile.id),
        "name": profile.name,
        "model_alias": profile.model_alias,
    }


default_action_registry.register(ActionSpec(
    name="gateway_v2_create_draft",
    guard_permission="platform.credentials.manage",
    propose=_propose,
    execute=_execute,
    description=(
        "Create a draft Gateway Profile v2. Two-step: returns a pending "
        "action for the user to confirm; the confirm click writes the row."
    ),
))
