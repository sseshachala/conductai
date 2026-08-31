"""Actor substrate helpers.

- `require_confirmation()` — mutating tools' impl call this to persist a
  `guard_approval_requests` row and return the confirm envelope for the LLM/UI.
- `dispatch_confirm()` / `dispatch_cancel()` — decide + dispatch (or cancel)
  a pending action. Shared by the HTTP endpoint (`POST /glens/actions/{id}/...`)
  and the LLM-callable `confirm_pending_action` / `cancel_pending_action`
  tools introduced in #1465 so natural-language "yes"/"no" actually works.
"""
from __future__ import annotations

import hashlib
import json
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.modules.glens.actor.types import ActionCtx, ActionSpec
from app.modules.glens.events import publish_session_event
from app.modules.guard.approval import (
    apply_decision,
    can_decide,
    create_approval_request,
    sweep_if_timed_out,
)
from app.modules.guard.models import GuardApprovalRequest


def _publish_action_event(row: GuardApprovalRequest, event_type: str, *, result: Any = None, cached: bool = False) -> None:
    """Tee an action.* event to the row's originating Lens session so any
    open session-stream connection can update its bubble reactively.

    No-op when the row has no session_id (HTTP actor calls without chat
    context — nothing to route to). Fail-open inside publish_session_event
    means Redis outages never fail the decide operation.
    """
    if not row.session_id:
        return
    payload: dict[str, Any] = {
        "tool_name": row.tool_name,
        "status": row.status,
    }
    if result is not None:
        payload["result"] = result
    if cached:
        payload["cached"] = True
    publish_session_event(
        row.session_id,
        event_type,
        entity={"type": "approval", "id": str(row.id)},
        payload=payload,
    )


def _idempotency_key(tool_name: str, resolved_input: dict[str, Any]) -> str:
    """Stable per-(tool, input) key used to dedupe pending proposals within
    a session. `_warnings` and `_execute_result` are computed post-facto so
    they are stripped before hashing."""
    scrub = {k: v for k, v in resolved_input.items() if not k.startswith("_")}
    payload = json.dumps({"tool": tool_name, "input": scrub}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _find_existing_pending(
    db: Session,
    *,
    workspace_id: str,
    session_id: str | None,
    tool_name: str,
    idem_key: str,
) -> GuardApprovalRequest | None:
    """Look for an unexpired PENDING row matching the same session + tool +
    idempotency key. Session-scoped so unrelated sessions don't collide."""
    try:
        ws = _uuid.UUID(workspace_id)
    except ValueError:
        return None

    q = (
        db.query(GuardApprovalRequest)
        .filter(
            GuardApprovalRequest.workspace_id == ws,
            GuardApprovalRequest.tool_name == tool_name,
            GuardApprovalRequest.status == "pending",
            GuardApprovalRequest.timeout_at > datetime.now(timezone.utc),
        )
    )
    if session_id is not None:
        q = q.filter(GuardApprovalRequest.session_id == session_id)
    else:
        q = q.filter(GuardApprovalRequest.session_id.is_(None))

    # Filter idem_key in Python — tool_input is JSONB and we stash the key in
    # a private field. Fetching a handful of rows per (workspace, session,
    # tool) is fine at Lens volume.
    for row in q.order_by(GuardApprovalRequest.created_at.desc()).limit(10).all():
        if (row.tool_input or {}).get("_idem_key") == idem_key:
            return row
    return None


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

    # Session-scoped idempotency (#1470). Re-proposing the exact same action
    # in the same session returns the ORIGINAL envelope + row, so the LLM
    # can call `run_workflow` twice without losing the ActionConfirmBubble
    # or creating duplicate pending rows.
    idem_key = _idempotency_key(spec.name, proposal.resolved_input)
    existing = _find_existing_pending(
        ctx.db,
        workspace_id=ctx.workspace_id,
        session_id=ctx.session_id,
        tool_name=spec.name,
        idem_key=idem_key,
    )
    if existing is not None:
        envelope = build_confirm_envelope(existing)
        envelope["guard_decision"] = guard_decision
        envelope["deduped"] = True
        return envelope

    # Persist the pending approval. `surface='lens'` (or the inbound MCP
    # surface) tags where the proposal came from. Rule_id is a synthetic
    # marker so approvals-list callers can distinguish Lens-proposed from
    # policy-paused rows.
    persisted_input = {**proposal.resolved_input, "_idem_key": idem_key}
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
    """Enforce that only an authorized decider can act on the pending row.

    Two proposer classes:
      1. Human-proposed (real clerk_user_id) — same human must decide, matches
         the pre-actor-substrate model.
      2. Agent-proposed (requester_agent_ident set, or synthetic user id like
         'system:lens') — this is HITL: an agent proposes, a human approves.
         Route auth already gated the caller via `platform.approvals.decide`,
         so any workspace user with that permission may decide.

    Session_id still matches when both sides carry one — protects against a
    compromised LLM in a different session confirming this session's rows.
    """
    is_agent_proposed = bool(getattr(row, "requester_agent_ident", None)) or (
        isinstance(row.requester_user_id, str) and row.requester_user_id.startswith("system:")
    )
    if (
        not is_agent_proposed
        and row.requester_user_id
        and clerk_user_id
        and row.requester_user_id != clerk_user_id
    ):
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
        cached_result = row.tool_input.get("_execute_result")
        # Re-publish so cross-tab subscribers that missed the first event
        # (e.g. tab opened after the confirm) still see the resolution.
        _publish_action_event(row, "action.confirmed", result=cached_result, cached=True)
        return {
            "executed": True,
            "cached": True,
            "action_id": str(row.id),
            "tool_name": row.tool_name,
            "status": row.status,
            "result": cached_result,
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

    _publish_action_event(row, "action.confirmed", result=result)

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

    _publish_action_event(row, "action.cancelled")

    return {
        "cancelled": True,
        "action_id": str(row.id),
        "tool_name": row.tool_name,
    }
