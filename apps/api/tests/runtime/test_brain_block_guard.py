"""Characterization: Guard checks on brain tool calls (#2400, #2401).

Rules are fed as raw policy rows through ``compute_policy`` so the real
``_get_rules`` → ``_project_rule`` projection runs, exactly as in the
worker.
"""
from __future__ import annotations

from tests.runtime.brain_block_harness import (
    RUN_ID,
    WORKFLOW_ID,
    WORKSPACE_ID,
    base_state,
    brain_block,
    brain_harness,
    run_brain,
    text_response,
    tool_response,
)

NO_RM = {"id": "no-rm", "match_tool": "shell", "match_pattern": "rm -rf",
         "action": "block", "message": "no recursive deletes"}


def _run(script, rules, *, guard=True, **harness_kw):
    with brain_harness(script, raw_rules=rules, **harness_kw) as h:
        result = run_brain(h, brain_block(agentic=True, max_turns=5),
                           base_state(__guard_enabled=guard))
    return h, result


def _tool_result(h, call_idx: int = 1, msg_idx: int = 2) -> str:
    return h.llm_calls[call_idx]["messages"][msg_idx]["content"]


def test_non_mcp_tool_blocked_by_guard():
    script = [tool_response(("t1", "run_shell", {"command": "rm -rf /tmp/x"})),
              text_response("gave up")]
    h, result = _run(script, [NO_RM])

    assert result["output"] == "gave up"
    assert h.session.dispatched == []  # never reached the sandbox
    assert _tool_result(h) == "[guard_blocked] no recursive deletes  [rule: no-rm]"
    assert h.rule_lookups == [(WORKSPACE_ID, "agent")]

    guard_evt, tool_evt = h.emitted("brain_tool_call")
    assert guard_evt == {"tool": "run_shell", "guard_action": "block",
                         "guard_rule": "no-rm",
                         "guard_message": "no recursive deletes", "turn": 1}
    assert tool_evt["tool"] == "run_shell"

    (row,) = h.audit_rows()
    assert (row.decision, row.rule_id, row.tool_call) == ("blocked", "no-rm", "run_shell")
    assert (row.source, row.ai_tool) == ("runtime", "conduct_runtime")
    assert row.conductai_run_id == RUN_ID
    assert row.conductai_workflow == "char-playbook"
    assert row.conductai_workflow_id == WORKFLOW_ID
    assert row.user_email == "dev@example.com"
    assert h.notifies == [{"workspace_id": WORKSPACE_ID, "decision": "blocked",
                           "rule_id": "no-rm", "user_email": "dev@example.com",
                           "tool": "run_shell", "source": "runtime"}]


def test_non_mcp_warn_dispatches_and_notifies():
    rule = {**NO_RM, "action": "warn"}
    script = [tool_response(("t1", "run_shell", {"command": "rm -rf /tmp/x"})),
              text_response("done")]
    h, _ = _run(script, [rule])
    assert [n for n, _ in h.session.dispatched] == ["run_shell"]
    assert [r.decision for r in h.audit_rows()] == ["warned"]
    assert [n["decision"] for n in h.notifies] == ["warned"]


def test_non_mcp_audit_action_records_without_notify():
    rule = {**NO_RM, "action": "audit"}
    script = [tool_response(("t1", "run_shell", {"command": "rm -rf /tmp/x"})),
              text_response("done")]
    h, _ = _run(script, [rule])
    assert [n for n, _ in h.session.dispatched] == ["run_shell"]
    assert [r.decision for r in h.audit_rows()] == ["audited"]
    assert h.notifies == []


def test_block_wins_over_warn_when_both_match():
    rules = [{**NO_RM, "id": "warn-rm", "action": "warn"}, NO_RM]
    script = [tool_response(("t1", "run_shell", {"command": "rm -rf /tmp/x"})),
              text_response("done")]
    h, _ = _run(script, rules)
    assert h.session.dispatched == []
    assert [r.rule_id for r in h.audit_rows()] == ["no-rm"]


def test_rule_not_supported_on_runtime_is_skipped():
    rule = {**NO_RM, "enforcement": {"runtime": "not_supported"}}
    script = [tool_response(("t1", "run_shell", {"command": "rm -rf /tmp/x"})),
              text_response("done")]
    h, _ = _run(script, [rule])
    assert [n for n, _ in h.session.dispatched] == ["run_shell"]
    assert h.audit_rows() == []


def test_path_pattern_rule_blocks_traversal():
    rule = {"id": "no-traversal", "match_tool": "read_file",
            "match_path_pattern": r"\.\./", "action": "block", "message": "traversal"}
    script = [tool_response(("t1", "read_file", {"path": "../etc/passwd"})),
              text_response("done")]
    h, _ = _run(script, [rule])
    assert h.session.dispatched == []
    assert _tool_result(h) == "[guard_blocked] traversal  [rule: no-traversal]"


def test_guard_disabled_skips_rule_lookup():
    script = [tool_response(("t1", "run_shell", {"command": "rm -rf /tmp/x"})),
              text_response("done")]
    h, _ = _run(script, [NO_RM], guard=False)
    assert h.rule_lookups == []
    assert [n for n, _ in h.session.dispatched] == ["run_shell"]
    assert h.audit_rows() == []
    assert h.notifies == []
