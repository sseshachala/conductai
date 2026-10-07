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


# ─── ai_tool detection (per-tool budget enforcement, #1965 follow-up) ────────
#
# Populated at proxy entry so PolicyContext.ai_tool feeds SpendCapPolicySource,
# which scopes budget lookups per-tool when a matching row exists.
#
# Trust model: this is administrative visibility, NOT adversarial enforcement.
# A malicious client that lies about its identity in the header or UA can be
# labeled as whatever they want. The workspace-wide hard_limit_usd remains the
# absolute ceiling — see PR body for the honest scope note.
#
# Adding a new tool: append its key to config/ai_tools.json (already the
# canonical list for the Per-tool caps UI). This function reads that same
# file so there is one source of truth.

import json as _json_ai_tool
from pathlib import Path as _Path_ai_tool
from functools import lru_cache as _lru_cache_ai_tool
from app.guard.gateway_errors import (  # noqa: F401 — re-exports
    GuardedLLMBlocked, LensUpstreamError, _safe_loads,
)
from app.guard.gateway_stream import (  # noqa: F401 — re-exports
    guarded_client_stream, guarded_llm_stream,
)


@_lru_cache_ai_tool(maxsize=1)
def _known_ai_tools() -> tuple[str, ...]:
    """Load the canonical AI tool key list from config/ai_tools.json.

    Cached — the file is read once per process. Returns an empty tuple if
    the file is missing (dev containers built before it existed).
    """
    root = _Path_ai_tool(__file__).resolve()
    # Walk up to repo root (apps/api/app/guard/gateway.py → 5 levels).
    for _ in range(5):
        root = root.parent
    cfg = root / "config" / "ai_tools.json"
    try:
        raw = _json_ai_tool.loads(cfg.read_text())
        tools = raw.get("tools") or []
        return tuple(t for t in tools if isinstance(t, str))
    except Exception:
        return ()


def detect_ai_tool(headers) -> str:
    """Return an ai_tool key inferred from request headers.

    Precedence:
      1. Explicit X-Conduct-Ai-Tool header wins (self-labeling client).
      2. First substring match against known keys in the User-Agent.
      3. Fall back to "unknown" — SpendCapPolicySource treats that as
         "no per-tool row match", so workspace + user caps still apply.

    Accepts either a starlette Headers instance or any mapping with a
    case-insensitive .get. Passing a plain dict works too.
    """
    def _get(name: str) -> str:
        try:
            v = headers.get(name)
        except Exception:
            v = None
        return (v or "").strip()

    explicit = _get("x-conduct-ai-tool").lower()
    if explicit:
        return explicit

    ua = _get("user-agent").lower()
    if ua:
        for key in _known_ai_tools():
            if key in ua:
                return key

    log.info("guard.gateway.ai_tool_unknown", user_agent=ua[:80])
    return "unknown"


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
    is_trial: bool = False,
) -> StreamingResponse | JSONResponse:
    """Evaluate policy, dispatch to upstream if allowed, schedule audit.

    This is the ONE code path that must be true for every LLM call — HTTP
    proxy, Lens, per-tool guard_check. If a caller needs a variant, add a
    parameter here; do not fork the composition."""
    import uuid as _uuid
    from app.guard.receipts import build_receipt_url as _build_receipt_url
    from app.guard.receipts import mint_share_token as _mint_share_token

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
        gate="prompt",  # #1733: outbound LLM proxy egress
        ai_tool=ai_tool,
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
        _receipt_id = str(_uuid.uuid4())
        _share_token: str | None = None
        _share_token_hash: str | None = None
        if is_trial:
            _share_token, _share_token_hash = _mint_share_token()
        _receipt_url = _build_receipt_url(_receipt_id, _share_token)
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
            receipt_id=_receipt_id,
            share_token_hash=_share_token_hash,
            agent_identity_id=agent_identity_id,
        )
        return _router.fail_closed(
            403,
            f"Blocked by Guard rule {decision.rule_id}: {decision.message or 'policy violation'}"
            f"\n→ Receipt: {_receipt_url}",
            extra={"receipt_id": _receipt_id, "receipt_url": _receipt_url},
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
    hook_session_id: str | None = None,
    is_trial: bool = False,
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
        hook_session_id=hook_session_id,
        is_trial=is_trial,
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
    hook_session_id: str | None = None,
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
        gate="prompt",  # #1733: outbound LLM proxy egress
        ai_tool=ai_tool,
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
                hook_session_id=hook_session_id,
            
            agent_identity_id=agent_identity_id,
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
            hook_session_id=hook_session_id,
        
        agent_identity_id=agent_identity_id,
        )
    except Exception as e:
        log.warning("guarded_client_call.audit_allow_failed", err=str(e))

    # #2209 — Lens attempt-receipt write. shadow_write catches every
    # exception internally so a failed write never breaks the caller.
    try:
        import uuid as _uuid_shadow
        from app.runtime.accounting.shadow_writer import shadow_write as _shadow_write
        _shadow_write(
            workspace_id=workspace_id,
            request_id=_uuid_shadow.uuid4(),
            provider=provider,
            model=model,
            operation="chat.completions",
            dispatched=True,
            response_bytes=synth,
            developer_external_id=clerk_user_id,
            agent_identity_id=agent_identity_id,
            hook_session_id=hook_session_id,
            source="lens",
            client_tool=ai_tool,
        )
    except Exception:
        pass

    return resp


