"""ConductGuard HITL approval helpers (#1140).

One place that all Guard code paths call when a rule with action=approval
fires — MCP hook, LLM proxy, workflow guard_block. Creates a
GuardApprovalRequest row, fans out notifications, and returns the pending
marker text that surfaces expect (CLI/MCP prints it verbatim; workflow
runtime writes an approval_requested run_event alongside).

Decide flow lives in `apps/api/app/modules/guard/routers/approvals.py`.
"""
from __future__ import annotations

import json
import os
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.core.pii import redact_secrets
from app.modules.guard.models import GuardApprovalRequest, GuardAuditEvent, chain_hash_for_insert, get_policy_hash

log = structlog.get_logger(__name__)


# Default timeout when the rule does not specify one. 30 minutes is enough
# for a human to notice a Slack ping and decide, without leaving pending
# requests around forever.
DEFAULT_TIMEOUT_SEC = 1800
_VALID_APPROVAL_TYPES = {"peer", "any_admin", "any_security", "any_authorized"}


def _base_url() -> str:
    return (os.environ.get("CONDUCT_WEB_URL") or "https://conductai.ai").rstrip("/")


def approval_url(request_id: str | _uuid.UUID) -> str:
    return f"{_base_url()}/theguard/approvals?highlight={request_id}"


def _snapshot_input(tool_input: dict | None) -> dict:
    """Redact secrets from the tool input before persisting. Bound size at
    ~8KB serialized — large blobs don't add signal for a human deciding."""
    if not tool_input:
        return {}
    try:
        result = redact_secrets(json.dumps(tool_input, default=str))
        # redact_secrets returns (cleaned_text, secret_labels) — unpack.
        redacted = result[0] if isinstance(result, tuple) else result
        payload = json.loads(redacted)
    except Exception:
        # If redaction/serialisation blows up, keep the pause functional but
        # store nothing rather than leaking the raw call.
        return {"__redacted__": "snapshot unavailable"}
    dumped = json.dumps(payload, default=str)
    if len(dumped) > 8192:
        return {"__truncated__": True, "preview": dumped[:8192]}
    return payload


def create_approval_request(
    db: Session,
    *,
    workspace_id: str | _uuid.UUID,
    rule: dict,
    tool_name: str | None,
    tool_input: dict | None,
    requester_email: str | None,
    requester_user_id: str | None = None,
    requester_agent_ident: str | None = None,
    surface: str = "unknown",
    session_id: str | None = None,
    source_run_id: str | _uuid.UUID | None = None,
    source_block_id: str | None = None,
    now: datetime | None = None,
) -> GuardApprovalRequest:
    """Materialise one pending approval row + write the audit event.

    Notifications are fanned out separately (dispatch_approval_notifications)
    so callers that emit their own audit path (like guard_block) can control
    ordering and error handling."""
    ws = workspace_id if isinstance(workspace_id, _uuid.UUID) else _uuid.UUID(str(workspace_id))
    ts = now or datetime.now(timezone.utc)

    timeout_sec = int(rule.get("approval_timeout_sec") or DEFAULT_TIMEOUT_SEC)
    if timeout_sec < 60:
        timeout_sec = 60
    approval_type = str(rule.get("approval_type") or "any_authorized").lower()
    if approval_type not in _VALID_APPROVAL_TYPES:
        approval_type = "any_authorized"

    row = GuardApprovalRequest(
        workspace_id=ws,
        rule_id=str(rule.get("id") or rule.get("rule_id") or "unknown"),
        rule_pack=rule.get("pack") or rule.get("pack_slug"),
        rule_message=rule.get("message"),
        tool_name=tool_name,
        tool_input=_snapshot_input(tool_input),
        requester_email=requester_email,
        requester_user_id=requester_user_id,
        requester_agent_ident=requester_agent_ident,
        surface=surface or "unknown",
        session_id=session_id,
        source_run_id=_uuid.UUID(str(source_run_id)) if source_run_id else None,
        source_block_id=source_block_id,
        approval_group=rule.get("approval_group"),
        approval_type=approval_type,
        status="pending",
        created_at=ts,
        timeout_at=ts + timedelta(seconds=timeout_sec),
    )
    db.add(row)
    db.flush()  # need row.id for audit + fanout

    # Hash-chained audit trail: mark the pause distinctly from a block/warn so
    # SIEMs can count HITL pauses separately.
    try:
        prev_h, entry_h = chain_hash_for_insert(db, ws, ts, tool_name or "guard.approval", "approval_pending")
        pol_h = get_policy_hash(db, ws)
        db.add(GuardAuditEvent(
            workspace_id=ws,
            ai_tool=surface or "unknown",
            tool_call=tool_name,
            source="hook" if surface != "workflow" else "workflow",
            input_summary=(rule.get("message") or "")[:500],
            decision="approval_pending",
            rule_id=row.rule_id,
            rule_message=row.rule_message,
            ts=ts,
            conductai_run_id=str(source_run_id) if source_run_id else None,
            user_email=requester_email,
            previous_hash=prev_h,
            entry_hash=entry_h,
            policy_hash=pol_h,
        ))
    except Exception as exc:  # audit must never break the pause
        log.warning("guard.approval.audit_failed", err=str(exc))
    db.commit()
    db.refresh(row)
    log.info(
        "guard.approval.created",
        request_id=str(row.id),
        workspace_id=str(ws),
        rule_id=row.rule_id,
        surface=row.surface,
        source_run_id=str(source_run_id) if source_run_id else None,
    )
    return row


def dispatch_approval_notifications(
    db: Session,
    request: GuardApprovalRequest,
) -> None:
    """Fan out to every enabled 'approval' channel — reuses the block/warn
    dispatch helpers so we get slack/webhook/pagerduty/email for free.
    Fail-soft: notification errors never block the pause."""
    from app.modules.guard.routers.notifications import resolve_channels
    from app.modules.guard.routers.events import (
        _fanout_slack,
        _fanout_webhook,
        _fanout_pagerduty,
        _fanout_email,
    )

    try:
        channels = resolve_channels(db, request.workspace_id, "approval")
    except Exception as exc:
        log.warning("guard.approval.resolve_channels_failed", err=str(exc))
        return
    if not channels:
        return

    url = approval_url(request.id)
    rule_id = request.rule_id
    summary = request.rule_message or f"Approval required for rule {rule_id}"
    requester = request.requester_email or request.requester_agent_ident or "unknown"
    slack_text = (
        f":raised_hand: *Guard approval required* — `{rule_id}`\n"
        f"• Requester: {requester}\n"
        f"• Surface: `{request.surface}`\n"
        f"• {summary}\n"
        f"• Decide: {url}"
    )
    slack_blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": slack_text}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve"},
                    "style": "primary",
                    "value": f"approve:{request.id}",
                    "action_id": "guard_approve",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Reject"},
                    "style": "danger",
                    "value": f"reject:{request.id}",
                    "action_id": "guard_reject",
                },
            ],
        },
    ]
    email_html = (
        f"<p><strong>Guard approval required</strong> — rule <code>{rule_id}</code></p>"
        f"<p>Requester: {requester}</p>"
        f"<p>Surface: <code>{request.surface}</code></p>"
        f"<p>{summary}</p>"
        f'<p><a href="{url}">Approve or reject in ConductGuard →</a></p>'
    )
    webhook_payload = {
        "event": "guard.approval.requested",
        "request_id": str(request.id),
        "workspace_id": str(request.workspace_id),
        "rule_id": rule_id,
        "rule_pack": request.rule_pack,
        "message": summary,
        "requester": requester,
        "surface": request.surface,
        "source_run_id": str(request.source_run_id) if request.source_run_id else None,
        "url": url,
        "timeout_at": request.timeout_at.isoformat() if request.timeout_at else None,
    }

    by_type: dict[str, list] = {"slack": [], "webhook": [], "pagerduty": [], "email": []}
    for ch in channels:
        by_type.setdefault(ch.channel_type, []).append(ch)
    try:
        if by_type["slack"]:
            _fanout_slack(db, request.workspace_id, by_type["slack"], slack_text, blocks=slack_blocks)
        if by_type["webhook"]:
            _fanout_webhook(by_type["webhook"], webhook_payload)
        if by_type["pagerduty"]:
            _fanout_pagerduty(by_type["pagerduty"], "approval", rule_id, slack_text)
        if by_type["email"]:
            _fanout_email(
                db, request.workspace_id, by_type["email"],
                subject=f"[Guard approval] {rule_id}",
                html=email_html,
            )
    except Exception as exc:
        log.warning("guard.approval.fanout_failed", err=str(exc), request_id=str(request.id))


def pending_marker(request: GuardApprovalRequest) -> str:
    """The exact text an agent surface shows the user when a rule pauses.
    Keep the shape stable — hooks parse it to know a pause happened."""
    mins = max(1, int((request.timeout_at - request.created_at).total_seconds() // 60))
    return (
        f"PENDING approval — {request.rule_message or 'policy requires human approval'}\n"
        f"rule: {request.rule_id}\n"
        f"request: {request.id}\n"
        f"decide: {approval_url(request.id)}\n"
        f"timeout in {mins}m"
    )


def resume_verdict(prior: GuardApprovalRequest | None) -> tuple[str, str | None]:
    """Given a prior approval request for the same (session, rule), return
    the resume verdict for the caller (MCP guard_check, hook, runtime).

    Returns (verdict, block_reason):
      ("proceed", None)      — prior approved, caller returns ok / exit 0
      ("block", reason)      — prior rejected or timed_out, caller returns BLOCKED
      ("wait", None)         — prior still pending, caller returns existing marker
      ("create", None)       — no prior, caller creates a new approval request

    The prior row must already have been passed through sweep_if_timed_out
    so its status is current.
    """
    if prior is None:
        return ("create", None)
    if prior.status == "approved":
        return ("proceed", None)
    if prior.status == "rejected":
        return ("block", "human reviewer rejected this action")
    if prior.status == "timed_out":
        return ("block", "prior approval request timed out — ask a human to re-approve")
    # pending or any other status → keep waiting
    return ("wait", None)


def sweep_if_timed_out(db: Session, row: GuardApprovalRequest, *, now: datetime | None = None) -> GuardApprovalRequest:
    """Lazy timeout: called on every read. If the request is still pending
    past `timeout_at`, mark it timed_out and commit. No background job needed."""
    if row.status != "pending":
        return row
    ts = now or datetime.now(timezone.utc)
    if ts < row.timeout_at:
        return row
    row.status = "timed_out"
    row.decided_at = ts
    row.latency_ms = int((ts - row.created_at).total_seconds() * 1000)
    db.commit()
    db.refresh(row)
    log.info("guard.approval.timed_out", request_id=str(row.id), workspace_id=str(row.workspace_id))
    return row


def can_decide(
    row: GuardApprovalRequest,
    *,
    decider_email: str | None,
    decider_user_id: str | None,
    decider_role: str | None,
) -> tuple[bool, str | None]:
    """Enforce approval_type + peer rule. Permission check happens in the
    endpoint (require_permission); this covers the "who specifically" part."""
    if row.status != "pending":
        return False, f"already {row.status}"

    at = row.approval_type or "any_authorized"
    role = (decider_role or "").lower()
    if at == "any_admin" and role != "admin":
        return False, "only workspace admins can decide this approval"
    if at == "any_security" and role not in ("admin", "security"):
        return False, "only admins or security can decide this approval"

    if at == "peer":
        # 2-person rule — the requester cannot approve themselves. We compare
        # email, then user_id, whichever we have. Missing both means we cannot
        # enforce, so refuse rather than silently allow self-approval.
        req_email = (row.requester_email or "").strip().lower()
        req_uid = (row.requester_user_id or "").strip().lower()
        d_email = (decider_email or "").strip().lower()
        d_uid = (decider_user_id or "").strip().lower()
        if not req_email and not req_uid:
            return False, "peer approval required but requester identity unknown"
        if d_email and req_email and d_email == req_email:
            return False, "peer approval — requester cannot approve themselves"
        if d_uid and req_uid and d_uid == req_uid:
            return False, "peer approval — requester cannot approve themselves"

    return True, None


def apply_decision(
    db: Session,
    row: GuardApprovalRequest,
    *,
    decision: str,
    decider_email: str | None,
    decider_user_id: str | None,
    reason: str | None,
    now: datetime | None = None,
) -> GuardApprovalRequest:
    """Write the decision to the row and its hash-chained audit event.
    Does NOT resume the workflow run — the router handles that so the CAS
    on runs.status stays atomic in one place."""
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'")

    ts = now or datetime.now(timezone.utc)
    row.status = decision
    row.decided_by_email = decider_email
    row.decided_by_user_id = decider_user_id
    row.decided_reason = reason
    row.decided_at = ts
    row.latency_ms = int((ts - row.created_at).total_seconds() * 1000)

    try:
        prev_h, entry_h = chain_hash_for_insert(
            db, row.workspace_id, ts, row.tool_name or "guard.approval", decision,
        )
        pol_h = get_policy_hash(db, row.workspace_id)
        db.add(GuardAuditEvent(
            workspace_id=row.workspace_id,
            ai_tool=row.surface or "unknown",
            tool_call=row.tool_name,
            source="hook" if row.surface != "workflow" else "workflow",
            input_summary=(row.rule_message or "")[:500],
            decision=decision,
            rule_id=row.rule_id,
            rule_message=row.rule_message,
            ts=ts,
            duration_ms=row.latency_ms,
            conductai_run_id=str(row.source_run_id) if row.source_run_id else None,
            user_email=decider_email,
            previous_hash=prev_h,
            entry_hash=entry_h,
            policy_hash=pol_h,
        ))
    except Exception as exc:
        log.warning("guard.approval.decision_audit_failed", err=str(exc))
    db.commit()
    db.refresh(row)
    log.info(
        "guard.approval.decided",
        request_id=str(row.id),
        workspace_id=str(row.workspace_id),
        rule_id=row.rule_id,
        decision=decision,
        decider=decider_email,
        latency_ms=row.latency_ms,
    )
    return row
