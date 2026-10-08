"""Characterization: ``_execute_brain`` single-call (non-agentic) mode (#2400).

Pins the returned dict, the Gateway-profile client wiring, emitted run
events / traces, and the refusal paths, so the #2400 refactor can prove
no behavior change.
"""
from __future__ import annotations

import copy

import pytest

from app.core.config import settings
from app.runtime.llm_client import LLMUpstreamError
from tests.runtime.brain_block_harness import (
    BLOCK_ID,
    MODEL,
    PROVIDER,
    ROUTING_REASON,
    RUN_ID,
    WORKFLOW_ID,
    WORKSPACE_ID,
    base_state,
    brain_block,
    brain_harness,
    expected_pricing,
    run_brain,
    text_response,
)

PROXY_URL = settings.conduct_proxy_url.rstrip("/")


def _upstream_error() -> LLMUpstreamError:
    return LLMUpstreamError(
        provider="gateway_profile", status=503, content_type="text/html",
        body_snippet="<html>blocked</html>", cf_ray="ray-1",
        request_id="req-1", attempts=3,
    )


def test_single_turn_json_happy_path():
    out_text = 'Done.\n{"verdict": "ok", "pr_url": "https://x/pr/1", "model": "llm-says"}'
    state = base_state()
    before = copy.deepcopy(state)
    with brain_harness([text_response(out_text, cost=0.0025, inp=12, out=7)]) as h:
        result = run_brain(h, brain_block(agentic=False), state)

    rates, version = expected_pricing()
    assert result == {
        "verdict": "ok",
        "pr_url": "https://x/pr/1",
        # runtime telemetry keys win over keys extracted from LLM JSON
        "model": MODEL,
        "output": out_text,
        "turns": 1,
        "input_tokens": 12,
        "output_tokens": 7,
        "cost_usd": 0.0025,
        "provider": PROVIDER,
        "routing_reason": ROUTING_REASON,
        "pricing_version": version,
        "pricing_rates": rates,
        "upstream_url": PROXY_URL,
        "llm_upstream": None,
    }

    # Exactly one model call through the Gateway profile client.
    assert len(h.llm_calls) == 1
    call = h.llm_calls[0]
    assert call["model"] == MODEL
    assert call["max_tokens"] == 2048
    assert call["system"] == "You are a characterization-test brain block."
    # Rendered prompt + the credential section (run_id is always exported).
    assert call["messages"] == [{"role": "user", "content": (
        "Summarise Fix flaky test\n\nCredentials are pre-exported into every "
        "run_shell call — use them directly without any setup:\n  $CONDUCT_RUN_ID\n"
        "DO NOT check if these vars exist. DO NOT try to read them from files. "
        "They are already in the shell environment."
    )}]
    assert "tools" not in call
    assert call["idempotency_key"] == f"conduct-{RUN_ID}-{BLOCK_ID}-0"
    assert call["outer_attempt"] == 1

    (kw,) = h.client_kwargs
    assert kw["profile_cond_code"] == "cond-ABC12345-default"
    assert kw["base_url"] == PROXY_URL
    assert kw["stream_enabled"] is False
    assert kw["default_headers"] == {
        "x-conductai-run-id": RUN_ID,
        "x-conductai-workflow": "Char Workflow",
        "x-conductai-workflow-id": WORKFLOW_ID,
        "x-conductai-workspace-id": WORKSPACE_ID,
        "x-conductai-user-email": "dev@example.com",
    }

    assert h.kinds() == ["brain_tool_call"]
    evt = h.emitted("brain_tool_call")[0]
    assert evt["tool"] == "single_call"
    assert evt["turn"] == 1
    assert evt["output"] == out_text
    assert (evt["input_tokens"], evt["output_tokens"]) == (12, 7)
    assert [(t, r) for t, r, _ in h.traces] == [(1, "user"), (1, "assistant")]

    # No tool loop side effects, no Guard, no memory, state untouched.
    assert h.checkpoints == []
    assert h.rule_lookups == []
    assert h.memory_calls == []
    assert h.mcp_tool_loads == []
    assert h.sessions_created == []
    assert h.session.close_calls == 1
    assert h.session.capture_calls == 0
    assert state == before


def test_single_turn_for_each_index_in_idempotency_key():
    with brain_harness([text_response("plain text")]) as h:
        result = run_brain(h, brain_block(agentic=False), base_state(__for_each_index=2))
    assert h.llm_calls[0]["idempotency_key"] == f"conduct-{RUN_ID}-{BLOCK_ID}-0-fe2"
    assert result["output"] == "plain text"
    assert "verdict" not in result


def test_single_turn_upstream_error_emits_and_reraises():
    err = _upstream_error()
    with brain_harness([err]) as h:
        with pytest.raises(LLMUpstreamError) as exc:
            run_brain(h, brain_block(agentic=False), base_state())
    assert exc.value is err
    (evt,) = h.emitted("llm_upstream_blocked")
    assert evt["status"] == 503
    assert evt["turn"] == 0
    assert evt["is_final"] is True
    assert evt["cf_ray"] == "ray-1"
    assert evt["base_url"] == PROXY_URL
    assert h.kinds() == ["llm_upstream_blocked"]
    assert h.traces == []


def test_single_turn_generic_model_error_propagates_without_event():
    with brain_harness([ValueError("gateway exploded")]) as h:
        with pytest.raises(ValueError, match="gateway exploded"):
            run_brain(h, brain_block(agentic=False), base_state())
    assert h.emits == []


# ── Gateway profile requirement (#2170) ──────────────────────────────


def test_unassigned_profile_refuses_before_session_or_model_call():
    with brain_harness([], assigned=False) as h:
        with pytest.raises(RuntimeError) as exc:
            run_brain(h, brain_block(agentic=False), base_state(), injected_session=None)
    assert str(exc.value) == (
        f"workflow {WORKFLOW_ID} has no Gateway profile assigned. Every brain "
        f"block must pin a published profile in workflow settings (#2170). "
        f"Direct-provider routing is retired."
    )
    assert h.sessions_created == []
    assert h.llm_calls == []
    assert h.client_kwargs == []
    assert h.emits == []


def test_missing_workflow_id_refuses():
    with brain_harness([]) as h:
        with pytest.raises(RuntimeError, match="requires a workflow context"):
            run_brain(h, brain_block(agentic=False), base_state(), workflow_id=None)
    assert h.llm_calls == []


def test_dry_run_with_profile_returns_stub_without_model_call():
    with brain_harness([]) as h:
        result = run_brain(h, brain_block(agentic=True), base_state(__dry_run=True))
    assert result == {
        "dry_run": True,
        "note": "Dry run — Brain block would invoke Claude AI with the workflow context",
        "description": "You are a characterization-test brain block.",
        "is_agentic": True,
        "remote_host": False,
    }
    assert h.llm_calls == []
    assert h.session.close_calls == 0
