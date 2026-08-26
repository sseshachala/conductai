"""Guard gateway — thin orchestrator composing policy + audit + router.

Single entry point for a guarded LLM completion. Both the HTTP proxy handler
(external agents) and the Lens in-process client (dogfood) call
`guarded_completion()` — same policy engine, same audit chain, same upstream
router. Zero network hop between them.

Composed of:
- app.guard.policy.evaluate()    → Decision (rules + budgets)
- app.guard.router.upstream()    → Stream (provider fanout)
- app.guard.audit.record()       → hash-chain audit (scheduled as background task)

Extracted in #1218 Step 2. Behavior mirrors the pre-refactor _proxy() flow;
the regression harness locks that in.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import structlog
from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse

from app.guard import policy as _policy
from app.guard import router as _router
from app.guard.audit import record as _record_audit

log = structlog.get_logger(__name__)


@dataclass
class Decision:
    """Structured output of policy.evaluate — narrower typed view over the
    dict returned today. Callers can migrate to Decision incrementally; the
    orchestrator itself still passes the raw dict through for now to preserve
    byte-parity with existing call sites."""
    action: str                       # ALLOW | WARN | BLOCK | APPROVAL
    rule_id: str | None
    message: str | None
    matched_rules: list[dict]
    defense_score: int
    inject_guidance: bool = False
    guidance: str | None = None
    raw: dict | None = None           # original dict for legacy consumers


def _decision_from_dict(d: dict) -> Decision:
    return Decision(
        action=d.get("action", "ALLOW"),
        rule_id=d.get("rule_id"),
        message=d.get("message"),
        matched_rules=d.get("matched_rules") or [],
        defense_score=int(d.get("defense_score") or 0),
        inject_guidance=bool(d.get("inject_guidance")),
        guidance=d.get("guidance"),
        raw=d,
    )


async def guarded_completion(
    *,
    workspace_id: str,
    clerk_user_id: str,
    ai_tool: str,
    provider: str,
    model: str,
    body: dict,
    upstream_url: str,
    upstream_path: str,
    real_key: str,
    auth_header_out: str,
    bearer: bool,
    is_stream: bool,
    background: BackgroundTasks,
    prompt_summary: str = "",
    user_email: str | None = None,
    upstream_api_key: str | None = None,
    vendor_key: str | None = None,
    extra_headers: dict | None = None,
    conductai_run_id: str | None = None,
    conductai_workflow: str | None = None,
    conductai_workflow_id: str | None = None,
    hook_session_id: str | None = None,
) -> StreamingResponse | JSONResponse:
    """Evaluate policy, dispatch to upstream if allowed, schedule audit.

    This is the ONE code path that must be true for every LLM call — HTTP
    proxy, Lens, per-tool guard_check. If a caller needs a variant, add a
    parameter here; do not fork the composition."""
    started = time.monotonic()

    decision_dict = _policy.evaluate(workspace_id, provider, model, body)
    decision = _decision_from_dict(decision_dict)

    if decision.action == "BLOCK":
        background.add_task(
            _record_audit,
            workspace_id, clerk_user_id, ai_tool, provider, model,
            "blocked", decision.rule_id,
            int((time.monotonic() - started) * 1000),
            body=body, response_bytes=None, upstream=upstream_url,
            prompt_summary=prompt_summary, user_email=user_email,
            conductai_run_id=conductai_run_id,
            conductai_workflow=conductai_workflow,
            conductai_workflow_id=conductai_workflow_id,
            hook_session_id=hook_session_id,
            evaluated_rules=decision.matched_rules,
            defense_score=decision.defense_score,
        )
        return _router.fail_closed(
            403,
            f"Blocked by Guard rule {decision.rule_id}: {decision.message or 'policy violation'}",
        )

    audit_args: tuple[Any, ...] = (
        workspace_id, clerk_user_id, ai_tool, provider, model,
        decision.action.lower(), decision.rule_id,
        started, body,
        prompt_summary, user_email,
        conductai_run_id, conductai_workflow, conductai_workflow_id, hook_session_id,
    )

    return await _router.upstream(
        upstream=upstream_url,
        path=upstream_path,
        body=body,
        real_key=real_key,
        auth_header_out=auth_header_out,
        bearer=bearer,
        is_stream=is_stream,
        background=background,
        audit_args=audit_args,
        extra_headers=extra_headers,
        upstream_api_key=upstream_api_key,
        vendor_key=vendor_key,
        provider=provider,
    )
