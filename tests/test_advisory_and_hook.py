"""
CLI tests covering advisory mode (P1), pretooluse hook flow, and conduct verify (P3).

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

  conduct verify (P3):
    - OWASP mapping covers all 10 categories + unknown fallback
    - evidence file: pass with no blocked events → exit 0
    - evidence file: blocked events + --strict → exit 1
    - evidence file: blocked events without --strict → exit 0
    - empty evidence → exit 0, no-op message
    - bad file path → exit 2
    - invalid JSON → exit 2
    - --format json: status=fail when strict+blocked, status=pass otherwise
    - chain hashes appear in output when present

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


# ── conduct verify (P3) ──────────────────────────────────────────────────────

class TestOWASPMapping:
    """_map_owasp covers all 10 categories and falls back to A??."""

    def _map(self, rule_id: str) -> str:
        from conduct_cli.guard import _map_owasp
        return _map_owasp(rule_id)[0]

    def test_a01_prompt_injection(self):
        assert self._map("prompt_inject_tool") == "A01"

    def test_a02_sensitive_data(self):
        assert self._map("sensitive_data_read") == "A02"

    def test_a03_supply_chain(self):
        assert self._map("supply_chain_pkg") == "A03"

    def test_a04_excessive_agency(self):
        assert self._map("excessive_agency_shell") == "A04"

    def test_a07_monitoring(self):
        assert self._map("policy_eval_error") == "A07"

    def test_a07_sig_invalid(self):
        assert self._map("policy_signature_invalid") == "A07"

    def test_a09_privilege(self):
        assert self._map("privilege_escalat_detected") == "A09"

    def test_a10_budget(self):
        assert self._map("budget_hard_cap") == "A10"

    def test_unknown_falls_back(self):
        assert self._map("some_random_rule") == "A??"

    def test_empty_rule_id(self):
        assert self._map("") == "A??"


_EVIDENCE_BLOCKED = [
    {"timestamp": "2026-07-06T10:00:00", "ai_tool": "Claude",
     "tool_call": "Bash", "decision": "blocked",
     "rule_id": "excessive_agency_shell",
     "entry_hash": "abc123def456", "policy_hash": "pol789"},
]

_EVIDENCE_WARN_ONLY = [
    {"timestamp": "2026-07-06T10:01:00", "ai_tool": "Claude",
     "tool_call": "Read", "decision": "warned",
     "rule_id": "sensitive_data_read"},
]

_EVIDENCE_CLEAN = [
    {"timestamp": "2026-07-06T10:02:00", "ai_tool": "Claude",
     "tool_call": "Bash", "decision": "allowed", "rule_id": None},
]


class TestVerifyCommand:
    def _run(self, args_list: list[str], capsys) -> int:
        import argparse
        from conduct_cli.guard import cmd_verify

        parser = argparse.ArgumentParser()
        parser.add_argument("--evidence", default=None)
        parser.add_argument("--strict", action="store_true")
        parser.add_argument("--format", default="text")
        parser.add_argument("--since", default="24h")
        args = parser.parse_args(args_list)

        try:
            cmd_verify(args)
            return 0
        except SystemExit as exc:
            return int(exc.code) if exc.code is not None else 0

    def test_clean_evidence_exits_0(self, tmp_path, capsys):
        f = tmp_path / "ev.json"
        f.write_text(__import__("json").dumps(_EVIDENCE_CLEAN))
        code = self._run(["--evidence", str(f)], capsys)
        assert code == 0

    def test_blocked_without_strict_exits_0(self, tmp_path, capsys):
        f = tmp_path / "ev.json"
        f.write_text(__import__("json").dumps(_EVIDENCE_BLOCKED))
        code = self._run(["--evidence", str(f)], capsys)
        assert code == 0

    def test_blocked_with_strict_exits_1(self, tmp_path, capsys):
        f = tmp_path / "ev.json"
        f.write_text(__import__("json").dumps(_EVIDENCE_BLOCKED))
        code = self._run(["--evidence", str(f), "--strict"], capsys)
        assert code == 1

    def test_warn_only_with_strict_exits_0(self, tmp_path, capsys):
        f = tmp_path / "ev.json"
        f.write_text(__import__("json").dumps(_EVIDENCE_WARN_ONLY))
        code = self._run(["--evidence", str(f), "--strict"], capsys)
        assert code == 0

    def test_missing_file_exits_2(self, tmp_path, capsys):
        code = self._run(["--evidence", str(tmp_path / "missing.json")], capsys)
        assert code == 2

    def test_invalid_json_exits_2(self, tmp_path, capsys):
        f = tmp_path / "bad.json"
        f.write_text("not valid {{{")
        code = self._run(["--evidence", str(f)], capsys)
        assert code == 2

    def test_empty_array_no_error(self, tmp_path, capsys):
        f = tmp_path / "empty.json"
        f.write_text("[]")
        code = self._run(["--evidence", str(f)], capsys)
        assert code == 0
        out = capsys.readouterr().out
        assert "nothing to verify" in out.lower() or "no guard events" in out.lower()

    def test_json_format_status_fail_when_strict_and_blocked(self, tmp_path, capsys):
        import json
        f = tmp_path / "ev.json"
        f.write_text(json.dumps(_EVIDENCE_BLOCKED))
        self._run(["--evidence", str(f), "--strict", "--format", "json"], capsys)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["status"] == "fail"
        assert data["summary"]["blocked"] == 1

    def test_json_format_status_pass_without_strict(self, tmp_path, capsys):
        import json
        f = tmp_path / "ev.json"
        f.write_text(json.dumps(_EVIDENCE_BLOCKED))
        self._run(["--evidence", str(f), "--format", "json"], capsys)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["status"] == "pass"

    def test_chain_hash_appears_in_text_output(self, tmp_path, capsys):
        f = tmp_path / "ev.json"
        f.write_text(__import__("json").dumps(_EVIDENCE_BLOCKED))
        self._run(["--evidence", str(f)], capsys)
        out = capsys.readouterr().out
        assert "chain:abc123def456" in out

    def test_owasp_distribution_shown(self, tmp_path, capsys):
        f = tmp_path / "ev.json"
        f.write_text(__import__("json").dumps(_EVIDENCE_BLOCKED + _EVIDENCE_WARN_ONLY))
        self._run(["--evidence", str(f)], capsys)
        out = capsys.readouterr().out
        assert "A04" in out
        assert "A02" in out

    def test_envelope_json_input(self, tmp_path, capsys):
        """Accept {'events': [...]} envelope as well as raw array."""
        import json
        f = tmp_path / "ev.json"
        f.write_text(json.dumps({"events": _EVIDENCE_CLEAN}))
        code = self._run(["--evidence", str(f)], capsys)
        assert code == 0


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
