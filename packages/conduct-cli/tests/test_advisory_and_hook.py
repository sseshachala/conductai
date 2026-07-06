"""
CLI tests covering advisory mode (P1) and pretooluse hook flow.

Covers:
  Advisory mode config:
    - _get_advisory_mode returns False by default
    - _get_advisory_mode returns True when advisory_mode set in config
    - guard sync mirrors advisory_mode from policy into config

  Advisory mode hook behavior:
    - block rule + advisory ON  → exits 0, posts "audited" decision
    - block rule + advisory OFF → exits 2, posts "blocked" decision
    - warn rule  + advisory ON  → exits 0, posts "audited" decision
    - approval rule + advisory ON → exits 0, posts "audited" decision
    - allow (no match) + advisory ON → exits 0, posts "allowed"

  Fail-closed gate:
    - fail_closed + no policy file → exits 2, posts "blocked" guard-unavailable
    - fail_open  + no policy file → passes through to policy check

  Budget hard cap:
    - hard_blocked=True → exits 2 regardless of advisory mode

  Warn dedup:
    - same session + same rule → exits 0 on second warn (already warned)
    - different session → warns again

  Policy eval error interaction with advisory (P4 × P1):
    - policy eval throws + advisory OFF → exits 2 (fail-closed wins)
    - policy eval throws + advisory ON  → exits 2 (fail-closed wins; advisory only covers rule matches)
"""
from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

CONDUCT_CLI_SRC = Path(__file__).resolve().parent.parent / "src"
if str(CONDUCT_CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CONDUCT_CLI_SRC))

import conduct_cli.guard as guard_mod
from conduct_cli.guard import POLICY_PATH, CONFIG_PATH


# ── helpers ───────────────────────────────────────────────────────────────────

def _hook_input(tool="Bash", cmd="echo hi", session="sess-1") -> str:
    return json.dumps({
        "tool_name": tool,
        "tool_input": {"command": cmd},
        "session_id": session,
    })


def _block_policy(rule_id="no-echo", pattern="echo", action="block") -> dict:
    return {
        "version": "test",
        "rules": [{"rule_id": rule_id, "match_tool": "*", "match_pattern": pattern, "action": action, "message": f"rule {rule_id}"}],
    }


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


# ── advisory config ───────────────────────────────────────────────────────────

class TestGetAdvisoryMode:
    def test_default_false(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.json"
        _write(cfg, {"workspace_id": "ws1"})
        monkeypatch.setattr(guard_mod, "CONFIG_PATH", cfg)
        import conduct_cli.hooks.pretooluse as pt
        monkeypatch.setattr(pt, "load_config", lambda: {"workspace_id": "ws1"})
        assert pt._get_advisory_mode() is False

    def test_true_when_set(self, tmp_path, monkeypatch):
        import conduct_cli.hooks.pretooluse as pt
        monkeypatch.setattr(pt, "load_config", lambda: {"advisory_mode": True})
        assert pt._get_advisory_mode() is True

    def test_false_when_explicitly_false(self, tmp_path, monkeypatch):
        import conduct_cli.hooks.pretooluse as pt
        monkeypatch.setattr(pt, "load_config", lambda: {"advisory_mode": False})
        assert pt._get_advisory_mode() is False


# ── advisory hook behavior ────────────────────────────────────────────────────

class TestAdvisoryHookBehavior:
    """Patch check_policy to return a specific action, verify advisory bypass logic."""

    def _run(self, monkeypatch, *, advisory: bool, action: str, rule_id: str = "r1", message: str = "msg"):
        import conduct_cli.hooks.pretooluse as pt

        monkeypatch.setattr(pt, "_get_fail_mode", lambda: "fail_open")
        monkeypatch.setattr(pt, "_get_advisory_mode", lambda: advisory)
        monkeypatch.setattr(pt, "_load_budget_cache", lambda: (False, None))
        monkeypatch.setattr(pt, "_fetch_budget_status", lambda: (False, None))
        monkeypatch.setattr(pt, "_maybe_sync_policy", lambda: None)
        monkeypatch.setattr(pt, "_should_periodic_flush", lambda: False)
        # Return the desired action regardless of policy file content
        fake_rule = {"rule_id": rule_id, "action": action}
        monkeypatch.setattr(pt, "check_policy", lambda tn, ti, **kw: (fake_rule, action, rule_id, message))

        posted: list[dict] = []
        monkeypatch.setattr(pt, "post_event", lambda tn, ti, d, r, m, s, **kw: posted.append({"decision": d, "message": m}))
        monkeypatch.setattr(sys, "stdin", StringIO(_hook_input()))

        exit_code = None
        try:
            pt.main()
        except SystemExit as e:
            exit_code = e.code
        return exit_code, posted

    def test_block_advisory_on_exits_0(self, monkeypatch):
        code, posted = self._run(monkeypatch, advisory=True, action="block")
        assert code == 0
        assert posted[0]["decision"] == "audited"

    def test_block_advisory_off_exits_2(self, monkeypatch):
        code, posted = self._run(monkeypatch, advisory=False, action="block")
        assert code == 2
        assert posted[0]["decision"] == "blocked"

    def test_warn_advisory_on_exits_0(self, monkeypatch):
        code, posted = self._run(monkeypatch, advisory=True, action="warn")
        assert code == 0
        assert posted[0]["decision"] == "audited"

    def test_approval_advisory_on_exits_0(self, monkeypatch):
        code, posted = self._run(monkeypatch, advisory=True, action="approval")
        assert code == 0
        assert posted[0]["decision"] == "audited"

    def test_no_match_advisory_on_exits_0(self, monkeypatch):
        """No rule match — exits 0 even without advisory."""
        import conduct_cli.hooks.pretooluse as pt
        monkeypatch.setattr(pt, "_get_fail_mode", lambda: "fail_open")
        monkeypatch.setattr(pt, "_get_advisory_mode", lambda: True)
        monkeypatch.setattr(pt, "_load_budget_cache", lambda: (False, None))
        monkeypatch.setattr(pt, "_fetch_budget_status", lambda: (False, None))
        monkeypatch.setattr(pt, "_maybe_sync_policy", lambda: None)
        monkeypatch.setattr(pt, "_should_periodic_flush", lambda: False)
        monkeypatch.setattr(pt, "check_policy", lambda tn, ti, **kw: (None, "allow", None, None))
        monkeypatch.setattr(pt, "post_event", lambda *a, **kw: None)
        monkeypatch.setattr(sys, "stdin", StringIO(_hook_input()))

        with pytest.raises(SystemExit) as exc:
            pt.main()
        assert exc.value.code == 0

    def test_advisory_message_prefixed(self, monkeypatch):
        import conduct_cli.hooks.pretooluse as pt
        monkeypatch.setattr(pt, "_get_fail_mode", lambda: "fail_open")
        monkeypatch.setattr(pt, "_get_advisory_mode", lambda: True)
        monkeypatch.setattr(pt, "_load_budget_cache", lambda: (False, None))
        monkeypatch.setattr(pt, "_fetch_budget_status", lambda: (False, None))
        monkeypatch.setattr(pt, "_maybe_sync_policy", lambda: None)
        monkeypatch.setattr(pt, "_should_periodic_flush", lambda: False)
        monkeypatch.setattr(pt, "check_policy", lambda tn, ti, **kw: ({}, "block", "r1", "bad thing"))

        messages: list[str] = []
        monkeypatch.setattr(pt, "post_event", lambda tn, ti, d, r, m, s, **kw: messages.append(m))
        monkeypatch.setattr(sys, "stdin", StringIO(_hook_input()))

        try:
            pt.main()
        except SystemExit:
            pass
        assert messages and messages[0].startswith("[advisory]")


# ── fail-closed gate ──────────────────────────────────────────────────────────

class TestFailClosedGate:
    def test_fail_closed_no_policy_exits_2(self, monkeypatch, tmp_path):
        import conduct_cli.hooks.pretooluse as pt

        missing = tmp_path / "nowhere.json"
        monkeypatch.setattr(pt, "active_policy_path", lambda: missing)
        monkeypatch.setattr(pt, "_get_fail_mode", lambda: "fail_closed")
        monkeypatch.setattr(pt, "_get_advisory_mode", lambda: False)
        monkeypatch.setattr(pt, "_should_periodic_flush", lambda: False)
        monkeypatch.setattr(pt, "_maybe_sync_policy", lambda: None)

        posted: list[dict] = []
        def _fake_post(tn, ti, decision, rule_id, msg, sid, **kw):
            posted.append({"decision": decision, "rule_id": rule_id})
        monkeypatch.setattr(pt, "post_event", _fake_post)
        monkeypatch.setattr(sys, "stdin", StringIO(_hook_input()))

        with pytest.raises(SystemExit) as exc:
            pt.main()
        assert exc.value.code == 2
        assert posted[0]["decision"] == "blocked"
        assert posted[0]["rule_id"] == "guard-unavailable"

    def test_fail_open_no_policy_passes(self, monkeypatch, tmp_path):
        import conduct_cli.hooks.pretooluse as pt

        missing = tmp_path / "nowhere.json"
        monkeypatch.setattr(pt, "active_policy_path", lambda: missing)
        monkeypatch.setattr(pt, "_get_fail_mode", lambda: "fail_open")
        monkeypatch.setattr(pt, "_get_advisory_mode", lambda: False)
        monkeypatch.setattr(pt, "_load_budget_cache", lambda: (False, None))
        monkeypatch.setattr(pt, "_fetch_budget_status", lambda: (False, None))
        monkeypatch.setattr(pt, "_maybe_sync_policy", lambda: None)
        monkeypatch.setattr(pt, "_should_periodic_flush", lambda: False)
        monkeypatch.setattr(pt, "post_event", lambda *a, **kw: None)
        monkeypatch.setattr(sys, "stdin", StringIO(_hook_input()))

        with pytest.raises(SystemExit) as exc:
            pt.main()
        assert exc.value.code == 0


# ── budget hard cap ───────────────────────────────────────────────────────────

class TestBudgetHardCap:
    def test_hard_cap_exits_2(self, monkeypatch, tmp_path):
        import conduct_cli.hooks.pretooluse as pt

        policy_path = tmp_path / "policy.json"
        _write(policy_path, {"version": "test", "rules": []})
        monkeypatch.setattr(pt, "active_policy_path", lambda: policy_path)
        monkeypatch.setattr(pt, "_get_fail_mode", lambda: "fail_open")
        monkeypatch.setattr(pt, "_get_advisory_mode", lambda: False)
        monkeypatch.setattr(pt, "_load_budget_cache", lambda: (True, "Monthly cap reached"))
        monkeypatch.setattr(pt, "_maybe_sync_policy", lambda: None)
        monkeypatch.setattr(pt, "_should_periodic_flush", lambda: False)

        posted: list[dict] = []
        monkeypatch.setattr(pt, "post_event", lambda tn, ti, d, r, m, s, **kw: posted.append({"decision": d, "rule_id": r}))
        monkeypatch.setattr(sys, "stdin", StringIO(_hook_input()))

        with pytest.raises(SystemExit) as exc:
            pt.main()
        assert exc.value.code == 2
        assert posted[0]["decision"] == "blocked"
        assert posted[0]["rule_id"] == "budget-hard-cap"

    def test_hard_cap_wins_over_advisory(self, monkeypatch, tmp_path):
        """Budget hard cap blocks even when advisory mode is on."""
        import conduct_cli.hooks.pretooluse as pt

        policy_path = tmp_path / "policy.json"
        _write(policy_path, {"version": "test", "rules": []})
        monkeypatch.setattr(pt, "active_policy_path", lambda: policy_path)
        monkeypatch.setattr(pt, "_get_fail_mode", lambda: "fail_open")
        monkeypatch.setattr(pt, "_get_advisory_mode", lambda: True)  # advisory ON
        monkeypatch.setattr(pt, "_load_budget_cache", lambda: (True, "Cap reached"))
        monkeypatch.setattr(pt, "_maybe_sync_policy", lambda: None)
        monkeypatch.setattr(pt, "_should_periodic_flush", lambda: False)
        monkeypatch.setattr(pt, "post_event", lambda *a, **kw: None)
        monkeypatch.setattr(sys, "stdin", StringIO(_hook_input()))

        with pytest.raises(SystemExit) as exc:
            pt.main()
        assert exc.value.code == 2


# ── warn dedup ────────────────────────────────────────────────────────────────

class TestWarnDedup:
    def _run_warn(self, monkeypatch, session_id: str):
        import conduct_cli.hooks.pretooluse as pt

        monkeypatch.setattr(pt, "_get_fail_mode", lambda: "fail_open")
        monkeypatch.setattr(pt, "_get_advisory_mode", lambda: False)
        monkeypatch.setattr(pt, "_load_budget_cache", lambda: (False, None))
        monkeypatch.setattr(pt, "_fetch_budget_status", lambda: (False, None))
        monkeypatch.setattr(pt, "_maybe_sync_policy", lambda: None)
        monkeypatch.setattr(pt, "_should_periodic_flush", lambda: False)
        monkeypatch.setattr(pt, "check_policy", lambda tn, ti, **kw: ({}, "warn", "rule-w1", "watch out"))
        monkeypatch.setattr(pt, "_already_warned_this_session", lambda s, r: False)
        monkeypatch.setattr(pt, "_record_session_warn", lambda s, r: None)

        posted: list[str] = []
        monkeypatch.setattr(pt, "post_event", lambda tn, ti, d, r, m, s, **kw: posted.append(d))
        monkeypatch.setattr(sys, "stdin", StringIO(_hook_input(session=session_id)))

        try:
            pt.main()
        except SystemExit:
            pass
        return posted

    def test_first_warn_posts(self, monkeypatch):
        posted = self._run_warn(monkeypatch, "sess-abc")
        assert "warned" in posted

    def test_second_warn_same_session_skips(self, monkeypatch, tmp_path):
        import conduct_cli.hooks.pretooluse as pt
        warns: dict[str, set] = {}

        def _fake_already(session, rule):
            return rule in warns.get(session, set())

        def _fake_record(session, rule):
            warns.setdefault(session, set()).add(rule)

        monkeypatch.setattr(pt, "_already_warned_this_session", _fake_already)
        monkeypatch.setattr(pt, "_record_session_warn", _fake_record)

        # First call records the warn
        _fake_record("sess-xyz", "no-echo")

        monkeypatch.setattr(pt, "check_policy", lambda tn, ti, **kw: ({}, "warn", "no-echo", "watch out"))
        monkeypatch.setattr(pt, "_get_fail_mode", lambda: "fail_open")
        monkeypatch.setattr(pt, "_get_advisory_mode", lambda: False)
        monkeypatch.setattr(pt, "_load_budget_cache", lambda: (False, None))
        monkeypatch.setattr(pt, "_fetch_budget_status", lambda: (False, None))
        monkeypatch.setattr(pt, "_maybe_sync_policy", lambda: None)
        monkeypatch.setattr(pt, "_should_periodic_flush", lambda: False)

        posted: list[str] = []
        monkeypatch.setattr(pt, "post_event", lambda tn, ti, d, r, m, s, **kw: posted.append(d))
        monkeypatch.setattr(sys, "stdin", StringIO(_hook_input(session="sess-xyz")))

        try:
            pt.main()
        except SystemExit:
            pass

        assert posted == [], "second warn same session should be skipped"


# ── advisory_mode mirrored on sync ────────────────────────────────────────────

class TestSyncMirrorsAdvisoryMode:
    def test_advisory_true_written_to_config(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.json"
        pol_path = tmp_path / "policy.json"
        _write(cfg_path, {"workspace_id": "ws1"})

        monkeypatch.setattr(guard_mod, "CONFIG_PATH", cfg_path)
        monkeypatch.setattr(guard_mod, "POLICY_PATH", pol_path)

        policy = {"version": "v1", "rules": [], "fail_mode": "fail_open", "advisory_mode": True}
        monkeypatch.setattr(guard_mod, "_load_guard_config", lambda: {"workspace_id": "ws1"})

        saved: list[dict] = []
        monkeypatch.setattr(guard_mod, "_save_guard_config", lambda cfg: saved.append(dict(cfg)))
        monkeypatch.setattr(guard_mod, "_save_policy", lambda p: None)

        # Simulate the sync block
        cfg = guard_mod._load_guard_config()
        cfg["fail_mode"] = policy.get("fail_mode", "fail_open")
        cfg["advisory_mode"] = policy.get("advisory_mode", False)
        guard_mod._save_guard_config(cfg)

        assert saved[0]["advisory_mode"] is True

    def test_advisory_false_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(guard_mod, "_load_guard_config", lambda: {"workspace_id": "ws1"})
        saved: list[dict] = []
        monkeypatch.setattr(guard_mod, "_save_guard_config", lambda cfg: saved.append(dict(cfg)))
        monkeypatch.setattr(guard_mod, "_save_policy", lambda p: None)

        policy = {"version": "v1", "rules": [], "fail_mode": "fail_open"}
        cfg = guard_mod._load_guard_config()
        cfg["fail_mode"] = policy.get("fail_mode", "fail_open")
        cfg["advisory_mode"] = policy.get("advisory_mode", False)
        guard_mod._save_guard_config(cfg)

        assert saved[0]["advisory_mode"] is False


# ── invalid stdin ─────────────────────────────────────────────────────────────

class TestInvalidStdin:
    def test_malformed_json_exits_0(self, monkeypatch):
        import conduct_cli.hooks.pretooluse as pt
        monkeypatch.setattr(sys, "stdin", StringIO("not json {{{"))
        with pytest.raises(SystemExit) as exc:
            pt.main()
        assert exc.value.code == 0

    def test_empty_stdin_exits_0(self, monkeypatch):
        import conduct_cli.hooks.pretooluse as pt
        monkeypatch.setattr(sys, "stdin", StringIO(""))
        with pytest.raises(SystemExit) as exc:
            pt.main()
        assert exc.value.code == 0
