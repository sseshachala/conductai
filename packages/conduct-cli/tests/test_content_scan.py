"""PostToolUse scan of tool output for indirect injection (#2384).

Uses a synthetic marker pattern: these tests exercise the mechanism, not a payload.
"""
import json

import pytest

from conduct_cli.hooks import content_scan, posttooluse

MARK = "ZZ-CANARY-MARK"


def _rule(action="warn", rule_id="r1", **kw):
    return {"rule_id": rule_id, "match_tool": "__tool_result__", "match_pattern": MARK,
            "match_content_source": ["tool_result"], "action": action, "message": "flagged", **kw}


@pytest.fixture(autouse=True)
def flags(tmp_path, monkeypatch):
    monkeypatch.setattr(content_scan, "GUARD_DIR", tmp_path)
    monkeypatch.setattr(content_scan, "FLAGS_PATH", tmp_path / "flags.json")
    return tmp_path / "flags.json"


def test_response_text_flattens_nested_values():
    assert "a" in content_scan.response_text({"x": ["a", {"y": "b"}], "n": 3})
    assert content_scan.response_text(None) == ""


def test_scan_matches_tool_result_rule_only():
    hit = content_scan.scan_tool_response([_rule()], {"stdout": f"page says {MARK} now"})
    assert hit and hit[0]["rule_id"] == "r1" and hit[1] == MARK
    assert content_scan.scan_tool_response([_rule()], "clean output") is None
    # a rule not scoped to tool_result (e.g. a tool-input rule) is ignored
    plain = {"rule_id": "p", "match_tool": "bash", "match_pattern": MARK, "action": "block"}
    assert content_scan.scan_tool_response([plain], MARK) is None


def test_most_severe_rule_wins():
    hit = content_scan.scan_tool_response([_rule("warn", "w"), _rule("block", "b")], MARK)
    assert hit[0]["rule_id"] == "b"


def test_bad_regex_is_skipped():
    assert content_scan.scan_tool_response([_rule(match_pattern="(")], MARK) is None


def test_block_marker_is_one_shot():
    content_scan.mark_session("s1", "r1", "block", "msg", "webfetch")
    flag = content_scan.take_session_block("s1")
    assert flag and flag["rule_id"] == "r1"
    assert content_scan.take_session_block("s1") is None
    assert content_scan.take_session_block("other") is None


def test_warn_marker_does_not_block():
    content_scan.mark_session("s1", "r1", "warn", "msg", "webfetch")
    assert content_scan.take_session_block("s1") is None


def _patch_post(monkeypatch, rules):
    events = []
    monkeypatch.setattr(posttooluse, "_load_policy_rules", lambda: rules)
    monkeypatch.setattr(posttooluse, "post_event", lambda *a, **k: events.append((a, k)))
    monkeypatch.setattr(posttooluse, "_already_warned_this_session", lambda *a: False)
    monkeypatch.setattr(posttooluse, "_record_session_warn", lambda *a: None)
    from conduct_cli.hooks import pretooluse
    monkeypatch.setattr(pretooluse, "_get_advisory_mode", lambda: False)
    return events


def test_posttool_warn_event_carries_content_source(monkeypatch):
    events = _patch_post(monkeypatch, [_rule("warn")])
    posttooluse._scan_tool_output("webfetch", f"x {MARK} y", "s1", "tu1", None)
    (args, kwargs), = events
    assert args[2] == "warned" and args[3] == "r1"
    assert kwargs["content_source"] == "tool_result" and kwargs["tool_use_id"] == "tu1"
    assert args[1]["content_source"] == "tool_result" and args[1]["matched_excerpt"] == MARK
    assert content_scan.take_session_block("s1") is None


def test_posttool_block_rule_marks_session_for_next_call(monkeypatch):
    events = _patch_post(monkeypatch, [_rule("block")])
    posttooluse._scan_tool_output("webfetch", MARK, "s1", None, None)
    assert len(events) == 1 and events[0][0][2] == "warned"
    assert content_scan.take_session_block("s1")["rule_id"] == "r1"


def test_posttool_clean_output_posts_nothing(monkeypatch):
    events = _patch_post(monkeypatch, [_rule("block")])
    posttooluse._scan_tool_output("webfetch", "all clear", "s1", None, None)
    assert events == []
    assert content_scan.take_session_block("s1") is None


def test_posttool_never_raises(monkeypatch):
    monkeypatch.setattr(posttooluse, "_load_policy_rules", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    posttooluse._scan_tool_output("webfetch", MARK, "s1", None, None)


def test_pretooluse_check_policy_ignores_content_source_rules(tmp_path, monkeypatch):
    from conduct_cli.hooks import pretooluse
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"rules": [_rule("block", match_tool="*")]}))
    monkeypatch.setattr(pretooluse, "active_policy_path", lambda: policy)
    monkeypatch.setattr(pretooluse, "_verify_policy_signature", lambda p: True)
    _, action, rule_id, _msg = pretooluse.check_policy("bash", {"command": MARK})
    assert action == "allow" and rule_id is None


def test_effective_action_prefers_tool_result_override():
    assert content_scan.effective_action(_rule("block", action_by_source={"tool_result": "warn"})) == "warn"
    assert content_scan.effective_action(_rule("block")) == "block"
    assert content_scan.effective_action(_rule("block", action_by_source={"user": "warn"})) == "block"


def test_posttool_block_rule_with_warn_override_marks_but_does_not_deny(monkeypatch):
    events = _patch_post(monkeypatch, [_rule("block", action_by_source={"tool_result": "warn"})])
    posttooluse._scan_tool_output("webfetch", MARK, "s1", None, None)
    assert len(events) == 1 and events[0][0][2] == "warned"
    assert content_scan.take_session_block("s1") is None
    assert content_scan._read_flags()["s1"]["action"] == "warn"
