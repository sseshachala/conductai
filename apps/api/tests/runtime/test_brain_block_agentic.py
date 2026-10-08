"""Characterization: ``_execute_brain`` agentic (tool-loop) mode (#2400).

Pins the tool loop, turn counting, turn/cost budgets, mark_complete,
clarification and model-error paths, including run-row accounting
(``actual_turns`` / ``budget_exhausted``) and turn checkpoints.
"""
from __future__ import annotations

import copy

import pytest

from app.runtime.blocks.brain_block import BRAIN_TOOLS
from app.runtime.exceptions import ClarificationRequired
from app.runtime.llm_client import LLMUpstreamError
from tests.runtime.brain_block_harness import (
    BLOCK_ID,
    DIFF_STAT,
    FILES_CHANGED,
    MODEL,
    PROVIDER,
    RUN_ID,
    base_state,
    brain_block,
    brain_harness,
    expected_pricing,
    run_brain,
    text_response,
    tool_response,
)


def _agentic(**data):
    data.setdefault("max_turns", 5)
    return brain_block(agentic=True, **data)


def test_multi_turn_tool_loop_returns_final_output():
    script = [
        tool_response(("t1", "run_shell", {"command": "pytest -q"}),
                      correlation_ids={"t1": "corr-1"}),
        tool_response(("t2", "read_file", {"path": "a.py"})),
        text_response('All fixed.\n{"status": "fixed"}'),
    ]
    state = base_state()
    before = copy.deepcopy(state)
    with brain_harness(script, session_outputs={"run_shell": "3 passed"}) as h:
        result = run_brain(h, _agentic(), state)

    rates, version = expected_pricing()
    assert result["status"] == "fixed"
    assert result["output"] == 'All fixed.\n{"status": "fixed"}'
    assert result["turns"] == 3
    assert (result["input_tokens"], result["output_tokens"]) == (30, 15)
    assert (result["cache_read_tokens"], result["cache_write_tokens"]) == (0, 0)
    assert result["cost_usd"] == 0.003
    assert result["files_changed"] == FILES_CHANGED
    assert result["diff_stat"] == DIFF_STAT
    assert result["remote_host_ip"] is None
    assert (result["provider"], result["model"]) == (PROVIDER, MODEL)
    assert (result["pricing_rates"], result["pricing_version"]) == (rates, version)

    # Placeholder is swapped for the real value only in the dispatched env.
    assert h.session.dispatched == [
        ("run_shell", {"command": "pytest -q", "env": {"CONDUCT_RUN_ID": RUN_ID}}),
        ("read_file", {"path": "a.py"}),
    ]
    assert len(h.llm_calls) == 3
    first = h.llm_calls[0]
    assert first["max_tokens"] == 4096
    assert first["system"].startswith("EXECUTION ENVIRONMENT:")
    assert [t["name"] for t in first["tools"]] == [t["name"] for t in BRAIN_TOOLS]
    assert [c["idempotency_key"] for c in h.llm_calls] == [
        f"conduct-{RUN_ID}-{BLOCK_ID}-{n}" for n in range(3)
    ]
    roles = [m["role"] for m in h.llm_calls[2]["messages"]]
    assert roles == ["user", "assistant", "tool", "assistant", "tool"]
    assert h.llm_calls[2]["messages"][2]["content"] == "3 passed"

    tool_evts = h.emitted("brain_tool_call")
    assert [(e["tool"], e["turn"]) for e in tool_evts] == [("run_shell", 1), ("read_file", 2)]
    assert tool_evts[0]["tool_call_correlation_id"] == "corr-1"
    assert "tool_call_correlation_id" not in tool_evts[1]
    assert h.kinds() == ["brain_tool_call", "brain_tool_call"]

    assert [(c["resume_from_turn"], c["partial"], c["block_id"], c["attempt_id"])
            for c in h.checkpoints] == [(1, True, BLOCK_ID, "attempt-1"),
                                        (2, True, BLOCK_ID, "attempt-1")]
    assert [(t, r) for t, r, _ in h.traces] == [
        (1, "user"), (1, "assistant"), (1, "tool_use"), (1, "tool_result"),
        (2, "user"), (2, "assistant"), (2, "tool_use"), (2, "tool_result"),
        (3, "user"), (3, "assistant"),
    ]
    assert h.run_updates() == [{"actual_turns": 3, "budget_exhausted": False}]
    assert h.session.capture_calls == 1
    assert h.session.close_calls == 1
    assert not h.session.captured_after_close
    assert len(h.mcp_tool_loads) == 1
    assert h.memory_calls == []
    assert h.rule_lookups == []
    assert state == before


def test_turn_budget_exhausted_raises_with_partial_state():
    script = [
        tool_response(("t1", "read_file", {"path": "a.py"})),
        tool_response(("t2", "read_file", {"path": "b.py"})),
    ]
    with brain_harness(script) as h:
        with pytest.raises(RuntimeError) as exc:
            run_brain(h, _agentic(max_turns=2, rollback_on_failure=True), base_state())

    assert str(exc.value) == (
        "Turn budget exhausted: agent did not reach end_turn after 2 turns "
        "(20 input / 10 output tokens, $0.0020)"
    )
    (evt,) = h.emitted("brain_budget_exhausted")
    assert evt["reason"] == "max_turns_reached"
    assert (evt["turns"], evt["max_turns"]) == (2, 2)
    assert evt["files_changed"] == FILES_CHANGED
    (rb,) = h.emitted("guardrail.rollback_triggered")
    assert rb["reason"] == "max_turns_reached"
    assert len(h.checkpoints) == 2
    assert len(h.session.dispatched) == 2
    assert h.session.close_calls == 1


def test_block_max_turns_overrides_run_level_budget():
    script = [tool_response(("t1", "read_file", {"path": "a.py"}))]
    with brain_harness(script) as h:
        with pytest.raises(RuntimeError, match="after 1 turns"):
            run_brain(h, _agentic(max_turns=1), base_state(__max_turns=20))
    assert len(h.llm_calls) == 1


def test_cost_budget_exhausted_raises_before_tools_run():
    script = [tool_response(("t1", "run_shell", {"command": "ls"}), cost=0.5)]
    with brain_harness(script) as h:
        with pytest.raises(RuntimeError) as exc:
            run_brain(h, _agentic(max_cost_usd=0.25), base_state())
    assert str(exc.value) == (
        "Cost budget exhausted: agent reached $0.5000 with cap $0.2500 after 1 turns"
    )
    (evt,) = h.emitted("brain_budget_exhausted")
    assert evt["reason"] == "max_cost_reached"
    assert evt["max_cost_usd"] == 0.25
    assert h.session.dispatched == []
    assert h.session.close_calls == 1


def test_needs_clarification_on_first_turn_pauses_block():
    script = [text_response("NEEDS_CLARIFICATION: which repository?")]
    with brain_harness(script) as h:
        with pytest.raises(ClarificationRequired) as exc:
            run_brain(h, _agentic(), base_state())
    assert exc.value.question == "which repository?"
    assert h.session.close_calls == 1
    assert h.run_updates() == []


def test_clarification_answer_is_appended_to_user_message():
    state = base_state(**{f"__clarification_{BLOCK_ID}": "conduct/marshal"})
    with brain_harness([text_response("ok")]) as h:
        run_brain(h, _agentic(), state)
    assert h.llm_calls[0]["messages"][0]["content"].endswith(
        "\n\nClarification from user: conduct/marshal"
    )


def test_upstream_error_mid_run_emits_and_reraises():
    script = [tool_response(("t1", "read_file", {"path": "a.py"})),
              LLMUpstreamError(provider="gateway_profile", status=502,
                               content_type="text/html", body_snippet="bad gateway",
                               cf_ray=None, request_id="req-9", attempts=3)]
    with brain_harness(script) as h:
        with pytest.raises(LLMUpstreamError):
            run_brain(h, _agentic(), base_state())
    (evt,) = h.emitted("llm_upstream_blocked")
    assert (evt["turn"], evt["status"], evt["is_final"]) == (1, 502, True)
    assert len(h.checkpoints) == 1
    assert h.run_updates() == []


def test_require_tests_pass_blocks_commit_until_tests_ran():
    script = [
        tool_response(("t1", "run_shell", {"command": "git commit -m x"})),
        tool_response(("t2", "run_shell", {"command": "pytest -q"}),
                      ("t3", "run_shell", {"command": "git commit -m x"})),
        text_response("committed"),
    ]
    with brain_harness(script) as h:
        run_brain(h, _agentic(require_tests_pass=True), base_state())
    assert [i["command"] for _, i in h.session.dispatched] == ["pytest -q", "git commit -m x"]
    blocked = h.llm_calls[1]["messages"][2]["content"]
    assert blocked.startswith("[guardrail_blocked] Tests must pass before committing.")
    assert len(h.emitted("guardrail.require_tests_pass")) == 1


def test_memory_blocks_are_not_invoked_by_brain():
    """recall_context / record_outcome are separate memory blocks run by
    dag_runner; _execute_brain never calls them itself."""
    with brain_harness([text_response("done")]) as h:
        run_brain(h, _agentic(), base_state())
    assert h.memory_calls == []
