"""Guard gateway — streaming entry points (``guarded_client_stream``, ``guarded_llm_stream``).

Same policy + audit + router composition as ``app.guard.gateway``; re-exported there."""

from __future__ import annotations

import structlog
from app.guard.audit import record as _record_audit
from app.guard.gateway_errors import (
    GuardedLLMBlocked,
)

log = structlog.get_logger("app.guard.gateway")


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
    hook_session_id: str | None = None,
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
            log.warning("guarded_client_stream.audit_block_failed", err=str(e))
        raise GuardedLLMBlocked(
            status=403,
            detail=f"Blocked by Guard rule {composed.rule_id}: {composed.reason or 'policy violation'}",
            payload={},
        )

    # #2209 Session 6F reviewer #5 (#2221 review at 1219d734): the
    # shadow-write MUST happen in a finally block. An upstream exception
    # mid-stream would otherwise drop the receipt even when
    # ``client.last_usage`` already holds real billable usage from
    # message_start / partial delta frames. Capture PARTIAL usage on
    # failure so provider-side billing is still visible on the row.
    parts: list[str] = []
    _stream_completed_normally = False
    _stream_exc: BaseException | None = None
    try:
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
                    log.warning(
                        "guarded_client_stream.on_token_failed", err=str(e)
                    )
        _stream_completed_normally = True
    except BaseException as _exc:  # noqa: BLE001
        _stream_exc = _exc
        raise
    finally:
        _last_usage = getattr(client, "last_usage", None)
        # #2209 Session 6G reviewer #1 (#2221 review at 42d89898):
        # ``last_usage_final`` distinguishes "captured message_start
        # only" from "captured the terminal message_delta / OpenAI
        # usage frame". Without this a mid-stream interruption
        # synthesizes JSON with input=100, output=0 that the normalizer
        # correctly marks COMPLETE (invariant #4: zero is legitimate) —
        # but for streaming context we KNOW that's partial data.
        _last_usage_final = bool(getattr(client, "last_usage_final", False))
        _shadow_bytes = None
        if isinstance(_last_usage, dict):
            try:
                import json as _json_shadow
                _shadow_bytes = _json_shadow.dumps(
                    {"usage": _last_usage}
                ).encode()
            except Exception:
                _shadow_bytes = None
        try:
            import uuid as _uuid_shadow
            from app.runtime.accounting.shadow_writer import (
                shadow_write as _shadow_write,
            )
            from app.runtime.accounting.contracts import (
                ExecutionOutcome,
                UsageCompleteness,
            )
            # If the stream completed normally AND we saw the terminal
            # usage frame → COMPLETE. Any other combination is PARTIAL
            # (we have some usage but the frame we needed didn't arrive).
            # UNAVAILABLE stays for the "no usage at all" case which the
            # writer handles when _shadow_bytes is None.
            if _shadow_bytes is None:
                _completeness_override = None  # writer picks UNAVAILABLE
            elif _stream_completed_normally and _last_usage_final:
                _completeness_override = UsageCompleteness.COMPLETE.value
            else:
                _completeness_override = UsageCompleteness.PARTIAL.value
            _shadow_write(
                workspace_id=workspace_id,
                request_id=_uuid_shadow.uuid4(),
                provider=provider,
                model=model,
                operation="chat.completions",
                dispatched=True,
                response_bytes=_shadow_bytes,
                developer_external_id=clerk_user_id,
                agent_identity_id=agent_identity_id,
                hook_session_id=hook_session_id,
                source="lens",
                client_tool=ai_tool,
                # Reviewer #5 (Session 6F): explicit outcome + succeeded
                # so usage completeness stays separate from execution
                # status.
                succeeded=_stream_completed_normally,
                execution_outcome=(
                    ExecutionOutcome.SUCCEEDED.value
                    if _stream_completed_normally
                    else ExecutionOutcome.DISCONNECTED.value
                ),
                usage_completeness_override=_completeness_override,
            )
        except Exception:
            # Shadow write is best-effort; never re-raise from finally.
            pass

    text = "".join(parts)

    try:
        _record_audit(
            workspace_id, clerk_user_id or "", ai_tool, provider, model,
            "allowed", composed.rule_id,
            int((_time.monotonic() - started) * 1000),
            body=body, response_bytes=None,
            prompt_summary=prompt_summary, user_email=user_email,
            hook_session_id=hook_session_id,

        agent_identity_id=agent_identity_id,
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
    hook_session_id: str | None = None,
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
        gate="prompt",  # #1733: outbound LLM proxy egress
        ai_tool=ai_tool,
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
                hook_session_id=hook_session_id,
            
            agent_identity_id=agent_identity_id,
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
            hook_session_id=hook_session_id,
        
        agent_identity_id=agent_identity_id,
        )
    except Exception as e:
        log.warning("guarded_llm_stream.audit_failed", err=str(e))

    return full_text or ""
