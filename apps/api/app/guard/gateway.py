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


async def guarded_llm_call(
    *,
    workspace_id: str,
    provider: str,
    model: str,
    body: dict,
    upstream_url: str,
    upstream_path: str,
    real_key: str,
    auth_header_out: str = "Authorization",
    bearer: bool = True,
    ai_tool: str = "lens",
    prompt_summary: str = "lens",
    user_email: str | None = None,
    upstream_api_key: str | None = None,
    vendor_key: str | None = None,
    extra_headers: dict | None = None,
) -> dict:
    """In-process, non-streaming Lens sibling of `guarded_completion`.

    Not a fork — this wraps `guarded_completion` (same policy engine, same
    audit chain, same upstream router). It exists so in-process callers like
    Lens can get the raw upstream JSON dict back and adapt it to their SDK
    shape, instead of receiving a FastAPI JSONResponse meant for HTTP wire.

    Zero self-HTTP hop: the underlying `_router.upstream` uses httpx directly.

    Raises on BLOCK (policy denial) or upstream error.
    """
    import asyncio as _asyncio
    import json as _json

    from fastapi import BackgroundTasks as _BackgroundTasks
    background = _BackgroundTasks()

    resp = await guarded_completion(
        workspace_id=workspace_id,
        clerk_user_id="",
        ai_tool=ai_tool,
        provider=provider,
        model=model,
        body=body,
        upstream_url=upstream_url,
        upstream_path=upstream_path,
        real_key=real_key,
        auth_header_out=auth_header_out,
        bearer=bearer,
        is_stream=False,
        background=background,
        prompt_summary=prompt_summary,
        user_email=user_email,
        upstream_api_key=upstream_api_key,
        vendor_key=vendor_key,
        extra_headers=extra_headers,
    )

    # Drive the scheduled audit writes now — no request lifecycle to run them for us.
    try:
        await background()
    except Exception as e:
        log.warning("guarded_llm_call.background_failed", err=str(e))

    if isinstance(resp, JSONResponse):
        raw_body = resp.body if isinstance(resp.body, (bytes, bytearray)) else b""
        if resp.status_code >= 400:
            payload = _safe_loads(raw_body)
            raise GuardedLLMBlocked(
                status=resp.status_code,
                detail=payload.get("detail") or payload.get("message") or "policy violation",
                payload=payload,
            )
        return _safe_loads(raw_body)

    raise Exception(
        "guarded_llm_call currently supports non-streaming responses only; "
        "callers needing streams should call guarded_completion(is_stream=True) "
        "and drive the StreamingResponse directly."
    )


def _safe_loads(raw: bytes) -> dict:
    import json as _json
    try:
        return _json.loads(raw or b"{}")
    except Exception:
        return {}


class GuardedLLMBlocked(Exception):
    """Raised by `guarded_llm_call` when policy or router refuses the call."""

    def __init__(self, *, status: int, detail: str, payload: dict) -> None:
        super().__init__(f"Guard blocked ({status}): {detail}")
        self.status = status
        self.detail = detail
        self.payload = payload
