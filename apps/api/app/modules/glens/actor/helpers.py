"""Actor substrate helpers.

- `require_confirmation()` — mutating tools' impl call this to persist a
  `guard_approval_requests` row and return the confirm envelope for the LLM/UI.
- `dispatch_confirm()` / `dispatch_cancel()` — decide + dispatch (or cancel)
  a pending action. Shared by the HTTP endpoint (`POST /glens/actions/{id}/...`)
  and the LLM-callable `confirm_pending_action` / `cancel_pending_action`
  tools introduced in #1465 so natural-language "yes"/"no" actually works.
"""
from __future__ import annotations

import uuid as _uuid
from typing import Any

from sqlalchemy.orm import Session

from app.modules.glens.actor.types import ActionCtx, ActionSpec
from app.modules.guard.approval import (
    apply_decision,
    can_decide,
    create_approval_request,
    sweep_if_timed_out,
)
from app.modules.guard.models import GuardApprovalRequest


class ConfirmError(Exception):
    """Raised inside `dispatch_confirm` / `dispatch_cancel` to signal a
    user-facing error with a matching HTTP status code. Endpoints translate
    to HTTPException; LLM tools translate to `{"error": detail}`."""
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


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


# ── Confirm / Cancel dispatch — shared by HTTP endpoint + LLM tools (#1465) ─

def _get_pending_row(
    db: Session, action_id: str, workspace_id: str,
) -> GuardApprovalRequest:
    try:
        aid = _uuid.UUID(action_id)
        ws = _uuid.UUID(workspace_id)
    except ValueError:
        raise ConfirmError(400, "invalid action id")
    row = (
        db.query(GuardApprovalRequest)
        .filter(
            GuardApprovalRequest.id == aid,
            GuardApprovalRequest.workspace_id == ws,
        )
        .first()
    )
    if not row:
        raise ConfirmError(404, "action not found")
    return row


def _enforce_ownership(
    row: GuardApprovalRequest,
    *,
    clerk_user_id: str | None,
    session_id: str | None,
) -> None:
    """The proposer must own the pending action. Session_id must match when
    both sides carry one — protects against a compromised LLM in a different
    session confirming actions from this session."""
    if row.requester_user_id and clerk_user_id and row.requester_user_id != clerk_user_id:
        raise ConfirmError(403, "only the proposer can decide this action")
    if row.session_id and session_id and row.session_id != session_id:
        raise ConfirmError(403, "action belongs to a different chat session")


def dispatch_confirm(
    db: Session,
    *,
    action_id: str,
    workspace_id: str,
    clerk_user_id: str | None,
    user_email: str | None,
    role: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Confirm a pending action and run `spec.execute`.

    Returns a serialisable dict on success. Raises `ConfirmError` on any
    user-facing failure. Caller decides how to surface the error
    (HTTPException for the endpoint, `{"error": detail}` for the LLM tool).
    """
    from app.modules.glens.actor.registry import default_action_registry

    row = _get_pending_row(db, action_id, workspace_id)
    row = sweep_if_timed_out(db, row)

    # Idempotent success — already executed, return cached result.
    if row.status == "approved" and (row.tool_input or {}).get("_execute_result") is not None:
        return {
            "executed": True,
            "cached": True,
            "action_id": str(row.id),
            "tool_name": row.tool_name,
            "status": row.status,
            "result": row.tool_input.get("_execute_result"),
        }

    if row.status != "pending":
        raise ConfirmError(409, f"action is {row.status}")

    _enforce_ownership(row, clerk_user_id=clerk_user_id, session_id=session_id)

    spec = default_action_registry.get(row.tool_name)
    if not spec:
        raise ConfirmError(500, f"no spec registered for {row.tool_name}")

    decider_email = user_email or row.requester_email
    ok, reason = can_decide(
        row, decider_email=decider_email, decider_user_id=clerk_user_id, decider_role=role,
    )
    if not ok:
        raise ConfirmError(403, reason or "not authorized")

    # Mark approved (writes hash-chained audit event).
    row = apply_decision(
        db, row,
        decision="approved",
        decider_email=decider_email,
        decider_user_id=clerk_user_id,
        reason=f"lens.actor:{row.tool_name}",
    )

    # Dispatch spec.execute.
    action_ctx = ActionCtx(
        db=db,
        workspace_id=workspace_id,
        clerk_user_id=clerk_user_id,
        user_email=decider_email,
        session_id=row.session_id,
        agent_identity_id=row.requester_agent_ident,
        surface=row.surface or "lens",
    )
    try:
        result = spec.execute(action_ctx, row.tool_input)
    except Exception as exc:
        # Approved row stays as-is for audit trail; caller sees an error.
        raise ConfirmError(500, f"execute failed: {exc}")

    # Cache result on the row for idempotent replay.
    row.tool_input = {**(row.tool_input or {}), "_execute_result": result}
    db.commit()

    return {
        "executed": True,
        "cached": False,
        "action_id": str(row.id),
        "tool_name": row.tool_name,
        "status": row.status,
        "result": result,
    }


def dispatch_cancel(
    db: Session,
    *,
    action_id: str,
    workspace_id: str,
    clerk_user_id: str | None,
    user_email: str | None,
    reason: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Cancel a pending action. No spec.execute — just marks rejected."""
    row = _get_pending_row(db, action_id, workspace_id)
    row = sweep_if_timed_out(db, row)
    if row.status != "pending":
        raise ConfirmError(409, f"action is {row.status}")

    _enforce_ownership(row, clerk_user_id=clerk_user_id, session_id=session_id)

    decider_email = user_email or row.requester_email
    apply_decision(
        db, row,
        decision="rejected",
        decider_email=decider_email,
        decider_user_id=clerk_user_id,
        reason=reason or f"lens.actor.cancelled:{row.tool_name}",
    )
    return {
        "cancelled": True,
        "action_id": str(row.id),
        "tool_name": row.tool_name,
    }
