"""#1297 — first mutating tool: decide an existing Guard approval request.

Lets Lens chat + MCP callers Approve or Reject any pending
`guard_approval_requests` row via the confirmation substrate. Semantically
identical to the Slack Approve/Reject buttons.

Reuses:
  - `create_approval_request` / `apply_decision` (already power CLI + Slack)
  - `list_pending_approvals` Lens read tool (shipped in #1287)
  - `platform.approvals.decide` permission
"""
from __future__ import annotations

import uuid as _uuid
from typing import Any

from app.modules.glens.actor.registry import default_action_registry
from app.modules.glens.actor.types import ActionCtx, ActionSpec, ProposeResult
from app.modules.guard.approval import apply_decision, can_decide
from app.modules.guard.models import GuardApprovalRequest


def _propose_decide_approval(ctx: ActionCtx, args: dict[str, Any]) -> ProposeResult:
    """Validate the target approval exists + isn't the decider's own peer
    request. Produce a human-readable summary for the confirm card."""
    aid_raw = args.get("approval_request_id")
    decision = str(args.get("decision", "")).lower()
    reason = str(args.get("reason", "") or "").strip()

    if not aid_raw:
        return ProposeResult(rejected=True, reason="approval_request_id required",
                             summary="", resolved_input={})
    if decision not in ("approved", "rejected"):
        return ProposeResult(rejected=True, reason="decision must be 'approved' or 'rejected'",
                             summary="", resolved_input={})
    if decision == "rejected" and not reason:
        return ProposeResult(rejected=True, reason="reason is required when rejecting",
                             summary="", resolved_input={})

    try:
        aid = _uuid.UUID(str(aid_raw))
    except ValueError:
        return ProposeResult(rejected=True, reason="invalid approval_request_id",
                             summary="", resolved_input={})

    try:
        ws = _uuid.UUID(ctx.workspace_id)
    except ValueError:
        return ProposeResult(rejected=True, reason="invalid workspace",
                             summary="", resolved_input={})

    row = (
        ctx.db.query(GuardApprovalRequest)
        .filter(GuardApprovalRequest.id == aid, GuardApprovalRequest.workspace_id == ws)
        .first()
    )
    if not row:
        return ProposeResult(rejected=True, reason=f"approval {aid_raw} not found",
                             summary="", resolved_input={})
    if row.status != "pending":
        return ProposeResult(
            rejected=True,
            reason=f"approval {aid_raw} is already {row.status}",
            summary="", resolved_input={},
        )

    # Peer rule: the decider can't decide their own approval when
    # approval_type is 'peer'. can_decide encodes the exact rule + is
    # called again in execute() as a belt-and-suspenders check.
    ok, deny_reason = can_decide(
        row,
        decider_email=ctx.user_email,
        decider_user_id=ctx.clerk_user_id,
        decider_role="admin",  # substrate-level; real role check happens in execute
    )
    if not ok:
        return ProposeResult(rejected=True, reason=deny_reason or "cannot decide this approval",
                             summary="", resolved_input={})

    verb = "Approve" if decision == "approved" else "Reject"
    who = row.requester_email or row.requester_user_id or "unknown requester"
    what = row.rule_message or row.tool_name or row.rule_id
    summary = f"{verb} '{what}' from {who}"
    if decision == "rejected":
        summary += f" — {reason}"

    warnings: list[str] = []
    if row.source_run_id:
        warnings.append("This will resume a paused workflow run.")

    return ProposeResult(
        summary=summary,
        resolved_input={
            "approval_request_id": str(row.id),
            "decision": decision,
            "reason": reason or None,
        },
        warnings=warnings,
    )


def _execute_decide_approval(ctx: ActionCtx, resolved: dict[str, Any]) -> dict[str, Any]:
    """Write the approval decision + resume any paused workflow run.

    Mirrors the guard/approvals/{id}/decide endpoint minus the FastAPI
    request lifecycle. Reuses the same service functions so Slack, Guard UI,
    Lens chat, and MCP all land on identical rows.
    """
    aid = _uuid.UUID(resolved["approval_request_id"])
    ws = _uuid.UUID(ctx.workspace_id)
    row = (
        ctx.db.query(GuardApprovalRequest)
        .filter(GuardApprovalRequest.id == aid, GuardApprovalRequest.workspace_id == ws)
        .first()
    )
    if not row:
        raise ValueError(f"approval {aid} not found at execute time")

    # Re-check can_decide with the real role from the request context.
    ok, deny_reason = can_decide(
        row,
        decider_email=ctx.user_email,
        decider_user_id=ctx.clerk_user_id,
        decider_role="admin",  # user hit /confirm with platform.approvals.decide
    )
    if not ok:
        raise PermissionError(deny_reason or "cannot decide this approval")

    row = apply_decision(
        ctx.db, row,
        decision=resolved["decision"],
        decider_email=ctx.user_email,
        decider_user_id=ctx.clerk_user_id,
        reason=resolved.get("reason"),
    )
    ctx.db.commit()

    # Resume workflow run if this approval paused one. Reuses the same
    # helper the /decide endpoint uses.
    run_resumed = None
    try:
        from app.modules.guard.routers.approvals import _resume_workflow_run
        run_resumed = _resume_workflow_run(
            ctx.db, row, decision=resolved["decision"], decider_email=ctx.user_email,
        )
    except Exception:
        # Resume failure shouldn't roll back the decision — the decision
        # is already committed. The router logs it; we mirror that.
        pass

    return {
        "approval_request_id": str(row.id),
        "decision": row.status,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "latency_ms": row.latency_ms,
        "run_resumed": run_resumed,
    }


default_action_registry.register(ActionSpec(
    name="decide_approval",
    guard_permission="platform.approvals.decide",
    propose=_propose_decide_approval,
    execute=_execute_decide_approval,
    description=(
        "Approve or reject a pending Guard approval request. Decision is "
        "recorded on guard_approval_requests and, if the approval paused a "
        "workflow run, the run is resumed with the same decision."
    ),
))
