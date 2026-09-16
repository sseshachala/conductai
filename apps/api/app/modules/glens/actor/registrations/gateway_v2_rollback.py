"""#2012 — Lens actor: repoint a binding at a historical revision.

Two-step; confirm delegates to the router's `rollback_profile` which
already enforces revision-belongs-to-profile and env-belongs-to-workspace
and writes the append-only `gateway_profile_binding_events` audit row.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.modules.glens.actor.registry import default_action_registry
from app.modules.glens.actor.types import ActionCtx, ActionSpec, ProposeResult


def _propose(ctx: ActionCtx, args: dict[str, Any]) -> ProposeResult:
    profile_id_raw = str(args.get("profile_id") or "").strip()
    env_id_raw = str(args.get("environment_id") or "").strip()
    revision_id_raw = str(args.get("revision_id") or "").strip()
    if not (profile_id_raw and env_id_raw and revision_id_raw):
        return ProposeResult(
            rejected=True,
            reason="profile_id, environment_id, revision_id all required",
            summary="", resolved_input={},
        )
    try:
        profile_uuid = UUID(profile_id_raw)
        env_uuid = UUID(env_id_raw)
        rev_uuid = UUID(revision_id_raw)
    except ValueError:
        return ProposeResult(
            rejected=True,
            reason="profile_id, environment_id, revision_id must all be UUIDs",
            summary="", resolved_input={},
        )

    from app.models.environment import Environment
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

    summary = (
        f"Roll back {profile.name!r} in {env.name} to revision "
        f"v{revision.version} (published by {revision.published_by})"
    )
    return ProposeResult(
        summary=summary,
        resolved_input={
            "profile_id": str(profile_uuid),
            "environment_id": str(env_uuid),
            "revision_id": str(rev_uuid),
        },
    )


def _execute(ctx: ActionCtx, resolved: dict[str, Any]) -> dict[str, Any]:
    from app.routers.gateway_profiles_v2 import (
        RollbackBody,
        rollback_profile as _http_rollback,
    )

    body = RollbackBody(
        environment_id=UUID(resolved["environment_id"]),
        revision_id=UUID(resolved["revision_id"]),
    )
    profile = _http_rollback(
        workspace_id=ctx.workspace_id,
        profile_id=UUID(resolved["profile_id"]),
        body=body, db=ctx.db,
        _ws=ctx.workspace_id,
        caller=ctx.user_email or ctx.clerk_user_id or "lens",
    )
    return {
        "id": str(profile.id),
        "name": profile.name,
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
    name="gateway_v2_rollback",
    guard_permission="platform.credentials.manage",
    propose=_propose,
    execute=_execute,
    description=(
        "Repoint an environment × alias binding at a historical revision "
        "of the profile. Two-step: returns a pending action for the user "
        "to confirm; the confirm click writes the new binding and appends "
        "to the profile binding events audit log."
    ),
))
