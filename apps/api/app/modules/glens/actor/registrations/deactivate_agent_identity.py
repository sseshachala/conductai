"""#1304 — Lens actor: deactivate an agent identity (security kill switch).

Two-step: `propose` validates the agent exists in this workspace and isn't
already deactivated. `execute` sets `lifecycle_state='deactivated'` +
`deactivated_at=now()` — matches the check constraint on the model.

Reuses `platform.members.manage` for RBAC since `platform.agents.manage`
isn't in the seeded permission set (see CLAUDE.md permission list).
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from app.modules.glens.actor.registry import default_action_registry
from app.modules.glens.actor.types import ActionCtx, ActionSpec, ProposeResult

log = structlog.get_logger()


def _propose_deactivate(ctx: ActionCtx, args: dict[str, Any]) -> ProposeResult:
    agent_id = str(args.get("agent_id") or "").strip()
    if not agent_id:
        return ProposeResult(rejected=True, reason="agent_id required",
                             summary="", resolved_input={})

    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
    except ValueError:
        return ProposeResult(rejected=True, reason="Invalid workspace",
                             summary="", resolved_input={})

    from app.modules.agent_identity.models import AgentIdentity

    agent = ctx.db.query(AgentIdentity).filter(
        AgentIdentity.id == agent_id,
        AgentIdentity.workspace_id == ws_uuid,
    ).first()
    if agent is None:
        return ProposeResult(
            rejected=True,
            reason=f"No agent identity matches id '{agent_id}' in this workspace",
            summary="", resolved_input={},
        )

    if agent.lifecycle_state == "deactivated":
        return ProposeResult(
            rejected=True,
            reason=f"Agent '{agent.name}' ({agent_id}) is already deactivated",
            summary="", resolved_input={},
        )

    reason = str(args.get("reason") or "").strip() or None
    summary = f"Deactivate agent identity '{agent.name}' ({agent.provider})"
    if reason:
        summary += f" — {reason}"

    return ProposeResult(
        summary=summary,
        resolved_input={
            "agent_id": agent_id,
            "agent_name": agent.name,
            "provider": agent.provider,
            "reason": reason,
        },
    )


def _execute_deactivate(ctx: ActionCtx, resolved: dict[str, Any]) -> dict[str, Any]:
    """Flip lifecycle_state to 'deactivated' + stamp deactivated_at. Runtime
    token-resolution code checks lifecycle_state before allowing use, so this
    kill-switch takes effect on the next call."""
    from app.modules.agent_identity.models import AgentIdentity

    agent_id = resolved["agent_id"]
    ws_uuid = _uuid.UUID(ctx.workspace_id)

    agent = ctx.db.query(AgentIdentity).filter(
        AgentIdentity.id == agent_id,
        AgentIdentity.workspace_id == ws_uuid,
    ).first()
    if agent is None:
        raise ValueError(f"agent {agent_id} disappeared between propose and execute")

    agent.lifecycle_state = "deactivated"
    agent.deactivated_at = datetime.now(timezone.utc)
    ctx.db.commit()

    return {
        "agent_id": agent_id,
        "agent_name": resolved.get("agent_name"),
        "lifecycle_state": "deactivated",
        "reason": resolved.get("reason"),
    }


default_action_registry.register(ActionSpec(
    name="deactivate_agent_identity",
    guard_permission="platform.members.manage",
    propose=_propose_deactivate,
    execute=_execute_deactivate,
    description=(
        "Deactivate an agent identity (security kill switch) by id. Two-step: "
        "returns a pending action for the user to confirm; the confirm click "
        "sets lifecycle_state='deactivated' so the identity can no longer "
        "authenticate on the next call. Existing tokens stop working."
    ),
))
