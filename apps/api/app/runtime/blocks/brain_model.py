"""Brain block model-call phase: run context, LLM call, accounting, single turn.

Extracted from ``brain_block._execute_brain`` (#2400). ``BrainRun``
carries everything the phases share. Names tests patch on
``app.runtime.blocks.brain_block`` (``_cache_get`` / ``_cache_set`` /
``_load_workspace_mcp_tools``) are looked up there by ``_execute_brain``
and handed in through ``BrainRun``, so those patches keep applying.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import structlog

from app.runtime.llm_client import LLMTextBlock, LLMUpstreamError

# Same logger name as before the split so worker log routing is unchanged.
log = structlog.get_logger("app.runtime.blocks.brain_block")


@dataclass
class BrainRun:
    """Per-invocation state shared by the brain block phases."""

    block: dict
    state: dict
    db: Any
    run_id: str | None
    block_id: str | None
    playbook_slug: str | None
    workspace_id: str
    workflow_id: str | None
    user_email: str | None
    environment_id: str | None
    attempt_id: str | None
    resume_from_turn: int
    # Helpers resolved by _execute_brain at call time (patch-sensitive).
    emit: Callable
    write_trace: Callable
    summarise_tool_call: Callable
    clarification_required: type
    cache_get: Callable
    cache_set: Callable
    load_mcp_tools: Callable
    # Sandbox session + credential dispatch.
    session: Any
    close_session: Callable[[], None]
    dispatch_with_creds: Callable[[str, dict], str]
    remote_host: dict | None
    # Prompts.
    system_prompt: str
    user_message: str
    # Model routing.
    llm: Any
    provider: str
    model_id: str
    routing_reason: str
    pricing_rates: Any
    pricing_version: Any
    proxy_url: str
    env_vars: dict


def extract_last_json_object(text: str) -> dict | None:
    """
    Find the last well-formed JSON object in text.
    Handles three cases: compact JSON on last line, whole output is JSON,
    and prose followed by a multi-line JSON block.
    """
    text = text.strip()
    # 1. Last line (compact single-line JSON)
    last_line = text.rsplit("\n", 1)[-1].strip()
    if last_line.startswith("{") and last_line.endswith("}"):
        try:
            obj = json.loads(last_line)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    # 2. Whole output is JSON (multi-line, no prose prefix)
    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    # 3. Prose + trailing JSON block — brace-match from the last closing brace
    last_close = text.rfind("}")
    if last_close != -1:
        depth = 0
        for i in range(last_close, -1, -1):
            if text[i] == "}":
                depth += 1
            elif text[i] == "{":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[i : last_close + 1])
                        if isinstance(obj, dict):
                            return obj
                    except Exception:
                        pass
                    break
    return None


def record_turns(db, run_id: str | None, actual: int, exhausted: bool) -> None:
    """Persist actual_turns + budget_exhausted on the Run row for future estimation."""
    if not db or not run_id:
        return
    try:
        from app.models.run import Run as _Run
        db.query(_Run).filter(_Run.id == run_id).update(
            {"actual_turns": actual, "budget_exhausted": exhausted},
            synchronize_session=False,
        )
        db.commit()
    except Exception:
        pass  # never block the run on telemetry writes


def cached_response(r: BrainRun, turn: int):
    """Replay a cached LLM response for ``turn`` (cost zeroed), or None."""
    _cached = r.cache_get(r.run_id, r.block_id, turn)
    if _cached is None:
        return None
    from app.runtime.llm_client import LLMResponse as _LLMResponse
    response = _LLMResponse.from_cache_dict(_cached)
    response.cost_usd = 0.0  # ponytail: no charge on replay
    log.debug("brain.llm_cache_hit", run_id=r.run_id, block_id=r.block_id, turn=turn)
    return response


def _retry_params(r: BrainRun, turn: int):
    """``(idempotency_key, on_retry, outer_attempt)`` for one LLM call."""
    state, db, run_id, block_id = r.state, r.db, r.run_id, r.block_id
    # Stable idempotency key across our retry attempts within
    # this turn — lets OpenAI dedupe if a request was
    # intercepted mid-flight. Include __for_each_index so
    # iterations of the same block inside for_each don't
    # collide on the provider's dedup window.
    _fe_idx = state.get("__for_each_index")
    _idem_key = (
        f"conduct-{run_id}-{block_id}-{turn}"
        + (f"-fe{_fe_idx}" if _fe_idx is not None else "")
    ) if run_id and block_id else None

    # Emit llm_upstream_retry on each retry attempt so ops
    # can spot infra degradation. Fires only when retry
    # occurs; silent on happy path.
    def _on_retry(info: dict) -> None:
        if db and run_id:
            r.emit(db, run_id, block_id, "llm_upstream_retry", {
                **info, "turn": turn,
                "block_attempt": state.get("__block_attempt", 1),
            })
    # If a future dag_runner block-retry wraps this call, it
    # sets state["__block_attempt"] to N. Passing outer_attempt
    # caps internal retries at 1 when N>1 so 3×3=9 stacked
    # attempts never happen. Silent no-op today (nothing sets
    # __block_attempt).
    _outer_attempt = int(state.get("__block_attempt", 1))
    return _idem_key, _on_retry, _outer_attempt


def call_llm(r: BrainRun, turn: int, *, agentic: bool, **create_kwargs):
    """One ``llm.create`` call; closes the session and re-raises on failure.

    ``agentic`` keeps the two original paths exact: the agentic loop
    builds its retry params inside the ``try`` and logs
    ``brain.llm_call_failed`` on a generic error; the single call
    builds them before the ``try`` and does not log.
    """
    if not agentic:
        _idem_key, _on_retry, _outer_attempt = _retry_params(r, turn)
    try:
        if agentic:
            _idem_key, _on_retry, _outer_attempt = _retry_params(r, turn)
        return r.llm.create(
            **create_kwargs,
            idempotency_key=_idem_key,
            on_retry=_on_retry,
            outer_attempt=_outer_attempt,
        )
    except LLMUpstreamError as _up_err:
        # CF/Render/WAF intercepted. Emit a structured event with
        # cf-ray + render request ID BEFORE re-raising — the raise
        # goes into block_failed via str(exc) which is short and clean.
        # is_final marks this as the terminal adapter failure; if a
        # future dag_runner block-retry wraps this call and later
        # succeeds, consumers can filter for is_final events only.
        if r.db and r.run_id:
            r.emit(r.db, r.run_id, r.block_id, "llm_upstream_blocked", {
                "provider": _up_err.provider,
                "status": _up_err.status,
                "content_type": _up_err.content_type,
                "attempts": _up_err.attempts,
                "cf_ray": _up_err.cf_ray,
                "render_request_id": _up_err.request_id,
                "body_snippet": _up_err.body_snippet,
                "turn": turn,
                "base_url": r.proxy_url,
                "is_final": True,
                "block_attempt": r.state.get("__block_attempt", 1),
            })
        log.error("brain.llm_upstream_blocked",
                  provider=_up_err.provider, status=_up_err.status,
                  cf_ray=_up_err.cf_ray, render_req=_up_err.request_id,
                  attempts=_up_err.attempts,
                  run_id=r.run_id, block_id=r.block_id)
        r.close_session()  # #2401: don't leak the sandbox
        raise
    except Exception as _llm_err:
        if agentic:
            _cause = getattr(_llm_err, "__cause__", None) or getattr(_llm_err, "__context__", None)
            log.error("brain.llm_call_failed",
                      error=str(_llm_err), cause=str(_cause),
                      base_url=r.proxy_url, turn=turn,
                      run_id=r.run_id, block_id=r.block_id)
        r.close_session()  # #2401: don't leak the sandbox
        raise


def shadow_account(r: BrainRun, response) -> None:
    """#2209 Session 6b — workflow shadow accounting for one actual LLM call.

    Caller skips this when the adapter routes through Gateway (Session 4
    hook already wrote the receipt) and on cache-hit replay (Reviewer #6
    #2221: no upstream inference, so no receipt). shadow_write is a
    no-op when the workspace is not on the canary allowlist; every
    exception is swallowed.
    """
    try:
        import json as _json_shadow
        import uuid as _uuid_shadow
        from app.runtime.accounting.shadow_writer import (
            shadow_write as _shadow_write,
        )
        if r.provider == "anthropic":
            _synth = _json_shadow.dumps({
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "cache_read_input_tokens": (
                        response.usage.cache_read_tokens
                    ),
                    "cache_creation_input_tokens": (
                        response.usage.cache_write_tokens
                    ),
                }
            }).encode()
        else:
            _synth = _json_shadow.dumps({
                "usage": {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                }
            }).encode()
        # run_id is a Run.id UUID; block_id is a semantic slug.
        # Only run_id maps to a UUID column.
        _wf_run = None
        if r.run_id:
            try:
                _wf_run = _uuid_shadow.UUID(str(r.run_id))
            except (ValueError, TypeError):
                _wf_run = None
        _shadow_write(
            workspace_id=r.workspace_id,
            request_id=_uuid_shadow.uuid4(),
            provider=r.provider,
            model=r.model_id,
            operation="chat.completions",
            dispatched=True,
            response_bytes=_synth,
            workflow_run_id=_wf_run,
            source="workflow_runtime",
            client_tool=str(r.block_id) if r.block_id else None,
        )
    except Exception:
        pass


def run_single_turn(r: BrainRun) -> dict:
    """Single call (no tools): one LLM turn, emit + trace, build result."""
    db, run_id, block_id = r.db, r.run_id, r.block_id
    user_message = r.user_message
    response = cached_response(r, 0)
    if response is None:
        response = call_llm(
            r, 0, agentic=False,
            model=r.model_id,
            max_tokens=2048,
            system=r.system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        r.cache_set(run_id, block_id, 0, response.to_cache_dict())
    text = next((b.text for b in response.content if isinstance(b, LLMTextBlock)), "")
    if db and run_id and block_id:
        r.emit(db, run_id, block_id, "brain_tool_call", {
            "turn": 1,
            "tool": "single_call",
            "summary": text[:300],
            "input": user_message[:600],
            "output": text,
            "model": r.model_id,
            "provider": r.provider,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        })
        r.write_trace(db, run_id, block_id, 1, "user",
                      content=user_message[:8000] if user_message else None)
        r.write_trace(db, run_id, block_id, 1, "assistant",
                      content=text[:8000] if text else None,
                      input_tokens=response.usage.input_tokens,
                      output_tokens=response.usage.output_tokens)
    result = {
        "output": text,
        "turns": 1,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cost_usd": response.cost_usd,
        "provider": r.provider,
        "model": r.model_id,
        "routing_reason": r.routing_reason,
        "pricing_version": r.pricing_version,
        "pricing_rates": r.pricing_rates,
        "upstream_url": r.proxy_url,
        "llm_upstream": r.env_vars.get("PROXY_CONFIG_LLM_UPSTREAM") or None,
    }
    _extracted = extract_last_json_object(result.get("output", ""))
    if _extracted:
        result = {**_extracted, **result}
    record_turns(db, run_id, 1, False)  # #2401: single call is one turn
    r.close_session()
    return result
