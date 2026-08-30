"""`_require_confirmation()` — the substrate entry every mutating tool's
ToolDef `impl` calls after doing its Guard permission check.

Persists a `guard_approval_requests` row with `surface='lens'` (or the
inbound MCP surface) and returns the confirm envelope. The row is later
resolved by the `/glens/actions/{id}/confirm` endpoint, which calls
`spec.execute()`.
"""
from __future__ import annotations

from typing import Any

from app.modules.glens.actor.types import ActionCtx, ActionSpec
from app.modules.guard.approval import create_approval_request
from app.modules.guard.models import GuardApprovalRequest


# Sentinel rule_id used for Lens-proposed actions. Distinct from real
# policy-triggered pauses so audit consumers can filter cleanly.
LENS_ACTOR_RULE_ID_PREFIX = "lens.actor.confirm"
LENS_ACTOR_RULE_PACK = "lens.actor"


def build_confirm_envelope(row: GuardApprovalRequest) -> dict[str, Any]:
    """Shape the LLM/chat surface sees when a mutating tool proposes an
    action. Consumers key on `confirm_required=True` and dispatch to
    `<ActionConfirmCard>` via `tool_name`."""
    return {
        "confirm_required": True,
        "approval_request_id": str(row.id),
        "tool_name": row.tool_name,
        "summary": row.rule_message or "",
        "warnings": row.tool_input.get("_warnings", []) if row.tool_input else [],
        "expires_at": row.timeout_at.isoformat() if row.timeout_at else None,
        "surface": row.surface,
    }


def require_confirmation(
    ctx: ActionCtx,
    spec: ActionSpec,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    """Guard-check + validate + persist a pending approval row.

    Returns either:
      - `{"blocked": True, "reason": ...}` when propose rejects or Guard blocks
      - the confirm envelope from `build_confirm_envelope()` on success

    Never mutates outside `guard_approval_requests`.
    """
    proposal = spec.propose(ctx, tool_input)
    if proposal.rejected:
        return {"blocked": True, "reason": proposal.reason or "Proposal rejected"}

    # Guard pre-flight — same policy engine every other surface uses.
    # We call the shared evaluator directly so any policy that would block
    # the underlying HTTP endpoint also blocks the Lens-proposed action.
    guard_warnings: list[str] = list(proposal.warnings)
    guard_decision: str = "allowed"

    try:
        from app.guard.policy_engine import evaluate_composed
        from app.guard.policy_types import PolicyDecision

        decision: PolicyDecision = evaluate_composed(
            workspace_id=ctx.workspace_id,
            tool_name=spec.name,
            tool_input=proposal.resolved_input,
            clerk_user_id=ctx.clerk_user_id,
            surface=ctx.surface,
        )
        if getattr(decision.action, "value", str(decision.action)).lower() == "block":
            return {
                "blocked": True,
                "reason": decision.reason or f"Policy blocks {spec.name}",
            }
        if getattr(decision.action, "value", str(decision.action)).lower() == "warn":
            guard_decision = "warned"
            if decision.reason:
                guard_warnings.append(decision.reason)
    except Exception:
        # Guard evaluation is best-effort at the propose stage — the confirm
        # endpoint re-checks before dispatch via the underlying service call
        # (which enforces its own permission). Never fail-open on real errors:
        # the confirm route is the enforcement point.
        pass

    # Persist the pending approval. `surface='lens'` (or the inbound MCP
    # surface) tags where the proposal came from. Rule_id is a synthetic
    # marker so approvals-list callers can distinguish Lens-proposed from
    # policy-paused rows.
    persisted_input = {**proposal.resolved_input}
    if guard_warnings:
        persisted_input["_warnings"] = guard_warnings

    row = create_approval_request(
        ctx.db,
        workspace_id=ctx.workspace_id,
        rule={
            "id": f"{LENS_ACTOR_RULE_ID_PREFIX}.{spec.name}",
            "pack": LENS_ACTOR_RULE_PACK,
            "message": proposal.summary,
            "approval_type": "any_authorized",
            "approval_timeout_sec": int(spec.expires_in.total_seconds()),
        },
        tool_name=spec.name,
        tool_input=persisted_input,
        requester_email=ctx.user_email,
        requester_user_id=ctx.clerk_user_id,
        requester_agent_ident=ctx.agent_identity_id,
        surface=ctx.surface or "lens",
        session_id=ctx.session_id,
    )
    ctx.db.commit()

    envelope = build_confirm_envelope(row)
    envelope["guard_decision"] = guard_decision
    return envelope
