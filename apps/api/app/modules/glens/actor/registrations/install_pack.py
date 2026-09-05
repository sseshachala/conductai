"""#1300 — Lens actor: install a marketplace skill pack into the workspace.

Two-step: `propose` validates the slug exists in the catalog and isn't
already installed; the confirm card shows the pack name + rule count.
`execute` inserts the `WorkspaceSkillPack` row and invalidates the policy
cache so new rules apply on the next Guard evaluation.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from app.modules.glens.actor.registry import default_action_registry
from app.modules.glens.actor.types import ActionCtx, ActionSpec, ProposeResult

log = structlog.get_logger()


def _propose_install_pack(ctx: ActionCtx, args: dict[str, Any]) -> ProposeResult:
    slug = str(args.get("slug") or "").strip()
    if not slug:
        return ProposeResult(rejected=True, reason="slug required",
                             summary="", resolved_input={})

    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
    except ValueError:
        return ProposeResult(rejected=True, reason="Invalid workspace",
                             summary="", resolved_input={})

    from app.modules.guard.models import WorkspaceSkillPack
    from app.routers.compliance import _latest_pack

    pack = _latest_pack(ctx.db, slug)
    if not pack:
        return ProposeResult(
            rejected=True,
            reason=f"No pack matches slug '{slug}' in the catalog",
            summary="", resolved_input={},
        )

    existing = ctx.db.get(WorkspaceSkillPack, (ws_uuid, slug))
    if existing:
        return ProposeResult(
            rejected=True,
            reason=f"Pack '{slug}' is already installed",
            summary="", resolved_input={},
        )

    rules_count = len(pack.rules or [])
    summary = f"Install pack '{pack.name}' ({rules_count} rules)"

    return ProposeResult(
        summary=summary,
        resolved_input={
            "slug": slug,
            "pack_name": pack.name,
            "rules_count": rules_count,
        },
    )


def _execute_install_pack(ctx: ActionCtx, resolved: dict[str, Any]) -> dict[str, Any]:
    """Insert WorkspaceSkillPack + invalidate policy cache. Reuses the same
    invalidator the HTTP install endpoint calls so a pack installed here
    behaves identically to one installed from the marketplace UI."""
    from app.modules.guard.models import WorkspaceSkillPack
    from app.modules.guard.policy_engine import invalidate_policy_cache

    slug = resolved["slug"]
    ws_uuid = _uuid.UUID(ctx.workspace_id)

    existing = ctx.db.get(WorkspaceSkillPack, (ws_uuid, slug))
    if not existing:
        ctx.db.add(WorkspaceSkillPack(
            workspace_id=ws_uuid,
            pack_slug=slug,
            installed_by=ctx.clerk_user_id or "lens.actor",
            installed_at=datetime.now(timezone.utc),
        ))

    invalidate_policy_cache(ctx.db, ws_uuid)
    ctx.db.commit()

    return {
        "slug": slug,
        "pack_name": resolved.get("pack_name"),
        "rules_installed": resolved.get("rules_count", 0),
        "installed": True,
    }


default_action_registry.register(ActionSpec(
    name="install_pack",
    guard_permission="guard.policies.edit",
    propose=_propose_install_pack,
    execute=_execute_install_pack,
    description=(
        "Install a marketplace skill pack into the workspace. Two-step: "
        "returns a pending action for the user to confirm; the confirm click "
        "adds the WorkspaceSkillPack row and invalidates the policy cache."
    ),
))
