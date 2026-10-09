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
    mcp_server_row,
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


# ── MCP tool calls (#2401 item 1) ────────────────────────────────────

NO_GH_DELETE = {"id": "no-gh-delete", "match_mcp_server": "github",
                "match_tool": "delete_repo", "action": "block",
                "message": "no repo deletes"}


def _mcp_run(tool_name: str, rules: list[dict]):
    servers = [mcp_server_row("github", "https://gh.mcp.test"),
               mcp_server_row("slack", "https://slack.mcp.test")]
    script = [tool_response(("t1", tool_name, {"repo": "acme/api"})),
              text_response("done")]
    return _run(script, rules, mcp_servers=servers)


def test_mcp_server_scoped_rule_blocks_on_its_server_with_audit_and_notify():
    h, _ = _mcp_run("github__delete_repo", [NO_GH_DELETE])

    assert h.mcp_calls == []
    assert _tool_result(h) == "[guard_blocked] no repo deletes"
    (evt,) = h.emitted("brain_tool_call")
    assert evt == {"tool": "github__delete_repo", "guard_action": "block",
                   "guard_rule": "no-gh-delete",
                   "guard_message": "no repo deletes", "turn": 1}
    (row,) = h.audit_rows()
    assert (row.decision, row.rule_id, row.tool_call) == (
        "blocked", "no-gh-delete", "github__delete_repo")
    assert (row.source, row.ai_tool, row.conductai_run_id) == (
        "runtime", "conduct_runtime", RUN_ID)
    assert h.notifies == [{"workspace_id": WORKSPACE_ID, "decision": "blocked",
                           "rule_id": "no-gh-delete", "user_email": "dev@example.com",
                           "tool": "github__delete_repo", "source": "runtime"}]


def test_mcp_server_scoped_rule_does_not_apply_to_other_servers():
    h, _ = _mcp_run("slack__delete_repo", [NO_GH_DELETE])

    assert h.mcp_calls == [("https://slack.mcp.test", "delete_repo", {"repo": "acme/api"})]
    assert _tool_result(h) == '{"ok": true, "tool": "delete_repo"}'
    assert [e["tool"] for e in h.emitted("brain_tool_call")] == ["slack__delete_repo"]
    assert h.audit_rows() == []
    assert h.notifies == []


def test_mcp_unscoped_rule_applies_to_every_server():
    rule = {k: v for k, v in NO_GH_DELETE.items() if k != "match_mcp_server"}
    h, _ = _mcp_run("slack__delete_repo", [rule])
    assert h.mcp_calls == []
    assert [r.rule_id for r in h.audit_rows()] == ["no-gh-delete"]
