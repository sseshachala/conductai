"""Guard gateway — thin orchestrator composing policy + audit + router.

Single entry point for a guarded LLM completion. Both the HTTP proxy handler
(external agents) and the Lens in-process client (dogfood) call
`guarded_completion()` — same policy engine, same audit chain, same upstream
router. Zero network hop between them.

Composed of:
- app.guard.policy.evaluate_composed()  → Decision (rules + budgets + throughput,
                                          #1225 composable engine — was single-source
                                          _policy.evaluate before #1254)
- app.guard.router.upstream()           → Stream (provider fanout)
- app.guard.audit.record()              → hash-chain audit (scheduled as background task)

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
from app.guard.policy import evaluate_composed as _evaluate_composed
from app.guard.policy_types import PolicyAction as _PolicyAction, PolicyContext as _PolicyContext

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
    agent_identity_id: str | None = None,
) -> StreamingResponse | JSONResponse:
    """Evaluate policy, dispatch to upstream if allowed, schedule audit.

    This is the ONE code path that must be true for every LLM call — HTTP
    proxy, Lens, per-tool guard_check. If a caller needs a variant, add a
    parameter here; do not fork the composition."""
    started = time.monotonic()

    # #1254 — composable policy engine (#1225). RulePolicySource inside
    # DEFAULT_SOURCES still calls _policy.evaluate under the hood, so behavior
    # is byte-identical to the pre-refactor _proxy() flow when ctx.db is None
    # (SpendCap + ThroughputCap sources short-circuit ALLOW without a db).
    # When callers eventually thread db + agent_identity_id in, spend caps
    # and throughput caps activate for free.
    _ctx = _PolicyContext(
        workspace_id=workspace_id,
        clerk_user_id=clerk_user_id or None,
        agent_identity_id=agent_identity_id,
        provider=provider,
        model=model,
        body=body,
        input_tokens=0,
        db=None,
    )
    _composed = _evaluate_composed(_ctx)
    decision = Decision(
        action=_composed.action.value,
        rule_id=_composed.rule_id,
        message=_composed.reason,
        matched_rules=_composed.matched_rules,
        defense_score=_composed.defense_score,
        inject_guidance=_composed.inject_guidance,
        guidance=_composed.guidance,
        raw=None,
    )

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
    clerk_user_id: str = "system:lens",
    upstream_api_key: str | None = None,
    vendor_key: str | None = None,
    extra_headers: dict | None = None,
    agent_identity_id: str | None = None,
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
        clerk_user_id=clerk_user_id,
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
        agent_identity_id=agent_identity_id,
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
            # fail_closed emits {"error": {"type": "conduct_guard_proxy",
            # "message": "Blocked by Guard rule <id>: ..."}}; also handle
            # OpenAI-shaped {"error": {"message": ...}} and flat variants.
            _err = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            detail = (
                payload.get("detail")
                or payload.get("message")
                or _err.get("message")
                or _err.get("type")
                or "policy violation"
            )
            # Guard's own fail_closed uses error.type == "conduct_guard_proxy".
            # Any other 4xx/5xx from upstream is a provider error, not a Guard
            # block — must not be labelled as such (misleads users + audit).
            _is_guard_block = _err.get("type") == "conduct_guard_proxy"
            if _is_guard_block:
                raise GuardedLLMBlocked(
                    status=resp.status_code,
                    detail=detail,
                    payload=payload,
                )
            raise LensUpstreamError(
                status=resp.status_code,
                detail=detail,
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


class LensUpstreamError(Exception):
    """Upstream provider (OpenAI/Anthropic/etc) returned a non-2xx.

    Semantically distinct from GuardedLLMBlocked — this is a provider
    error, not a policy denial. Callers should surface it as such and
    NOT prefix it with 'Guard blocked'.
    """

    def __init__(self, *, status: int, detail: str, payload: dict | None = None) -> None:
        self.status = status
        self.detail = detail
        self.payload = payload or {}
        super().__init__(f"upstream HTTP {status}: {detail}")


class GuardedLLMBlocked(Exception):
    """Raised by `guarded_llm_call` when policy or router refuses the call."""

    def __init__(self, *, status: int, detail: str, payload: dict) -> None:
        super().__init__(f"Guard blocked ({status}): {detail}")
        self.status = status
        self.detail = detail
        self.payload = payload


def guarded_client_call(
    *,
    client,
    workspace_id: str,
    provider: str,
    model: str,
    messages: list[dict],
    system: str,
    tools: list[dict] | None = None,
    max_tokens: int = 1024,
    ai_tool: str = "lens",
    clerk_user_id: str = "system:lens",
    agent_identity_id: str | None = None,
    prompt_summary: str = "",
    user_email: str | None = None,
):
    """Policy-checked LLMClient.create — same policy engine as guarded_completion.

    In-process, non-streaming. No self-HTTP hop. Audit written inline via
    `record()` because there's no request lifecycle to defer to.

    Vendor-neutral: `client` is any LLMClient (Anthropic/OpenAI/Perplexity/
    Together/…). Provider + model + api_key come from the caller's LLM
    config factory, which reads workspace primitives + vault (see
    workspace_llm_primitives and app.core.credentials.get_credential)."""
    import time as _time
    import json as _json
    from app.guard.policy import evaluate_composed as _eval_composed
    from app.guard.policy_types import PolicyAction as _PolicyAction, PolicyContext as _PolicyContext

    started = _time.monotonic()
    body = {
        "model": model, "messages": messages, "system": system,
        "tools": tools, "max_tokens": max_tokens,
    }

    ctx = _PolicyContext(
        workspace_id=workspace_id,
        clerk_user_id=clerk_user_id or None,
        agent_identity_id=agent_identity_id,
        provider=provider,
        model=model,
        body=body,
        input_tokens=0,
        db=None,
    )
    composed = _eval_composed(ctx)

    if composed.action == _PolicyAction.BLOCK:
        try:
            _record_audit(
                workspace_id, clerk_user_id or "", ai_tool, provider, model,
                "blocked", composed.rule_id,
                int((_time.monotonic() - started) * 1000),
                body=body, response_bytes=None,
                prompt_summary=prompt_summary, user_email=user_email,
            )
        except Exception as e:
            log.warning("guarded_client_call.audit_block_failed", err=str(e))
        raise GuardedLLMBlocked(
            status=403,
            detail=f"Blocked by Guard rule {composed.rule_id}: {composed.reason or 'policy violation'}",
            payload={},
        )

    resp = client.create(
        model=model, messages=messages, system=system,
        tools=tools, max_tokens=max_tokens,
    )

    try:
        synth = _json.dumps({
            "usage": {
                "prompt_tokens": getattr(resp.usage, "input_tokens", 0),
                "completion_tokens": getattr(resp.usage, "output_tokens", 0),
            }
        }).encode()
        _record_audit(
            workspace_id, clerk_user_id or "", ai_tool, provider, model,
            "allowed", composed.rule_id,
            int((_time.monotonic() - started) * 1000),
            body=body, response_bytes=synth,
            prompt_summary=prompt_summary, user_email=user_email,
        )
    except Exception as e:
        log.warning("guarded_client_call.audit_allow_failed", err=str(e))

    return resp


def guarded_client_stream(
    *,
    client,
    workspace_id: str,
    provider: str,
    model: str,
    messages: list[dict],
    system: str,
    max_tokens: int = 1024,
    on_token=None,
    ai_tool: str = "lens",
    clerk_user_id: str = "system:lens",
    agent_identity_id: str | None = None,
    prompt_summary: str = "",
    user_email: str | None = None,
) -> str:
    """Policy-checked LLMClient.stream — text-only synthesis path.

    Same policy engine as `guarded_completion` / `guarded_client_call`. Text
    deltas flow through `on_token(delta)` as they arrive; the accumulated
    full text is returned. Audit is written at the end (streaming path
    doesn't give us exact output-token counts without SDK-specific hooks —
    left as 0; a follow-up can post-tokenize)."""
    import time as _time
    from app.guard.policy import evaluate_composed as _eval_composed
    from app.guard.policy_types import PolicyAction as _PolicyAction, PolicyContext as _PolicyContext

    started = _time.monotonic()
    body = {
        "model": model, "messages": messages, "system": system,
        "max_tokens": max_tokens, "stream": True,
    }

    ctx = _PolicyContext(
        workspace_id=workspace_id,
        clerk_user_id=clerk_user_id or None,
        agent_identity_id=agent_identity_id,
        provider=provider,
        model=model,
        body=body,
        input_tokens=0,
        db=None,
    )
    composed = _eval_composed(ctx)

    if composed.action == _PolicyAction.BLOCK:
        try:
            _record_audit(
                workspace_id, clerk_user_id or "", ai_tool, provider, model,
                "blocked", composed.rule_id,
                int((_time.monotonic() - started) * 1000),
                body=body, response_bytes=None,
                prompt_summary=prompt_summary, user_email=user_email,
            )
        except Exception as e:
            log.warning("guarded_client_stream.audit_block_failed", err=str(e))
        raise GuardedLLMBlocked(
            status=403,
            detail=f"Blocked by Guard rule {composed.rule_id}: {composed.reason or 'policy violation'}",
            payload={},
        )

    parts: list[str] = []
    for delta in client.stream(
        model=model, messages=messages, system=system, max_tokens=max_tokens
    ):
        if not delta:
            continue
        parts.append(delta)
        if on_token is not None:
            try:
                on_token(delta)
            except Exception as e:
                log.warning("guarded_client_stream.on_token_failed", err=str(e))
    text = "".join(parts)

    try:
        _record_audit(
            workspace_id, clerk_user_id or "", ai_tool, provider, model,
            "allowed", composed.rule_id,
            int((_time.monotonic() - started) * 1000),
            body=body, response_bytes=None,
            prompt_summary=prompt_summary, user_email=user_email,
        )
    except Exception as e:
        log.warning("guarded_client_stream.audit_allow_failed", err=str(e))

    return text


def guarded_llm_stream(
    *,
    workspace_id: str,
    provider: str,
    model: str,
    upstream_url: str,
    api_key: str,
    messages: list[dict],
    system: str,
    max_tokens: int,
    on_token,
    ai_tool: str = "lens",
    clerk_user_id: str = "system:lens",
    db=None,
    agent_identity_id: str | None = None,
) -> str:
    """Streaming, in-process sibling of `guarded_llm_call` for OpenAI-shape SSE.

    Extracted from GLens `_stream_synthesis` in #1254 so any in-process caller
    (Lens Phase 2, future agents) can drive a guard-enforced streaming
    completion without reinventing the policy/audit dance.

    Uses the composable engine (evaluate_composed, #1225). guarded_completion
    was promoted to the same engine in this PR, so Phase 1 (guarded_llm_call
    → guarded_completion) and Phase 2 (guarded_llm_stream) now share one
    policy engine end-to-end.

    Returns the accumulated full_text; raises on BLOCK.
    """
    import json as _json
    import time as _time

    import httpx as _httpx

    from app.guard.audit import record as _record_audit
    from app.guard.policy import evaluate_composed as _eval_composed
    from app.guard.policy_types import PolicyAction as _PolicyAction, PolicyContext as _PolicyContext

    oai_messages = [{"role": "system", "content": system}, *messages]
    payload: dict = {
        "model": model,
        "messages": oai_messages,
        "max_tokens": max_tokens,
        "stream": True,
    }

    t_start = _time.monotonic()
    ctx = _PolicyContext(
        workspace_id=workspace_id,
        clerk_user_id=clerk_user_id,
        agent_identity_id=agent_identity_id,
        provider=provider,
        model=model,
        body=payload,
        input_tokens=0,
        db=db,
    )
    decision = _eval_composed(ctx)

    if decision.action == _PolicyAction.BLOCK:
        try:
            _record_audit(
                workspace_id, clerk_user_id, ai_tool, provider, model,
                "blocked", decision.rule_id, 0,
                body=payload, response_bytes=None,
                prompt_summary=f"{ai_tool}.stream",
                evaluated_rules=decision.matched_rules,
                defense_score=decision.defense_score,
            )
        except Exception:
            pass
        raise Exception(
            f"Guard blocked {ai_tool} call: {decision.reason or decision.rule_id}"
        )

    resp_bytes = bytearray()
    full_text = ""
    with _httpx.stream(
        "POST",
        f"{upstream_url}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    ) as r:
        if r.status_code >= 400:
            body = r.read().decode()[:500]
            raise Exception(f"Upstream stream {r.status_code}: {body}")
        for line in r.iter_lines():
            line_bytes = line.encode() if isinstance(line, str) else line
            resp_bytes.extend(line_bytes)
            resp_bytes.extend(b"\n")
            if not line or line == "data: [DONE]":
                continue
            if line.startswith("data: "):
                try:
                    chunk = _json.loads(line[6:])
                    token = ((chunk.get("choices") or [{}])[0]).get("delta", {}).get("content") or ""
                    if token:
                        full_text += token
                        on_token(token)
                except Exception:
                    pass

    total_ms = int((_time.monotonic() - t_start) * 1000)

    try:
        _record_audit(
            workspace_id, clerk_user_id, ai_tool, provider, model,
            "warned" if decision.action == _PolicyAction.WARN else "allowed",
            decision.rule_id if decision.action == _PolicyAction.WARN else None,
            total_ms,
            body=payload, response_bytes=bytes(resp_bytes),
            prompt_summary=f"{ai_tool}.stream",
            evaluated_rules=decision.matched_rules,
            defense_score=decision.defense_score,
        )
    except Exception as e:
        log.warning("guarded_llm_stream.audit_failed", err=str(e))

    return full_text or ""
