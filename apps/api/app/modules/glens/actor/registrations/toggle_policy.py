"""#1303 — Lens actor: enable_policy + disable_policy.

Two ActionSpecs share one file because their propose/execute paths only
differ by the target `enabled` value. Both handle custom rules
(WorkspaceCustomRule) and pack rules (GuardRuleOverride) — same shape as
the HTTP PATCH /guard/policies/{rule_id} handler.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from app.modules.glens.actor.registry import default_action_registry
from app.modules.glens.actor.types import ActionCtx, ActionSpec, ProposeResult

log = structlog.get_logger()


def _resolve_policy(ctx: ActionCtx, rule_id: str) -> tuple[str, Any] | None:
    """Look up a rule by id — returns (kind, row) where kind is 'custom' or
    'pack'. Returns None if the rule doesn't exist in this workspace."""
    from app.modules.guard.models import WorkspaceCustomRule
    from app.modules.guard.routers.policies import _find_pack_rule

    ws_uuid = _uuid.UUID(ctx.workspace_id)
    custom = ctx.db.get(WorkspaceCustomRule, (ws_uuid, rule_id))
    if custom is not None:
        return ("custom", custom)

    found = _find_pack_rule(ctx.db, ws_uuid, rule_id)
    if found is not None:
        return ("pack", found)  # found = (rule_dict, WorkspaceSkillPack)

    return None


def _propose_toggle(ctx: ActionCtx, args: dict[str, Any], *, target_enabled: bool) -> ProposeResult:
    verb = "Enable" if target_enabled else "Disable"
    rule_id = str(args.get("rule_id") or "").strip()
    if not rule_id:
        return ProposeResult(rejected=True, reason="rule_id required",
                             summary="", resolved_input={})

    try:
        _uuid.UUID(ctx.workspace_id)
    except ValueError:
        return ProposeResult(rejected=True, reason="Invalid workspace",
                             summary="", resolved_input={})

    resolved = _resolve_policy(ctx, rule_id)
    if resolved is None:
        return ProposeResult(
            rejected=True,
            reason=f"No policy matches rule_id '{rule_id}' in this workspace",
            summary="", resolved_input={},
        )
    kind, row = resolved

    # Disabling a pack rule is a policy exception — surfaced in audit trail.
    # Reason is required on disable to prevent silent permanent removals.
    reason = str(args.get("reason") or "").strip()
    if not target_enabled and kind == "pack" and not reason:
        return ProposeResult(
            rejected=True,
            reason="Disabling a pack rule requires a reason (compliance exception surfaces this in the audit trail).",
            summary="", resolved_input={},
        )

    if kind == "custom":
        current_enabled = bool(row.enabled)
        rule_name = (row.body or {}).get("description") or rule_id
    else:
        rule_dict, _wp = row
        rule_name = rule_dict.get("description") or rule_dict.get("id") or rule_id
        current_enabled = True  # pack rules default enabled unless override says otherwise
        from app.modules.guard.models import GuardRuleOverride
        override = ctx.db.get(GuardRuleOverride, (_uuid.UUID(ctx.workspace_id), rule_id))
        if override is not None and override.disabled:
            current_enabled = False

    if current_enabled == target_enabled:
        state = "enabled" if target_enabled else "disabled"
        return ProposeResult(
            rejected=True,
            reason=f"Rule '{rule_id}' is already {state}",
            summary="", resolved_input={},
        )

    summary = f"{verb} policy '{rule_name}' ({rule_id})"
    return ProposeResult(
        summary=summary,
        resolved_input={
            "rule_id": rule_id,
            "kind": kind,
            "target_enabled": target_enabled,
            "reason": reason or None,
        },
    )


def _execute_toggle(ctx: ActionCtx, resolved: dict[str, Any]) -> dict[str, Any]:
    from app.modules.guard.models import (
        GuardRuleOverride, WorkspaceCustomRule,
    )
    from app.modules.guard.policy_engine import invalidate_policy_cache

    rule_id = resolved["rule_id"]
    kind = resolved["kind"]
    target = bool(resolved["target_enabled"])
    ws_uuid = _uuid.UUID(ctx.workspace_id)
    now = datetime.now(timezone.utc)

    if kind == "custom":
        row = ctx.db.get(WorkspaceCustomRule, (ws_uuid, rule_id))
        if row is None:
            raise ValueError(f"custom rule {rule_id} disappeared between propose and execute")
        row.enabled = target
        row.updated_at = now
    else:
        # Pack rule → upsert override with disabled=(not target).
        override = ctx.db.get(GuardRuleOverride, (ws_uuid, rule_id))
        if override is None:
            override = GuardRuleOverride(
                workspace_id=ws_uuid,
                rule_id=rule_id,
                disabled=not target,
                reason=resolved.get("reason"),
                overridden_by=ctx.clerk_user_id or "lens.actor",
                created_at=now,
                updated_at=now,
            )
            ctx.db.add(override)
        else:
            override.disabled = not target
            if resolved.get("reason"):
                override.reason = resolved["reason"]
            override.overridden_by = ctx.clerk_user_id or "lens.actor"
            override.updated_at = now

    ctx.db.commit()
    invalidate_policy_cache(ctx.db, ws_uuid)

    return {
        "rule_id": rule_id,
        "kind": kind,
        "enabled": target,
    }


def _propose_enable(ctx, args):
    return _propose_toggle(ctx, args, target_enabled=True)


def _propose_disable(ctx, args):
    return _propose_toggle(ctx, args, target_enabled=False)


default_action_registry.register(ActionSpec(
    name="enable_policy",
    guard_permission="guard.policies.edit",
    propose=_propose_enable,
    execute=_execute_toggle,
    description=(
        "Enable a Guard policy rule by id. Two-step: returns a pending "
        "action for the user to confirm; the confirm click flips the "
        "enabled flag + invalidates the policy cache."
    ),
))

default_action_registry.register(ActionSpec(
    name="disable_policy",
    guard_permission="guard.policies.edit",
    propose=_propose_disable,
    execute=_execute_toggle,
    description=(
        "Disable a Guard policy rule by id. Two-step: returns a pending "
        "action for the user to confirm; the confirm click flips the enabled "
        "flag + invalidates the policy cache. Disabling a pack rule requires "
        "a reason (compliance exception surfaces in the audit trail)."
    ),
))
