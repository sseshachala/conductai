"""Decision → response helpers for the composable engine migration.

Reconstructs the pre-refactor error envelopes from a PolicyDecision so
_proxy() can call evaluate_composed() with byte-parity. See #1225 Phase 4.
"""
from __future__ import annotations

import time
import uuid

from fastapi.responses import JSONResponse

from app.core.database import SessionLocal


def render_block(
    decision, background, workspace_id, clerk_user_id, ai_tool, provider,
    model, body, prompt_summary, user_email, run_id, workflow,
    workflow_id, hook_session_id, started, record_audit_fn, fail_closed_fn,
    *, is_trial: bool = False,
):
    from app.guard.receipts import build_receipt_url, mint_share_token

    source = decision.source
    extras = decision.extras or {}
    duration_ms = int((time.monotonic() - started) * 1000)

    # Pre-mint the audit row id so the response can carry a link to it
    # before the background audit write completes. Trial rows also get a
    # short-lived share token so anonymous signup users can view their
    # own receipt without logging in.
    receipt_id = str(uuid.uuid4())
    share_token: str | None = None
    share_token_hash: str | None = None
    if is_trial:
        share_token, share_token_hash = mint_share_token()
    receipt_url = build_receipt_url(receipt_id, share_token)

    def _audit(decision_str: str, rule_id: str | None, *, with_verdict: bool):
        kwargs = dict(
            body=body, response_bytes=None,
            prompt_summary=prompt_summary, user_email=user_email,
            conductai_run_id=run_id, conductai_workflow=workflow,
            conductai_workflow_id=workflow_id, hook_session_id=hook_session_id,
            receipt_id=receipt_id,
            share_token_hash=share_token_hash,
        )
        if with_verdict:
            kwargs["evaluated_rules"] = decision.matched_rules
            kwargs["defense_score"] = decision.defense_score
        background.add_task(
            record_audit_fn, workspace_id, clerk_user_id, ai_tool, provider, model,
            decision_str, rule_id, duration_ms, **kwargs,
        )

    # Embed the receipt URL in the message itself so every SDK that raises
    # on `error.message` (Anthropic, OpenAI, LiteLLM, LangChain, raw curl)
    # surfaces the link with zero per-integration wiring. Structured fields
    # stay next to it for plugins that want machine-readable access.
    def _with_receipt(msg: str | None) -> str:
        base = msg or "Blocked by policy"
        return f"{base}\n→ Receipt: {receipt_url}"

    if source == "rule":
        _audit("blocked", decision.rule_id, with_verdict=True)
        err = {
            "type": "guard_block",
            "message": _with_receipt(decision.reason),
            "rule": decision.rule_id,
            "matched_rules": decision.matched_rules,
            "defense_score": decision.defense_score,
            "receipt_id": receipt_id,
            "receipt_url": receipt_url,
        }
        if decision.inject_guidance and decision.guidance:
            err["guidance"] = decision.guidance
        return JSONResponse(status_code=403, content={"error": err})

    if source == "spend_cap":
        _audit("budget_exceeded", None, with_verdict=False)
        return JSONResponse(
            status_code=429,
            content={"error": {
                "type": "guard_budget_exceeded",
                "message": _with_receipt(decision.reason or "Monthly AI budget reached."),
                "monthly_cost_usd": extras.get("monthly_cost_usd"),
                "hard_limit_usd": extras.get("hard_limit_usd"),
                "receipt_id": receipt_id,
                "receipt_url": receipt_url,
            }},
        )

    if source == "throughput_cap":
        _audit("rate_limited", None, with_verdict=False)
        return JSONResponse(
            status_code=429,
            content={"error": {
                "type": "guard_rate_limited",
                "message": _with_receipt(decision.reason),
                "metric": extras.get("metric"),
                "limit": extras.get("limit"),
                "current": extras.get("current"),
                "scope": extras.get("scope"),
                "receipt_id": receipt_id,
                "receipt_url": receipt_url,
            }},
        )

    return fail_closed_fn(
        403,
        _with_receipt(decision.reason or "Blocked by policy"),
        extra={"receipt_id": receipt_id, "receipt_url": receipt_url},
    )


def render_approval(
    decision, background, workspace_id, clerk_user_id, ai_tool, provider,
    model, body, prompt_summary, user_email, run_id, workflow,
    workflow_id, hook_session_id, started, record_audit_fn,
):
    from app.modules.guard.models import GuardApprovalRequest as _GAR
    from app.modules.guard import approval as _approval
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    extras = decision.extras or {}
    rule_dict = extras.get("rule") or {"id": decision.rule_id, "message": decision.reason}
    duration_ms = int((time.monotonic() - started) * 1000)

    _db2 = SessionLocal()
    try:
        cutoff = _dt.now(_tz.utc) - _td(minutes=5)
        existing = _db2.query(_GAR).filter(
            _GAR.workspace_id == uuid.UUID(workspace_id),
            _GAR.rule_id == decision.rule_id,
            _GAR.requester_user_id == (clerk_user_id or ""),
            _GAR.status == "pending",
            _GAR.created_at >= cutoff,
        ).first() if clerk_user_id else None

        if existing is None:
            req = _approval.create_approval_request(
                _db2,
                workspace_id=workspace_id,
                rule=rule_dict,
                tool_name=f"llm.{provider}",
                tool_input={"model": model, "prompt": prompt_summary},
                requester_email=user_email,
                requester_user_id=clerk_user_id,
                surface="proxy",
                session_id=hook_session_id,
                source_run_id=run_id,
            )
            _approval.dispatch_approval_notifications(_db2, req)
        else:
            req = existing

        background.add_task(
            record_audit_fn, workspace_id, clerk_user_id, ai_tool, provider, model,
            "approval_pending", decision.rule_id, duration_ms,
            body=body, response_bytes=None,
            prompt_summary=prompt_summary, user_email=user_email,
            conductai_run_id=run_id, conductai_workflow=workflow,
            conductai_workflow_id=workflow_id, hook_session_id=hook_session_id,
            evaluated_rules=decision.matched_rules,
            defense_score=decision.defense_score,
        )
        return JSONResponse(
            status_code=428,
            content={"error": {
                "type": "guard_approval_required",
                "message": decision.reason or "Human approval required by policy.",
                "rule": decision.rule_id,
                "approval_request_id": str(req.id),
                "approval_url": _approval.approval_url(req.id),
                "pending_marker": _approval.pending_marker(req),
                "matched_rules": decision.matched_rules,
                "defense_score": decision.defense_score,
            }},
        )
    finally:
        _db2.close()
